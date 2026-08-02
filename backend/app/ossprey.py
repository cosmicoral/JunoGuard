"""Ossprey supply-chain verdicts.

Lane A's source of truth. Falls back to a deterministic mock when no API key
is configured, so the block path is demonstrable without the network.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Literal
from urllib.parse import quote

import httpx

from . import config

Severity = Literal["malicious", "suspicious", "unknown", "clean", "unavailable"]

SEVERITY_ORDER: dict[str, int] = {
    "clean": 0,
    "unknown": 1,
    "suspicious": 2,
    "malicious": 3,
}

# `unknown` is a statement about the package: nobody has established a
# reputation for it. `unavailable` is a statement about us: the scan did not
# happen. They are not interchangeable, and an infrastructure failure must never
# be graded as if it were evidence about the package.
UNAVAILABLE = "unavailable"

# Ossprey ships this deliberately-flagged package for integration testing.
CANARY = "@ossprey/test-package"

# --- caching ----------------------------------------------------------------
#
# The same package gets scanned repeatedly in a session and a scan is the
# slowest thing on the hot path, so a cache is worth having. The previous one
# was keyed on the string "latest" with no expiry, which meant a package cleared
# this morning kept its allow after a malicious version was published this
# afternoon — for as long as the process lived.
#
# Three rules follow from that:
#   * cache only an immutable coordinate — a resolved version, never "latest"
#   * expire entries, and bound how many there are
#   * never cache a verdict that does not exist (a scanner outage)

CACHE_TTL_SECONDS = 300
RESOLVE_TTL_SECONDS = 60
MAX_CACHE_ENTRIES = 512

# --- scan budget -------------------------------------------------------------
#
# The scan is asynchronous and the gate is not, so the hot path waits. These
# bound that wait. An install that exceeds the budget is refused as unscanned,
# never allowed on the assumption it was probably fine.
#
# A budget under the scanner's real spread does not make the gateway faster, it
# makes it refuse popular packages. See config.OSSPREY_SCAN_BUDGET_SECONDS for
# the measurements behind the default.

SCAN_BUDGET_SECONDS = config.OSSPREY_SCAN_BUDGET_SECONDS
POLL_INTERVAL_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10.0

# Part of every cache key. Bump it when normalisation or thresholds change, so
# verdicts decided under the old rules are not reused under the new ones.
SCANNER_POLICY_VERSION = "1"

_lock = threading.Lock()
_verdicts: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_resolved: OrderedDict[str, tuple[float, str]] = OrderedDict()


def _get(store: OrderedDict[str, tuple[float, Any]], key: str) -> Any | None:
    with _lock:
        entry = store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.time():
            del store[key]
            return None
        store.move_to_end(key)
        return value


def _put(store: OrderedDict[str, tuple[float, Any]], key: str, value: Any, ttl: int) -> None:
    with _lock:
        store[key] = (time.time() + ttl, value)
        store.move_to_end(key)
        while len(store) > MAX_CACHE_ENTRIES:
            store.popitem(last=False)


def clear_cache() -> None:
    """Drop every cached verdict and resolution. For tests and operators."""
    with _lock:
        _verdicts.clear()
        _resolved.clear()


def _cache_key(ecosystem: str, package: str, version: str) -> str:
    return f"v{SCANNER_POLICY_VERSION}|{ecosystem}|{package.strip().lower()}@{version}"


def resolve_version(package: str, ecosystem: str) -> str | None:
    """Ask the registry which version `latest` currently means.

    Without this there is no immutable coordinate to cache against, and a cached
    allow for "latest" silently covers versions nobody has looked at. Returning
    None is a valid answer: the scan still happens, it just is not cached.
    """
    key = f"{ecosystem}|{package.strip().lower()}"
    hit = _get(_resolved, key)
    if hit:
        return str(hit)

    try:
        if ecosystem == "npm":
            url = f"{config.NPM_REGISTRY_URL}/{quote(package, safe='@')}/latest"
            version = str(httpx.get(url, timeout=5.0).raise_for_status().json()["version"])
        else:
            url = f"{config.PYPI_URL}/pypi/{quote(package)}/json"
            body = httpx.get(url, timeout=5.0).raise_for_status().json()
            version = str(body["info"]["version"])
    except Exception as exc:  # noqa: BLE001 - resolution is best-effort
        print(f"[juno] could not resolve a version for {package}: {exc}")
        return None

    _put(_resolved, key, version, RESOLVE_TTL_SECONDS)
    return version


def _mock_verdict(package: str) -> dict[str, Any]:
    if package.strip().lower() == CANARY:
        return {
            "source": "mock",
            "severity": "malicious",
            "available": True,
            "findings": [
                "Obfuscated postinstall script",
                "Outbound POST on install",
                "Reads process environment at install time",
            ],
        }
    return {"source": "mock", "severity": "clean", "available": True, "findings": []}


def purl(package: str, ecosystem: str, version: str | None) -> str:
    """Package URL, the coordinate Ossprey's SBOM speaks in.

    An npm scope's `@` is percent-encoded — `pkg:npm/%40scope/name@1.0.0` — and
    the `@` before the version is not. Getting that backwards produces a purl
    the scanner accepts and silently scans nothing useful.
    """
    kind = "npm" if ecosystem == "npm" else "pypi"
    name = package.strip()
    coordinate = f"%40{name[1:]}" if name.startswith("@") else name
    return f"pkg:{kind}/{coordinate}" + (f"@{version}" if version else "")


def _parse(output: dict[str, Any]) -> dict[str, Any]:
    """Normalise a finished Ossprey scan into our envelope.

    The response carries no severity field. It carries a `vulnerabilities` list
    whose entries have a `type`, and the absence of entries is the clean signal.
    Read it defensively: an entry whose type we do not recognise is still an
    entry, and grading it `clean` because the label was unfamiliar is exactly
    the failure this function exists to avoid.
    """
    vulnerabilities = output.get("vulnerabilities") or []
    extra = output.get("findings") or []

    severity = "clean"
    for vuln in vulnerabilities:
        kind = str((vuln or {}).get("type") or "").lower()
        if "malware" in kind or "malicious" in kind:
            severity = "malicious"
            break
        # A vulnerability that is not malware is still something to answer for.
        severity = "suspicious"

    if severity == "clean" and extra:
        severity = "suspicious"

    findings: list[str] = []
    for vuln in vulnerabilities:
        vuln = vuln or {}
        label = str(vuln.get("type") or "finding")
        detail = str(vuln.get("description") or vuln.get("id") or "").strip()
        findings.append(f"{label}: {detail}" if detail else label)
    findings += [str(f) for f in extra]

    return {
        "source": "ossprey",
        "severity": severity,
        "available": True,
        "findings": findings[:5],
    }


def _headers() -> dict[str, str]:
    # `x-api-key`, not an Authorization bearer. The bearer form is accepted by
    # the edge and then 404s on every path, which reads like a missing endpoint
    # rather than a rejected credential.
    return {"x-api-key": config.OSSPREY_API_KEY, "Content-Type": "application/json"}


def _scan_and_wait(package: str, ecosystem: str, version: str | None) -> dict[str, Any]:
    """Submit a scan and block until it finishes, or run out of patience.

    Ossprey's scan is asynchronous — the POST only queues it — but the gate this
    feeds is not: an agent is waiting on a decision and the whole claim is that
    the decision happens before the install lands. So the wait happens here,
    bounded, and a scan that outlives the budget raises rather than returning
    something that would be read as a verdict. The caller turns that into
    `unavailable`, which fails closed.

    Observed round trip is a few seconds. The budget is deliberately several
    times that, because being slow once is better than blocking a clean install.
    """
    submit = httpx.post(
        f"{config.OSSPREY_BASE_URL}/public/v1/scans",
        headers=_headers(),
        json={
            "sbom": {
                "format": "OSSBOM",
                "components": [
                    {
                        "purl": purl(package, ecosystem, version),
                        "name": package,
                        "version": version,
                        "type": "npm" if ecosystem == "npm" else "pypi",
                    }
                ],
            }
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    submit.raise_for_status()
    queued = submit.json()
    sbom_id, scan_id = queued.get("sbom_id"), queued.get("scan_id")
    if not (sbom_id and scan_id):
        raise RuntimeError(f"scan was not queued: {queued}")

    deadline = time.time() + SCAN_BUDGET_SECONDS
    while True:
        poll = httpx.get(
            f"{config.OSSPREY_BASE_URL}/public/v1/scans/status",
            headers=_headers(),
            params={"sbom_id": sbom_id, "scan_id": scan_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        poll.raise_for_status()
        body = poll.json()
        status = str(body.get("status") or "").upper()

        if status == "SUCCEEDED":
            return body.get("output") or {}
        if status in {"QUEUED", "RUNNING"}:
            if time.time() >= deadline:
                raise TimeoutError(
                    f"scan still {status} after {SCAN_BUDGET_SECONDS}s"
                )
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        # FAILED, or a status this code has never seen. Either way it is not a
        # verdict, and guessing which way it would have gone is the one thing
        # this module must never do.
        raise RuntimeError(f"scan ended {status or 'with no status'}")


def scan(package: str, ecosystem: str = "npm", version: str | None = None) -> dict[str, Any]:
    """Get a verdict for one package, caching only what is safe to cache."""
    if not config.USE_OSSPREY:
        # Deterministic and local: nothing to gain from caching it, and a mock in
        # the cache is a mock that outlives the reason it was there.
        return _mock_verdict(package)

    # An immutable coordinate, or no caching at all.
    resolved = version or resolve_version(package, ecosystem)
    key = _cache_key(ecosystem, package, resolved) if resolved else None

    if key:
        cached = _get(_verdicts, key)
        if cached:
            return {**cached, "source": "cache", "version": resolved}

    try:
        verdict = _parse(_scan_and_wait(package, ecosystem, resolved))
    except Exception as exc:  # noqa: BLE001
        # An outage is not a verdict. Reporting it as `unknown` let the default
        # policy treat "we could not look" as "nothing much found" and hand back
        # a proceedable flag. Say plainly that no scan happened, and never cache
        # it — the next attempt must go back to the network.
        print(f"[juno] Ossprey scan failed for {package}: {exc}")
        return {
            "source": "ossprey",
            "severity": UNAVAILABLE,
            "available": False,
            "findings": ["Scanner unreachable — no scan was performed"],
            "error": str(exc),
        }

    if key:
        _put(_verdicts, key, verdict, CACHE_TTL_SECONDS)
    return {**verdict, "version": resolved}


def at_least(severity: str, threshold: str) -> bool:
    return SEVERITY_ORDER.get(severity, 1) >= SEVERITY_ORDER.get(threshold, 3)
