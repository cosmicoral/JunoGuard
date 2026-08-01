"""In-process event feed.

The dashboard's first choice is Supabase Realtime. This is the fallback for
when Supabase is not configured or is unreachable — the demo cannot depend on
a credential arriving.

Deliberately a bounded ring buffer polled by the SSE route rather than
cross-thread asyncio plumbing: FastAPI runs sync routes in a threadpool, and
a sequence-numbered buffer is trivially correct from any thread.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

MAX_EVENTS = 500

_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_seq = 0


def publish(event_type: str, project_id: str, payload: dict[str, Any]) -> int:
    """Record an event against its project. Returns its sequence number.

    project_id is not optional. Incident evidence carries credential names and
    blast-radius detail, and a buffer with no owner recorded is a buffer that
    cannot be filtered — which is how this feed came to serve every project's
    events to anyone who asked.
    """
    global _seq
    with _lock:
        _seq += 1
        _events.append(
            {"seq": _seq, "type": event_type, "project_id": project_id, "data": payload}
        )
        return _seq


def since(cursor: int, project_id: str) -> list[dict[str, Any]]:
    """Every event after `cursor` belonging to `project_id`, oldest first."""
    with _lock:
        return [
            e for e in _events if e["seq"] > cursor and e["project_id"] == project_id
        ]


def latest_seq() -> int:
    with _lock:
        return _seq


def recent(limit: int, project_id: str) -> list[dict[str, Any]]:
    with _lock:
        mine = [e for e in _events if e["project_id"] == project_id]
    return mine[-limit:]
