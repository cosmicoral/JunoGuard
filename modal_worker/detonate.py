"""JunoGuard — package detonation worker (Modal).

Runs a package's install in a throwaway, network-blocked sandbox and reports
what it actually did. This is the **cold path**: it never gates an install and
never blocks an agent. The hot path stays deterministic and local, which is the
one claim the product is built on.

What that buys, precisely:

* For a package that was **blocked**, this is evidence — the blast radius stops
  being inferred from the developer's own .env files and becomes an observation
  about the package.
* For a package that was **flagged and proceeded**, or that went in under an
  operator's `--allow-unscanned` override, it is protective: the report can
  escalate to a block and trip the kill switch after the fact.

It cannot prevent the install it is reporting on. Results arrive afterwards.
Say so plainly wherever this is described.

  Request:  POST /detonate  { action_id, project_id, package, ecosystem,
                              version, callback_url }
            Authorization: Bearer <MODAL_DETONATE_TOKEN>
  Reply:    202 { status: "queued", call_id } — immediately. The sandbox work
            happens in a spawned function so the gateway never waits on it.
  Callback: POST <callback_url> with the report and
            Authorization: Bearer <DETONATION_CALLBACK_TOKEN>.

Secrets (never hardcoded):

  modal secret create junoguard-detonation \\
      MODAL_DETONATE_TOKEN=...        # bearer this endpoint requires
      DETONATION_CALLBACK_TOKEN=...   # bearer we send back to the gateway

Deploy:  modal deploy modal_worker/detonate.py
Dev:     modal serve modal_worker/detonate.py

Everything above `--- serving layer ---` is plain Python with no Modal imports,
so the report shaping is unit-tested in backend/tests without a deployment.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

# --- knobs -------------------------------------------------------------------

SANDBOX_TIMEOUT = int(os.environ.get("DETONATION_TIMEOUT", "180"))
MAX_OUTPUT_CHARS = 4000
MAX_PATHS_REPORTED = 40

# Environment variable *names* a credential-hunting install script looks for.
# The names are what matter: a malicious postinstall dumps the environment or
# greps it for KEY/TOKEN/SECRET, it does not usually pattern-match on a
# provider's prefix.
CANARY_NAMES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "STRIPE_SECRET_KEY",
    "DATABASE_URL",
)

# Values are generated per run rather than hardcoded, for three reasons that all
# point the same way: a literal shaped like a real provider key trips every
# secret scanner that reads this repository (GitHub's push protection caught
# exactly that and was right to), a fixed value can collide with unrelated text
# and produce a false "exposed credential", and a fresh value per detonation
# means a match is unambiguous evidence that *this* run's environment leaked.
CANARY_PREFIX = "junoguard-canary"


def build_canaries(nonce: str | None = None) -> dict[str, str]:
    """Fake credentials for one detonation. Unique, and obviously synthetic."""
    import secrets

    seed = nonce or secrets.token_hex(16)
    return {name: f"{CANARY_PREFIX}-{seed}-{name.lower()}" for name in CANARY_NAMES}

# Directories a package install is expected to touch. A write anywhere else is
# worth naming.
EXPECTED_PREFIXES = ("/work/node_modules", "/work/package.json", "/work/package-lock.json",
                     "/work/.package-lock.json", "/tmp", "/root/.npm", "/root/.cache")

# stderr/stdout fragments that mean the install reached for the network. With
# egress blocked these are failures, and the failure is the signal.
NETWORK_MARKERS = (
    "ENOTFOUND", "ECONNREFUSED", "EAI_AGAIN", "ETIMEDOUT", "network is unreachable",
    "Temporary failure in name resolution", "Could not resolve host", "getaddrinfo",
)


# --- plain core (no Modal imports; unit-tested in backend/tests) --------------


def install_argv(ecosystem: str, package: str, version: str | None) -> list[str]:
    """The command whose behaviour we are observing.

    Lifecycle scripts are deliberately left enabled — they are the thing worth
    watching. That is the entire reason this runs in a disposable sandbox with
    no network rather than on anyone's machine.
    """
    spec = f"{package}@{version}" if version else package
    if ecosystem == "npm":
        return ["npm", "install", "--no-audit", "--no-fund", "--foreground-scripts", spec]
    pyspec = f"{package}=={version}" if version else package
    return ["pip", "install", "--no-input", "--disable-pip-version-check", pyspec]


def clamp(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def unexpected_paths(paths: list[str]) -> list[str]:
    """Filesystem writes outside where an install has any business writing."""
    out = [p for p in paths if not p.startswith(EXPECTED_PREFIXES)]
    return sorted(set(out))[:MAX_PATHS_REPORTED]


def canaries_found(haystack: str, canaries: dict[str, str]) -> list[str]:
    """Which of this run's fake credentials appear in output or staged files."""
    return sorted(name for name, value in canaries.items() if value in (haystack or ""))


def attempted_egress(output: str) -> bool:
    low = (output or "").lower()
    return any(marker.lower() in low for marker in NETWORK_MARKERS)


def declared_scripts(package_json: dict[str, Any] | None) -> list[str]:
    """Lifecycle hooks the package declares. Deterministic, unlike observation."""
    scripts = ((package_json or {}).get("scripts") or {}) if isinstance(package_json, dict) else {}
    hooks = ("preinstall", "install", "postinstall", "prepare", "prepublish")
    return [h for h in hooks if scripts.get(h)]


def severity_of(report: dict[str, Any]) -> str:
    """How alarming is this, on the evidence actually collected?

    Deliberately conservative. A postinstall script on its own is ordinary —
    native modules build that way. Reading a credential and reaching for the
    network is not.
    """
    if report.get("canaries_exposed"):
        return "critical"
    if report.get("attempted_egress") and report.get("ran_lifecycle_scripts"):
        return "high"
    if report.get("unexpected_writes") or report.get("attempted_egress"):
        return "medium"
    if report.get("ran_lifecycle_scripts"):
        return "low"
    return "none"


def summarise(report: dict[str, Any]) -> str:
    """One line a human reads first. Says what was seen, not what it means."""
    if report.get("status") == "error":
        return f"Detonation did not complete: {report.get('error', 'unknown error')}"

    bits: list[str] = []
    if report.get("ran_lifecycle_scripts"):
        bits.append(f"ran {', '.join(report['ran_lifecycle_scripts'])}")
    if report.get("attempted_egress"):
        bits.append("attempted network egress (blocked)")
    if report.get("canaries_exposed"):
        bits.append(f"exposed {', '.join(report['canaries_exposed'])}")
    writes = report.get("unexpected_writes") or []
    if writes:
        bits.append(f"wrote outside the package tree ({len(writes)} path(s))")
    if not bits:
        return "Installed with no observed lifecycle scripts, egress or stray writes."
    return "Install " + "; ".join(bits) + "."


def shape_report(
    *,
    package: str,
    ecosystem: str,
    version: str | None,
    exit_code: int | None,
    output: str,
    written_paths: list[str],
    canaries: dict[str, str] | None = None,
    package_json: dict[str, Any] | None,
    duration_ms: int,
    error: str | None = None,
) -> dict[str, Any]:
    """Turn raw sandbox observations into the report the gateway stores.

    Every field is something observed or declared. There is no inference here
    beyond `severity`, which is explicitly labelled as a judgement.
    """
    if error:
        return {
            "status": "error",
            "error": clamp(error, 400),
            "package": package,
            "ecosystem": ecosystem,
            "version": version,
            "method": "modal-sandbox",
            "duration_ms": duration_ms,
        }

    report: dict[str, Any] = {
        "status": "ok",
        "package": package,
        "ecosystem": ecosystem,
        "version": version,
        "method": "modal-sandbox",
        "network": "blocked",
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "ran_lifecycle_scripts": declared_scripts(package_json),
        "attempted_egress": attempted_egress(output),
        "canaries_exposed": canaries_found(output, canaries or {}),
        "unexpected_writes": unexpected_paths(written_paths),
        "output_tail": clamp(output[-MAX_OUTPUT_CHARS:] if output else ""),
    }
    report["severity"] = severity_of(report)
    report["summary"] = summarise(report)
    return report


# --- serving layer (Modal) ----------------------------------------------------

try:  # importable without Modal installed, so the core stays unit-testable
    import modal
except ImportError:  # pragma: no cover - only on the deployed side
    modal = None  # type: ignore[assignment]


if modal is not None:
    app = modal.App("junoguard-detonation")

    # The worker itself. Nothing untrusted runs here — it only drives the
    # sandbox and posts the report.
    worker_image = modal.Image.debian_slim(python_version="3.12").pip_install(
        "httpx>=0.27", "fastapi[standard]>=0.115"
    )

    # Where the package actually gets installed. Node and Python both present so
    # one image serves both ecosystems.
    sandbox_image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("nodejs", "npm", "findutils")
        .workdir("/work")
    )

    SECRETS = [modal.Secret.from_name("junoguard-detonation")]

    @app.function(image=worker_image, secrets=SECRETS, timeout=SANDBOX_TIMEOUT + 60)
    def detonate(job: dict[str, Any]) -> dict[str, Any]:
        """Install one package in an isolated sandbox and report what happened."""
        import httpx

        package = job["package"]
        ecosystem = job.get("ecosystem", "npm")
        version = job.get("version")
        started = time.time()
        canaries = build_canaries()

        sandbox = None
        try:
            sandbox = modal.Sandbox.create(
                image=sandbox_image,
                app=app,
                # The load-bearing line. Egress is denied, so any attempt fails
                # loudly and the failure itself becomes evidence.
                block_network=True,
                timeout=SANDBOX_TIMEOUT,
                # Fakes, so a package that reads them gives itself away.
                secrets=[modal.Secret.from_dict(canaries)],
                workdir="/work",
            )

            # Baseline of what exists before the install.
            before = sandbox.exec("find", "/work", "/root", "/etc", "-type", "f")
            before_paths = set(before.stdout.read().splitlines())

            proc = sandbox.exec(*install_argv(ecosystem, package, version))
            output = (proc.stdout.read() or "") + (proc.stderr.read() or "")
            exit_code = proc.wait()

            after = sandbox.exec("find", "/work", "/root", "/etc", "-type", "f")
            written = sorted(set(after.stdout.read().splitlines()) - before_paths)

            # The package's own declared lifecycle hooks — deterministic, and a
            # useful cross-check on what the output suggests.
            package_json = None
            if ecosystem == "npm":
                cat = sandbox.exec("cat", f"/work/node_modules/{package}/package.json")
                raw = cat.stdout.read()
                if raw:
                    import json as _json

                    try:
                        package_json = _json.loads(raw)
                    except ValueError:
                        package_json = None

            # Grep the staged tree for the canaries too, not just stdout: a
            # script that writes a credential to a file for later pickup never
            # prints it.
            grep_hay = output
            if written:
                pattern = "|".join(re.escape(v) for v in canaries.values())
                hits = sandbox.exec("grep", "-rlE", pattern, "/work", "/root", "/tmp")
                found_files = hits.stdout.read()
                if found_files.strip():
                    # A script that writes a credential to a file for later
                    # pickup never prints it, so a filesystem hit counts as
                    # exposure just as a printed one does.
                    grep_hay += "\n" + "\n".join(canaries.values())

            report = shape_report(
                package=package,
                ecosystem=ecosystem,
                version=version,
                exit_code=exit_code,
                output=grep_hay,
                written_paths=written,
                package_json=package_json,
                canaries=canaries,
                duration_ms=int((time.time() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - a failed detonation is still news
            report = shape_report(
                package=package,
                ecosystem=ecosystem,
                version=version,
                exit_code=None,
                output="",
                written_paths=[],
                package_json=None,
                duration_ms=int((time.time() - started) * 1000),
                error=str(exc),
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.terminate()
                except Exception:  # noqa: BLE001
                    pass

        # Hand the report back to the gateway, which stays the only writer to
        # the audit trail.
        callback = job.get("callback_url")
        if callback:
            token = os.environ.get("DETONATION_CALLBACK_TOKEN", "")
            try:
                httpx.post(
                    callback,
                    json={"action_id": job.get("action_id"), "report": report},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15.0,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[juno] detonation callback failed: {exc}")

        return report

    @app.function(image=worker_image, secrets=SECRETS, timeout=30, max_containers=4)
    @modal.asgi_app()
    def web():
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        api = FastAPI()

        @api.get("/")
        def health():
            return {
                "ok": True,
                "service": "junoguard-detonation",
                "network": "blocked",
                "auth": bool(os.environ.get("MODAL_DETONATE_TOKEN")),
            }

        @api.post("/detonate")
        async def enqueue(request: Request):
            expected = os.environ.get("MODAL_DETONATE_TOKEN")
            if not expected:
                return JSONResponse(
                    {"error": "not_configured", "detail": "MODAL_DETONATE_TOKEN is unset."},
                    status_code=503,
                )
            if request.headers.get("authorization", "") != f"Bearer {expected}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)

            job = await request.json()
            if not job.get("package"):
                return JSONResponse({"error": "package is required"}, status_code=400)

            # Spawned, not called: the gateway gets its 202 immediately and the
            # sandbox takes as long as it takes.
            call = detonate.spawn(job)
            return JSONResponse({"status": "queued", "call_id": call.object_id}, status_code=202)

        return api
