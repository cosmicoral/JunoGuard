"""Short-lived stream tokens.

`EventSource` cannot send headers, so the live feed needs a credential that
survives in a query string. A project key must never be that credential: it is
long-lived, it authorizes writes to both guarded lanes, and a URL ends up in
logs, proxies and browser history.

A stream token is signed, carries the project it is scoped to, and expires in
minutes. It authorizes exactly one thing: reading that project's event feed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from . import config

# Falling back to a per-process secret is deliberate: tokens issued before a
# restart stop working, which is the safe direction. Set STREAM_TOKEN_SECRET
# when running more than one replica.
_SECRET = (config.STREAM_TOKEN_SECRET or secrets.token_urlsafe(32)).encode("utf-8")

TTL_SECONDS = 300
_SIG_LENGTH = 32


def _sign(payload: bytes) -> str:
    return hmac.new(_SECRET, payload, hashlib.sha256).hexdigest()[:_SIG_LENGTH]


def issue(project_id: str, ttl: int = TTL_SECONDS) -> tuple[str, int]:
    """Return a token scoped to one project, and its lifetime in seconds."""
    expires_at = int(time.time()) + ttl
    payload = f"{project_id}:{expires_at}".encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{body}.{_sign(payload)}", ttl


def verify(token: str) -> tuple[str, int] | None:
    """Return (project_id, expires_at), or None for anything not verifiable."""
    if not token or "." not in token:
        return None
    body, _, signature = token.rpartition(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        project_id, _, expires_at = payload.decode("utf-8").rpartition(":")
        expiry = int(expires_at)
    except (ValueError, UnicodeDecodeError):
        return None

    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    if expiry < int(time.time()):
        return None
    if not project_id:
        return None

    return project_id, expiry
