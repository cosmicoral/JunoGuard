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

# No `from __future__ import annotations` here, deliberately. FastAPI resolves
# an endpoint's annotations against module globals, and this file imports
# FastAPI inside web() so the deploying machine does not need it installed.
# With postponed evaluation, `request: Request` becomes the unresolvable string
# "Request", FastAPI falls back to treating it as a query parameter, and every
# POST returns 422 "field required". Native 3.10+ syntax covers everything used
# below, so the import buys nothing and costs that.

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

# The extracted package tree and the artifact we put there. A write anywhere
# else — /root, /etc, a sibling of the package — is worth naming.
EXPECTED_PREFIXES = ("/work/package", "/work/artifact", "/root/.npm", "/root/.cache")

# stderr/stdout fragments that mean the install reached for the network. With
# egress blocked these are failures, and the failure is the signal.
NETWORK_MARKERS = (
    "ENOTFOUND", "ECONNREFUSED", "EAI_AGAIN", "ETIMEDOUT", "network is unreachable",
    "Temporary failure in name resolution", "Could not resolve host", "getaddrinfo",
)


# --- plain core (no Modal imports; unit-tested in backend/tests) --------------


def lifecycle_argv(script: str) -> list[str]:
    """Run one declared lifecycle script inside the extracted package.

    The package is *not* installed with `npm install`. A network-blocked
    container cannot reach the registry, so npm would fail to resolve anything
    and no package code would run at all — the first version of this reported
    "attempted egress" for every package on earth, and that egress was npm's,
    not the package's.

    Instead the artifact is fetched and digest-verified outside the sandbox,
    extracted inside it, and its declared hooks are executed directly. That
    observes the thing worth observing, and it makes an egress attempt mean
    something: nothing else in the container has any reason to touch the
    network.
    """
    return ["sh", "-lc", f"cd /work/package && {script}"]


def verify_digest(data: bytes, algorithm: str, expected: str) -> bool:
    """Is this the artifact the registry published?

    Fetching happens outside the sandbox, so the bytes must be pinned to what
    the registry says they are. Otherwise the thing being detonated is whatever
    answered the HTTP request, which is a different experiment.
    """
    import base64
    import hashlib

    digest = hashlib.new(algorithm, data).digest()
    if expected.startswith(f"{algorithm}-"):  # npm `integrity`: sha512-<base64>
        return base64.b64encode(digest).decode() == expected.split("-", 1)[1]
    return digest.hex() == expected  # npm `shasum` / PyPI `digests`: hex


def npm_artifact(package: str, version: str | None) -> tuple[str, str, str, str]:
    """(tarball url, resolved version, digest algorithm, expected digest)."""
    import httpx

    base = os.environ.get("NPM_REGISTRY_URL", "https://registry.npmjs.org").rstrip("/")
    from urllib.parse import quote

    coordinate = quote(package, safe="@")
    url = f"{base}/{coordinate}/{version}" if version else f"{base}/{coordinate}/latest"
    meta = httpx.get(url, timeout=20.0, follow_redirects=True).raise_for_status().json()
    dist = meta.get("dist") or {}
    integrity = dist.get("integrity")
    if integrity and "-" in integrity:
        return dist["tarball"], meta["version"], integrity.split("-", 1)[0], integrity
    return dist["tarball"], meta["version"], "sha1", dist["shasum"]


def pypi_artifact(package: str, version: str | None) -> tuple[str, str, str, str]:
    import httpx

    base = os.environ.get("PYPI_URL", "https://pypi.org").rstrip("/")
    from urllib.parse import quote

    path = f"/pypi/{quote(package)}/{version}/json" if version else f"/pypi/{quote(package)}/json"
    meta = httpx.get(f"{base}{path}", timeout=20.0, follow_redirects=True).raise_for_status().json()
    resolved = meta["info"]["version"]
    files = meta.get("urls") or []
    # Prefer an sdist: it is the one that can carry a setup.py worth watching.
    chosen = next((f for f in files if f.get("packagetype") == "sdist"), None) or (
        files[0] if files else None
    )
    if not chosen:
        raise RuntimeError(f"no distribution files published for {package} {resolved}")
    digests = chosen.get("digests") or {}
    algorithm = "sha256" if "sha256" in digests else next(iter(digests), "md5")
    return chosen["url"], resolved, algorithm, digests[algorithm]


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
            # 1. Fetch the artifact out here, where there *is* network, and pin
            #    it to the digest the registry published. The sandbox never
            #    talks to a registry, so anything it does reach for is the
            #    package's own doing.
            fetch = npm_artifact if ecosystem == "npm" else pypi_artifact
            tarball_url, version, algorithm, expected = fetch(package, version)
            blob = httpx.get(tarball_url, timeout=60.0, follow_redirects=True)
            blob.raise_for_status()
            artifact = blob.content
            if not verify_digest(artifact, algorithm, expected):
                raise RuntimeError(
                    f"{package}@{version} does not match its published {algorithm} digest"
                )

            sandbox = modal.Sandbox.create(
                image=sandbox_image,
                app=app,
                # The load-bearing line. Egress is denied, and nothing in here
                # has a legitimate reason to want it.
                block_network=True,
                timeout=SANDBOX_TIMEOUT,
                # Fakes, so a package that reads them gives itself away.
                secrets=[modal.Secret.from_dict(canaries)],
                workdir="/work",
            )

            # 2. Hand the verified bytes in, and unpack them.
            with sandbox.open("/work/artifact", "wb") as handle:
                handle.write(artifact)
            unpack = sandbox.exec("sh", "-lc", "cd /work && tar -xzf artifact")
            unpack_output = (unpack.stdout.read() or "") + (unpack.stderr.read() or "")
            unpack.wait()

            # 3. Read the manifest to learn which hooks it declares.
            import json as _json

            package_json = None
            manifest = sandbox.exec("sh", "-lc", "cat /work/package/package.json 2>/dev/null")
            raw = manifest.stdout.read()
            manifest.wait()
            if raw.strip():
                try:
                    package_json = _json.loads(raw)
                except ValueError:
                    package_json = None
            if ecosystem == "pypi":
                # An sdist has no package.json; setup.py is the equivalent hook
                # and it executes on build.
                probe = sandbox.exec("sh", "-lc", "ls /work/*/setup.py 2>/dev/null | head -1")
                if probe.stdout.read().strip():
                    package_json = {"scripts": {"install": "python setup.py --version"}}
                probe.wait()

            # 4. Baseline the filesystem, then run each declared hook.
            before = sandbox.exec("sh", "-lc", "find /work /root /etc /tmp -type f 2>/dev/null")
            before_paths = set(before.stdout.read().splitlines())
            before.wait()

            output = unpack_output
            exit_code = 0
            for hook in declared_scripts(package_json):
                script = (package_json.get("scripts") or {})[hook]
                proc = sandbox.exec(*lifecycle_argv(script))
                output += f"\n$ [{hook}] {script}\n"
                output += (proc.stdout.read() or "") + (proc.stderr.read() or "")
                code = proc.wait()
                exit_code = code or exit_code

            after = sandbox.exec("sh", "-lc", "find /work /root /etc /tmp -type f 2>/dev/null")
            written = sorted(set(after.stdout.read().splitlines()) - before_paths)
            after.wait()

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
