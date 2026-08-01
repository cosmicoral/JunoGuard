"""Persistence.

Two backends behind one interface: Supabase when credentials are present,
in-memory otherwise. The gateway boots and the demo runs either way.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from dataclasses import dataclass
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


# --- reservations -----------------------------------------------------------
#
# A reservation is a claim on rate and budget taken *before* the provider is
# called, and counted toward both limits until it is released. It is what makes
# concurrent requests bounded by policy rather than by timing.

# An abandoned reservation must not hold budget forever.
RESERVATION_TTL = timedelta(minutes=2)


@dataclass
class Reservation:
    """The atomic answer to 'may this request proceed, and at what cost?'."""

    outcome: str  # "ok" | "rate_exceeded" | "budget_exceeded"
    spend_today: float
    requests_last_min: int
    reservation_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


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
        # Held for the whole of reserve(), so this backend enforces limits with
        # the same semantics as the SQL advisory lock rather than only looking
        # like it does under a single-threaded demo.
        self._reserve_lock = threading.Lock()
        self.reservations: dict[str, dict[str, Any]] = {}
        self._idempotent: dict[tuple[str, str], dict[str, Any]] = {}

    # --- projects -----------------------------------------------------------

    def get_project(self, api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None
        matched = hmac.compare_digest(key_hash(api_key), self.project["api_key_hash"])
        return self.project if matched else None

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        return self.project if project_id == self.project["id"] else None

    def sole_project_id(self) -> str | None:
        """This backend holds exactly one project, so control actions may omit it."""
        return str(self.project["id"])

    def get_member_role(self, project_id: str, user_id: str) -> str | None:
        # No membership table in memory: this backend exists for local runs,
        # where the operator token is the way in.
        return None

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
        """Every charged action, whatever it was labelled.

        `flag` is a proceedable decision — the provider is called and the money
        is spent. Totalling only `allow` rows meant that once the 80% warning
        threshold flipped decisions to `flag`, real charges stopped advancing
        the daily total and the cap could be walked straight past.
        """
        midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(
            a.get("cost_usd") or 0.0
            for a in self.actions
            if (a.get("cost_usd") or 0.0) > 0
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

    # --- reservations -------------------------------------------------------

    def _open_reservations(self, project_id: str) -> list[dict[str, Any]]:
        cutoff = _now() - RESERVATION_TTL
        return [
            r
            for r in self.reservations.values()
            if r["project_id"] == project_id and r["created_at"] >= cutoff
        ]

    def reserve(
        self,
        project_id: str,
        est_cost: float,
        daily_budget_usd: float,
        max_requests_per_min: int,
    ) -> Reservation:
        with self._reserve_lock:
            # Drop anything a crashed request left behind.
            for res_id in [
                r_id
                for r_id, r in self.reservations.items()
                if r["created_at"] < _now() - RESERVATION_TTL
            ]:
                del self.reservations[res_id]

            open_reservations = self._open_reservations(project_id)
            spend = self.daily_spend_usd(project_id) + sum(
                r["est_cost"] for r in open_reservations
            )

            minute_ago = _now() - timedelta(minutes=1)
            rate = self.requests_last_min(project_id) + sum(
                1 for r in open_reservations if r["created_at"] >= minute_ago
            )

            if rate >= max_requests_per_min:
                return Reservation("rate_exceeded", spend, rate)

            if spend + est_cost > daily_budget_usd:
                return Reservation("budget_exceeded", spend, rate)

            res_id = str(uuid.uuid4())
            self.reservations[res_id] = {
                "project_id": project_id,
                "est_cost": est_cost,
                "created_at": _now(),
            }
            return Reservation("ok", spend, rate, res_id)

    def release(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        with self._reserve_lock:
            self.reservations.pop(reservation_id, None)

    # --- idempotency --------------------------------------------------------

    def lookup_idempotent(self, project_id: str, key: str) -> dict[str, Any] | None:
        return self._idempotent.get((project_id, key))

    def remember_idempotent(
        self, project_id: str, key: str, response: dict[str, Any]
    ) -> None:
        with self._lock:
            self._idempotent[(project_id, key)] = response

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

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        rows = self._get(
            "/projects", id=f"eq.{project_id}", select=PROJECT_SELECT, limit=1
        )
        return rows[0] if rows else None

    def sole_project_id(self) -> str | None:
        """A real deployment holds many projects; the caller must name one."""
        return None

    def get_member_role(self, project_id: str, user_id: str) -> str | None:
        rows = self._get(
            "/project_members",
            project_id=f"eq.{project_id}",
            user_id=f"eq.{user_id}",
            select="role",
            limit=1,
        )
        return rows[0]["role"] if rows else None

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

    # --- reservations -------------------------------------------------------

    def reserve(
        self,
        project_id: str,
        est_cost: float,
        daily_budget_usd: float,
        max_requests_per_min: int,
    ) -> Reservation:
        """One round trip, one transaction, one advisory lock. See
        supabase/migrations/202608010003_atomic_spend_reservations.sql."""
        r = self._client.post(
            "/rpc/reserve_action",
            json={
                "p_project_id": project_id,
                "p_est_cost": est_cost,
                "p_daily_budget": daily_budget_usd,
                "p_max_per_min": max_requests_per_min,
            },
        )
        r.raise_for_status()
        body = r.json() or {}
        return Reservation(
            outcome=str(body.get("outcome", "ok")),
            spend_today=float(body.get("spend_today") or 0.0),
            requests_last_min=int(body.get("requests_last_min") or 0),
            reservation_id=body.get("reservation_id"),
        )

    def release(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        r = self._client.post("/rpc/release_reservation", json={"p_id": reservation_id})
        r.raise_for_status()

    # --- idempotency --------------------------------------------------------

    def lookup_idempotent(self, project_id: str, key: str) -> dict[str, Any] | None:
        rows = self._get(
            "/idempotency_keys",
            project_id=f"eq.{project_id}",
            key=f"eq.{key}",
            select="response",
            limit=1,
        )
        return rows[0]["response"] if rows else None

    def remember_idempotent(
        self, project_id: str, key: str, response: dict[str, Any]
    ) -> None:
        r = self._client.post(
            "/idempotency_keys",
            json={"project_id": project_id, "key": key, "response": response},
            headers={"Prefer": "resolution=ignore-duplicates"},
        )
        r.raise_for_status()


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
