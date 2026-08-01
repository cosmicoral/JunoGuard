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


def publish(event_type: str, payload: dict[str, Any]) -> int:
    """Record an event. Returns its sequence number."""
    global _seq
    with _lock:
        _seq += 1
        _events.append({"seq": _seq, "type": event_type, "data": payload})
        return _seq


def since(cursor: int) -> list[dict[str, Any]]:
    """Every event after `cursor`, oldest first."""
    with _lock:
        return [e for e in _events if e["seq"] > cursor]


def latest_seq() -> int:
    with _lock:
        return _seq


def recent(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        return list(_events)[-limit:]
