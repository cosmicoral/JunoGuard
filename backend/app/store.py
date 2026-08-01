"""Persistence.

Two backends behind one interface: Supabase when credentials are present,
in-memory otherwise. The gateway boots and the demo runs either way.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from . import config


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --- agent keys -------------------------------------------------------------
#
# The key itself is never stored, and never leaves the client that holds it.
# Lookups hash the presented key and match on the hash, so a database dump
# cannot be replayed against the gateway.


def key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def key_prefix(api_key: str) -> str:
    """Enough to identify which key is in use, not enough to use it."""
    return api_key.strip()[:12]


# Columns any caller may see. Deliberately excludes api_key_hash: a hash is
# still a credential-shaped secret, and nothing outside the store needs it.
PUBLIC_PROJECT_FIELDS = (
    "id",
    "name",
    "status",
    "suspended_at",
    "suspended_reason",
    "api_key_prefix",
)

PROJECT_SELECT = ",".join(PUBLIC_PROJECT_FIELDS)


def public_project(project: dict[str, Any]) -> dict[str, Any]:
    """The project as an API response is allowed to describe it."""
    return {field: project.get(field) for field in PUBLIC_PROJECT_FIELDS}


class MemoryStore:
    """Fallback store. Everything lives in one process and dies with it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.project = {
            "id": str(uuid.uuid4()),
            "name": "Demo Project",
            "api_key_hash": key_hash(config.DEMO_PROJECT_KEY),
            "api_key_prefix": key_prefix(config.DEMO_PROJECT_KEY),
            "status": "active",
            "suspended_at": None,
            "suspended_reason": None,
        }
        self.policy = dict(config.DEFAULT_POLICY)
        self.actions: list[dict[str, Any]] = []
        self.incidents: list[dict[str, Any]] = []

    # --- projects -----------------------------------------------------------

    def get_project(self, api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None
        matched = hmac.compare_digest(key_hash(api_key), self.project["api_key_hash"])
        return self.project if matched else None

    def get_policy(self, project_id: str) -> dict[str, Any]:
        return self.policy

    def set_status(self, project_id: str, status: str, reason: str | None) -> dict[str, Any]:
        with self._lock:
            self.project["status"] = status
            self.project["suspended_reason"] = reason
            self.project["suspended_at"] = _iso(_now()) if status == "suspended" else None
        return self.project

    # --- actions ------------------------------------------------------------

    def record_action(self, action: dict[str, Any]) -> str:
        action_id = str(uuid.uuid4())
        with self._lock:
            # A caller may backdate a row (demo seeding); otherwise stamp now.
            self.actions.append(
                {"created_at": _iso(_now()), **action, "id": action_id}
            )
        return action_id

    def daily_spend_usd(self, project_id: str) -> float:
        midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(
            a.get("cost_usd") or 0.0
            for a in self.actions
            if a["decision"] == "allow"
            and datetime.fromisoformat(a["created_at"]) >= midnight
        )

    def requests_last_min(self, project_id: str) -> int:
        cutoff = _now() - timedelta(minutes=1)
        return sum(
            1
            for a in self.actions
            if a["action_type"] != "status_check"
            and datetime.fromisoformat(a["created_at"]) >= cutoff
        )

    def blocked_today(self, project_id: str) -> int:
        midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(
            1
            for a in self.actions
            if a["decision"] == "block"
            and datetime.fromisoformat(a["created_at"]) >= midnight
        )

    # --- incidents ----------------------------------------------------------

    def record_incident(self, incident: dict[str, Any]) -> str:
        incident_id = str(uuid.uuid4())
        with self._lock:
            self.incidents.append(
                {**incident, "id": incident_id, "created_at": _iso(_now())}
            )
        return incident_id

    def open_incidents(self, project_id: str) -> int:
        return sum(1 for i in self.incidents if i["status"] == "open")


class SupabaseStore:
    """PostgREST over HTTP. No SDK — one dependency fewer to go wrong."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=f"{config.SUPABASE_URL}/rest/v1",
            headers={
                "apikey": config.SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
            },
            timeout=8.0,
        )

    def _get(self, path: str, **params: Any) -> list[dict[str, Any]]:
        r = self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    # --- projects -----------------------------------------------------------

    def get_project(self, api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None
        rows = self._get(
            "/projects",
            api_key_hash=f"eq.{key_hash(api_key)}",
            key_revoked_at="is.null",
            select=PROJECT_SELECT,
            limit=1,
        )
        return rows[0] if rows else None

    def get_policy(self, project_id: str) -> dict[str, Any]:
        rows = self._get("/policies", project_id=f"eq.{project_id}", select="*", limit=1)
        if not rows:
            return dict(config.DEFAULT_POLICY)
        row = rows[0]
        return {
            "daily_budget_usd": float(row["daily_budget_usd"]),
            "per_request_budget_usd": float(row["per_request_budget_usd"]),
            "max_request_tokens": int(row["max_request_tokens"]),
            "max_requests_per_min": int(row["max_requests_per_min"]),
            "block_severity": row["block_severity"],
            "suspend_on_malware": bool(row["suspend_on_malware"]),
        }

    def set_status(self, project_id: str, status: str, reason: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status, "suspended_reason": reason}
        payload["suspended_at"] = _iso(_now()) if status == "suspended" else None
        r = self._client.patch(
            "/projects",
            # Ask for the public columns only, so no caller can leak the key
            # hash by forwarding whatever the store handed back.
            params={"id": f"eq.{project_id}", "select": PROJECT_SELECT},
            json=payload,
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return r.json()[0]

    # --- actions ------------------------------------------------------------

    def record_action(self, action: dict[str, Any]) -> str:
        r = self._client.post(
            "/agent_actions", json=action, headers={"Prefer": "return=representation"}
        )
        r.raise_for_status()
        return r.json()[0]["id"]

    def daily_spend_usd(self, project_id: str) -> float:
        r = self._client.post("/rpc/daily_spend_usd", json={"p_project_id": project_id})
        r.raise_for_status()
        return float(r.json() or 0)

    def requests_last_min(self, project_id: str) -> int:
        cutoff = _iso(_now() - timedelta(minutes=1))
        rows = self._get(
            "/agent_actions",
            project_id=f"eq.{project_id}",
            created_at=f"gte.{cutoff}",
            action_type="neq.status_check",
            select="id",
        )
        return len(rows)

    def blocked_today(self, project_id: str) -> int:
        midnight = _iso(_now().replace(hour=0, minute=0, second=0, microsecond=0))
        rows = self._get(
            "/agent_actions",
            project_id=f"eq.{project_id}",
            created_at=f"gte.{midnight}",
            decision="eq.block",
            select="id",
        )
        return len(rows)

    # --- incidents ----------------------------------------------------------

    def record_incident(self, incident: dict[str, Any]) -> str:
        r = self._client.post(
            "/incidents", json=incident, headers={"Prefer": "return=representation"}
        )
        r.raise_for_status()
        return r.json()[0]["id"]

    def open_incidents(self, project_id: str) -> int:
        rows = self._get(
            "/incidents", project_id=f"eq.{project_id}", status="eq.open", select="id"
        )
        return len(rows)


def build_store():
    if not config.USE_SUPABASE:
        return MemoryStore()
    try:
        store = SupabaseStore()
        # Fail fast and loudly here rather than mid-demo.
        store.get_project(config.DEMO_PROJECT_KEY)
        return store
    except Exception as exc:  # noqa: BLE001 - degrading is the point
        print(f"[juno] Supabase unreachable ({exc}); falling back to memory store")
        return MemoryStore()


store = build_store()
