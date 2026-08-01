"""The live decision feed behind `juno watch`.

Live mode derives events from `GET /v1/guard/status`, which is the only polling
surface the frozen contract gives us: a rise in `blocked_today` is a block, a
rise in `open_incidents` is an incident, a rise in `spend_today_usd` is billable
traffic. Offline mode replays a scripted run so the feed still moves on stage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .render import S_ALLOW, S_BLOCK, S_DIM, S_FLAG, S_KEY, Line

_LANE_W = 10
_DECISION_W = 7


@dataclass
class Event:
    decision: str  # allow | flag | block | incident
    lane: str  # install | llm | project
    detail: str


_STYLES = {
    "allow": (S_ALLOW, "allow"),
    "flag": (S_FLAG, "FLAG"),
    "block": (S_BLOCK, "BLOCK"),
    "incident": (S_BLOCK, "!"),
}


def render_event(event: Event, clock: str) -> Line:
    style, label = _STYLES.get(event.decision, (S_DIM, event.decision))
    detail_style = S_DIM if event.decision == "allow" else style
    return [
        (f"{clock}  ", S_DIM),
        (label.ljust(_DECISION_W), style),
        (event.lane.ljust(_LANE_W), S_KEY),
        (event.detail, detail_style),
    ]


def clock_now() -> str:
    return time.strftime("%H:%M:%S")


# --------------------------------------------------------------------------
# live mode — status deltas
# --------------------------------------------------------------------------


def diff_status(previous: dict, current: dict) -> list[Event]:
    events: list[Event] = []

    if previous.get("status") != current.get("status"):
        state = current.get("status")
        events.append(
            Event(
                "incident" if state != "active" else "allow",
                "project",
                f"project is now {state}",
            )
        )

    blocked_delta = (current.get("blocked_today") or 0) - (previous.get("blocked_today") or 0)
    for _ in range(max(0, blocked_delta)):
        events.append(Event("block", "guard", "an action was blocked by policy"))

    incident_delta = (current.get("open_incidents") or 0) - (previous.get("open_incidents") or 0)
    for _ in range(max(0, incident_delta)):
        events.append(Event("incident", "incident", "new incident opened"))

    spend_delta = (current.get("spend_today_usd") or 0.0) - (previous.get("spend_today_usd") or 0.0)
    if spend_delta > 0:
        budget = current.get("daily_budget_usd") or 0.0
        remaining = current.get("remaining_usd")
        if remaining is None:
            remaining = max(0.0, budget - (current.get("spend_today_usd") or 0.0))
        events.append(
            Event("allow", "llm", f"+${spend_delta:.6f}  ·  ${remaining:.4f} left today")
        )

    rpm = current.get("requests_last_min")
    cap = current.get("max_requests_per_min")
    was_over = (previous.get("requests_last_min") or 0) > (previous.get("max_requests_per_min") or 10**9)
    if rpm is not None and cap and rpm > cap and not was_over:
        events.append(Event("flag", "burst", f"{rpm} req/min against a {cap}/min limit"))

    return events


# --------------------------------------------------------------------------
# offline mode — scripted run
# --------------------------------------------------------------------------

SCRIPT: list[Event] = [
    Event("allow", "install", "express (npm) · clean"),
    Event("allow", "llm", "gpt-4o · 1,204 in / 287 out · $0.000431"),
    Event("allow", "install", "zod (npm) · clean"),
    Event("flag", "install", "@ossprey/suspicious-package (npm) · no published provenance"),
    Event("allow", "llm", "gpt-4o · 842 in / 190 out · $0.000312"),
    Event("block", "install", "@ossprey/test-package (npm) · malicious: obfuscated postinstall"),
    Event("incident", "incident", "critical · attempted credential exfiltration on install"),
    Event("allow", "llm", "gpt-4o · 611 in / 140 out · $0.000253"),
    Event("flag", "burst", "63 req/min against a 60/min limit"),
]
