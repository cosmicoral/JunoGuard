"""Cold-path detonation: requesting it, and trusting its answer carefully.

The gateway asks the Modal worker to install a package in a disposable,
network-blocked sandbox and report what it did. Two rules shape this module.

**It never touches the hot path.** The request is dispatched after the decision
has been made and the response returned. A detonation that is slow, failing, or
switched off changes nothing about what the agent was told.

**The report is hostile input.** It is assembled inside a container where a
package's install script has just executed. Anything it says could have been
chosen by that script — including strings meant to land in an operator's
dashboard. So it is bearer-authenticated, size-capped, and reduced to a known
set of fields with known types before it goes anywhere near the audit trail.
"""

from __future__ import annotations

import hmac
from typing import Any

import httpx

from . import config

# Field-level caps. A malicious package that wants to fill the incident table
# with megabytes of noise gets a truncated string instead.
MAX_STRING = 2000
MAX_LIST_ITEMS = 40
MAX_ITEM_LENGTH = 300

SEVERITIES = {"none", "low", "medium", "high", "critical"}
ECOSYSTEMS = {"npm", "pypi"}

# Nothing outside this set survives validation, whatever the worker sends.
STRING_FIELDS = ("status", "package", "ecosystem", "version", "method",
                 "network", "severity", "summary", "output_tail", "error")
LIST_FIELDS = ("ran_lifecycle_scripts", "canaries_exposed", "unexpected_writes")
BOOL_FIELDS = ("attempted_egress",)
INT_FIELDS = ("exit_code", "duration_ms")


def _clamp(value: Any, limit: int = MAX_STRING) -> str:
    text = str(value if value is not None else "")
    # Control characters are how you smuggle terminal escapes into a log viewer.
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def validate_report(raw: Any) -> dict[str, Any]:
    """Reduce a worker report to fields we recognise, at sizes we accept."""
    if not isinstance(raw, dict):
        raise ValueError("report must be an object")

    clean: dict[str, Any] = {}

    for field in STRING_FIELDS:
        if raw.get(field) is not None:
            clean[field] = _clamp(raw[field])

    for field in LIST_FIELDS:
        value = raw.get(field)
        if isinstance(value, list):
            clean[field] = [_clamp(item, MAX_ITEM_LENGTH) for item in value[:MAX_LIST_ITEMS]]

    for field in BOOL_FIELDS:
        if field in raw:
            clean[field] = bool(raw[field])

    for field in INT_FIELDS:
        value = raw.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            clean[field] = int(value)

    # Enumerations are pinned rather than trusted: `severity` drives how the
    # dashboard renders, so an unrecognised value becomes "unknown" instead of
    # whatever the package felt like claiming.
    if clean.get("severity") not in SEVERITIES:
        clean["severity"] = "unknown"
    if clean.get("ecosystem") not in ECOSYSTEMS:
        clean.pop("ecosystem", None)
    if clean.get("status") not in {"ok", "error"}:
        clean["status"] = "error"

    return clean


def should_detonate(action_type: str, verdict_decision: str, metadata: dict[str, Any]) -> bool:
    """Which installs are worth the sandbox.

    A clean allow needs no evidence — that is the overwhelming majority of
    traffic and detonating it would be pure cost. Everything else earns a look:
    a flag proceeded on thin grounds, a block wants evidence behind it, and an
    unscanned override is by definition something nobody has examined.
    """
    if not config.DETONATION_ENABLED or not config.MODAL_DETONATE_URL:
        return False
    if action_type != "package_install":
        return False
    if metadata.get("unscanned"):
        return True
    if verdict_decision != "allow":
        return True
    verdict = metadata.get("verdict") or {}
    return bool(verdict.get("severity") and verdict["severity"] != "clean")


def request_detonation(
    *, action_id: str, project_id: str, package: str, ecosystem: str, version: str | None
) -> None:
    """Ask the worker to detonate. Best-effort by design.

    Called after the response has gone out. Every failure here is logged and
    swallowed: the guard's decision has already been made and communicated, and
    a detonation service being down must never turn into an agent-visible error.
    """
    if not config.MODAL_DETONATE_URL:
        return

    callback = f"{config.PUBLIC_BASE_URL}/v1/detonations/{action_id}" if config.PUBLIC_BASE_URL else None
    if not callback:
        print("[juno] detonation skipped: PUBLIC_BASE_URL is unset, no callback address")
        return

    try:
        httpx.post(
            f"{config.MODAL_DETONATE_URL}/detonate",
            json={
                "action_id": action_id,
                "project_id": project_id,
                "package": package,
                "ecosystem": ecosystem,
                "version": version,
                "callback_url": callback,
            },
            headers={"Authorization": f"Bearer {config.MODAL_DETONATE_TOKEN}"},
            timeout=10.0,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001 - cold path, never agent-visible
        print(f"[juno] detonation request failed for {package}: {exc}")


def callback_authorized(authorization: str) -> bool:
    """Constant-time check on the worker's bearer token."""
    if not config.DETONATION_CALLBACK_TOKEN:
        return False
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return hmac.compare_digest(token.strip(), config.DETONATION_CALLBACK_TOKEN)
