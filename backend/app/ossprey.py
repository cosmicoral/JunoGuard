"""Ossprey supply-chain verdicts.

Lane A's source of truth. Falls back to a deterministic mock when no API key
is configured, so the block path is demonstrable without the network.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from . import config

Severity = Literal["malicious", "suspicious", "unknown", "clean"]

SEVERITY_ORDER: dict[str, int] = {
    "clean": 0,
    "unknown": 1,
    "suspicious": 2,
    "malicious": 3,
}

# Ossprey ships this deliberately-flagged package for integration testing.
CANARY = "@ossprey/test-package"

# Small cache — the same package gets scanned repeatedly during a session and
# a scan is the slowest thing on the hot path.
_cache: dict[str, dict[str, Any]] = {}


def _mock_verdict(package: str) -> dict[str, Any]:
    if package.strip().lower() == CANARY:
        return {
            "source": "mock",
            "severity": "malicious",
            "findings": [
                "Obfuscated postinstall script",
                "Outbound POST on install",
                "Reads process environment at install time",
            ],
        }
    return {"source": "mock", "severity": "clean", "findings": []}


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
        "findings": [str(f) for f in findings][:5],
    }


def scan(package: str, ecosystem: str = "npm", version: str | None = None) -> dict[str, Any]:
    key = f"{ecosystem}:{package}@{version or 'latest'}"
    if key in _cache:
        return {**_cache[key], "source": "cache"}

    if not config.USE_OSSPREY:
        verdict = _mock_verdict(package)
        _cache[key] = verdict
        return verdict

    try:
        r = httpx.post(
            f"{config.OSSPREY_BASE_URL}/v1/scan",
            headers={"Authorization": f"Bearer {config.OSSPREY_API_KEY}"},
            json={"package": package, "ecosystem": ecosystem, "version": version},
            timeout=10.0,
        )
        r.raise_for_status()
        verdict = _parse(r.json())
    except Exception as exc:  # noqa: BLE001
        # Never fail open on a scanner outage, and never hard-fail the agent.
        # Unknown is the honest answer, and policy decides what to do with it.
        print(f"[juno] Ossprey scan failed for {package}: {exc}")
        return {
            "source": "ossprey",
            "severity": "unknown",
            "findings": ["Scanner unreachable — verdict unavailable"],
        }

    _cache[key] = verdict
    return verdict


def at_least(severity: str, threshold: str) -> bool:
    return SEVERITY_ORDER.get(severity, 1) >= SEVERITY_ORDER.get(threshold, 3)
