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


def _parse(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise Ossprey's response into our envelope.

    Ossprey's shape has moved during the beta, so read defensively and treat
    anything unrecognised as `unknown` rather than assuming clean.
    """
    severity = (
        payload.get("severity")
        or payload.get("verdict")
        or ("malicious" if payload.get("malware") else None)
        or "unknown"
    )
    severity = str(severity).lower()
    if severity in {"malware", "malicious", "critical", "high"}:
        severity = "malicious"
    elif severity in {"suspicious", "medium", "warn"}:
        severity = "suspicious"
    elif severity in {"clean", "ok", "safe", "none", "low"}:
        severity = "clean"
    else:
        severity = "unknown"

    findings = payload.get("findings") or payload.get("reasons") or []
    if isinstance(findings, str):
        findings = [findings]

    return {
        "source": "ossprey",
        "severity": severity,
        "available": True,
        "findings": [str(f) for f in findings][:5],
    }


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
        r = httpx.post(
            f"{config.OSSPREY_BASE_URL}/v1/scan",
            headers={"Authorization": f"Bearer {config.OSSPREY_API_KEY}"},
            json={"package": package, "ecosystem": ecosystem, "version": resolved},
            timeout=10.0,
        )
        r.raise_for_status()
        verdict = _parse(r.json())
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
