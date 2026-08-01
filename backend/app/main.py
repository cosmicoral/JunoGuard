"""JunoGuard gateway.

Implements docs/api-contract.md. Three sessions build against that contract in
parallel, so treat it as frozen.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import auth, config, demo, events, pricing, provider, risk, tokens
from . import store as store_module
from .store import public_project, store

app = FastAPI(title="JunoGuard API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    # Any localhost port, not just 5173. Vite silently moves to 5174+ when the
    # default is taken, and a CORS rejection there is invisible in the UI — it
    # just renders an empty dashboard, which is the one thing the demo cannot do.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- auth -------------------------------------------------------------------


def current_project(x_juno_key: str = Header(default="")) -> dict[str, Any]:
    """Agent authentication. Guarded lanes only — never the control plane."""
    project = store.get_project(x_juno_key) if x_juno_key else None
    if not project:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_project_key",
                "detail": "No project matches that key.",
            },
        )
    return project


def controlled_project(
    project_id: str | None,
    authorization: str,
    operator_token: str,
    minimum_role: str,
    action: str,
) -> tuple[dict[str, Any], auth.Actor]:
    """Resolve a human-control request to (project, accountable actor).

    Deliberately takes no agent key. Suspend and resume are human decisions, and
    a credential that lives in agent configs and CI environments is not a person.
    """
    target = project_id or store.sole_project_id()
    if not target:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "project_id_required",
                "detail": "Name the project to act on.",
            },
        )

    try:
        actor = auth.resolve_actor(target, authorization, operator_token)
        auth.require(actor, minimum_role, action)
    except auth.AuthError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"error": exc.error, "detail": exc.detail},
        ) from exc

    project = store.get_project_by_id(target)
    if not project:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_project", "detail": "No such project."},
        )
    return project, actor


# --- schemas ----------------------------------------------------------------


class InstallRequest(BaseModel):
    package: str = Field(min_length=1, max_length=214)
    ecosystem: Literal["npm", "pypi"] = "npm"
    version: str | None = None


class LLMRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=200_000)
    model: str = "gpt-4o"
    max_output_tokens: int = Field(default=300, ge=1, le=32_000)


class SuspendRequest(BaseModel):
    reason: str = "Manual suspend from dashboard"
    # Which project to act on. Optional only where the deployment holds exactly
    # one — a local memory-store run.
    project_id: str | None = None


class ResumeRequest(BaseModel):
    project_id: str | None = None


# --- helpers ----------------------------------------------------------------


def _persist(project: dict[str, Any], verdict: risk.Verdict, **row: Any) -> str:
    """Record the decision, then any incident it raised, then any suspension.

    Order matters: the incident references the action, and the dashboard's
    Realtime feed should show the action land before the project goes dark.
    """
    action_id = store.record_action(
        {
            "project_id": project["id"],
            "decision": verdict.decision,
            "reason": verdict.reason,
            "risk_level": verdict.risk_level,
            "metadata": verdict.metadata,
            **row,
        }
    )

    events.publish(
        "action",
        project["id"],
        {
            "id": action_id,
            "decision": verdict.decision,
            "reason": verdict.reason,
            "risk_level": verdict.risk_level,
            "metadata": verdict.metadata,
            **row,
        },
    )

    if verdict.incident:
        store.record_incident(
            {
                "project_id": project["id"],
                "action_id": action_id,
                "status": "open",
                **verdict.incident,
            }
        )
        events.publish(
            "incident", project["id"], {"action_id": action_id, **verdict.incident}
        )

    if verdict.suspend:
        store.set_status(project["id"], "suspended", verdict.reason)
        events.publish(
            "project", project["id"], {"status": "suspended", "reason": verdict.reason}
        )

    return action_id


def _envelope(action_id: str, verdict: risk.Verdict, status: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "decision": verdict.decision,
        "reason": verdict.reason,
        "risk_level": verdict.risk_level,
        "project_status": status,
    }


# --- routes -----------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "JunoGuard", "mode": config.mode()}


@app.post("/v1/guard/install")
def guard_install(
    payload: InstallRequest, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """Lane A. Called before a package reaches disk."""
    if project["status"] == "suspended":
        verdict = risk.SUSPENDED
    else:
        verdict = risk.evaluate_install(
            payload.package,
            payload.ecosystem,
            payload.version,
            store.get_policy(project["id"]),
        )

    action_id = _persist(
        project,
        verdict,
        action_type="package_install",
        target=payload.package,
    )

    # Re-read: a malicious verdict may have just suspended the project.
    status = "suspended" if verdict.suspend else project["status"]

    body = _envelope(action_id, verdict, status) | {
        "verdict": verdict.metadata.get("verdict"),
        "blast_radius": verdict.metadata.get("blast_radius"),
    }

    # A refusal the agent should retry rather than route around says so
    # structurally, not only in prose it might not parse.
    if verdict.metadata.get("review_required"):
        body["review_required"] = True
        body["retry_after_seconds"] = verdict.metadata.get("retry_after_seconds")

    return body


@app.post("/v1/guard/llm")
def guard_llm(
    payload: LLMRequest,
    project: dict[str, Any] = Depends(current_project),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Lane B. Proxied model call, evaluated before the key is ever used.

    The rate and budget checks happen inside a single atomic reservation rather
    than as a read-then-act pair, so concurrent requests are bounded by the
    policy. The reservation counts toward both limits until it is released,
    which is what stops twenty simultaneous calls sharing one slot.
    """
    if idempotency_key:
        replay = store.lookup_idempotent(project["id"], idempotency_key)
        if replay is not None:
            # A retry must never buy a second completion.
            return replay | {"idempotent_replay": True}

    policy = store.get_policy(project["id"])
    base, tokens_in_est, est_cost = risk.estimate(
        payload.prompt, payload.model, payload.max_output_tokens
    )

    reservation: store_module.Reservation | None = None
    spend_today = 0.0

    if project["status"] == "suspended":
        verdict = risk.SUSPENDED
    else:
        # Local limits first: no point reserving a slot for a request that can
        # never be allowed no matter what the shared counters say.
        verdict = risk.check_request_limits(base, tokens_in_est, est_cost, policy)
        if verdict is None:
            reservation = store.reserve(
                project["id"],
                est_cost,
                policy["daily_budget_usd"],
                policy["max_requests_per_min"],
            )
            spend_today = reservation.spend_today
            if reservation.outcome == "rate_exceeded":
                verdict = risk.rate_exceeded(base, reservation.requests_last_min, policy)
            elif reservation.outcome == "budget_exceeded":
                verdict = risk.budget_exceeded(base, spend_today, est_cost, policy)
            else:
                verdict = risk.within_limits(base, spend_today, est_cost, policy)

    answer: str | None = None
    tokens_in = int(verdict.metadata.get("tokens_in") or 0)
    tokens_out = 0
    cost = 0.0

    try:
        if verdict.decision != "block":
            # The provider is called exactly once, and only after the decision.
            result = provider.complete(
                payload.prompt, payload.model, payload.max_output_tokens
            )
            answer = result["answer"]
            tokens_in = result["tokens_in"]
            tokens_out = result["tokens_out"]
            cost = pricing.cost_usd(payload.model, tokens_in, tokens_out)

        action_id = _persist(
            project,
            verdict,
            action_type="llm_call",
            target=payload.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
    finally:
        # Released only after the action row exists, so the charge is never
        # invisible to a concurrent request. Briefly counting both is the safe
        # direction to be wrong in.
        if reservation is not None:
            store.release(reservation.reservation_id)

    response = _envelope(action_id, verdict, project["status"]) | {
        "answer": answer,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "spend_today_usd": round(spend_today + cost, 6),
        "daily_budget_usd": policy["daily_budget_usd"],
    }

    if idempotency_key:
        store.remember_idempotent(project["id"], idempotency_key, response)

    return response


@app.get("/v1/guard/status")
def guard_status(project: dict[str, Any] = Depends(current_project)) -> dict[str, Any]:
    """Cheap enough to poll. Lets the agent check its budget before acting."""
    policy = store.get_policy(project["id"])
    spend = store.daily_spend_usd(project["id"])
    return {
        "project": project["name"],
        "status": project["status"],
        "spend_today_usd": round(spend, 6),
        "daily_budget_usd": policy["daily_budget_usd"],
        "remaining_usd": round(max(0.0, policy["daily_budget_usd"] - spend), 6),
        "requests_last_min": store.requests_last_min(project["id"]),
        "max_requests_per_min": policy["max_requests_per_min"],
        "blocked_today": store.blocked_today(project["id"]),
        "open_incidents": store.open_incidents(project["id"]),
    }


@app.post("/v1/projects/suspend")
def suspend(
    payload: SuspendRequest,
    authorization: str = Header(default=""),
    x_juno_operator: str = Header(default=""),
) -> dict[str, Any]:
    """The kill switch. Both lanes go dark until a human reverses it.

    Operator or owner. An agent key gets 401 here no matter how valid it is.
    """
    project, actor = controlled_project(
        payload.project_id, authorization, x_juno_operator, "operator", "Suspending a project"
    )
    updated = store.set_status(project["id"], "suspended", payload.reason)
    events.publish(
        "project",
        project["id"],
        {"status": "suspended", "reason": payload.reason} | actor.audit(),
    )
    # The persistence row carries the agent key hash. Responses carry the
    # public view of a project and nothing else.
    return public_project(updated) | {"actor": actor.audit()}


@app.post("/v1/projects/resume")
def resume(
    payload: ResumeRequest = ResumeRequest(),
    authorization: str = Header(default=""),
    x_juno_operator: str = Header(default=""),
) -> dict[str, Any]:
    """Bringing a project back is the higher bar of the two: owner only.

    Stopping something should be easy and reversing it should be deliberate.
    """
    project, actor = controlled_project(
        payload.project_id, authorization, x_juno_operator, "owner", "Resuming a project"
    )
    updated = store.set_status(project["id"], "active", None)
    events.publish(
        "project", project["id"], {"status": "active", "reason": None} | actor.audit()
    )
    return public_project(updated) | {"actor": actor.audit()}


# --- live feed --------------------------------------------------------------


@app.post("/v1/demo/seed")
def demo_seed(
    count: int = 28, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """Backfill plausible history. Demo tooling — backdated, policy not applied."""
    return {"seeded": demo.seed(project, count=count)}


@app.post("/v1/events/token")
def events_token(project: dict[str, Any] = Depends(current_project)) -> dict[str, Any]:
    """Mint a short-lived token for one project's event stream.

    EventSource cannot send headers, and a project key does not belong in a URL:
    it is long-lived, it authorizes both guarded lanes, and query strings end up
    in logs and history. This token reads one project's feed and nothing else.
    """
    token, ttl = tokens.issue(project["id"])
    return {"token": token, "expires_in": ttl}


@app.get("/v1/events/recent")
def recent_events(
    limit: int = 50, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """Backfill, so the dashboard is never empty on load. Caller's project only."""
    return {
        "cursor": events.latest_seq(),
        "events": events.recent(limit, project["id"]),
    }


@app.get("/v1/events/stream")
async def stream_events(cursor: int = 0, token: str = "") -> StreamingResponse:
    """Server-sent events for one project.

    The dashboard's fallback when Supabase Realtime is not configured. Pass the
    cursor from /v1/events/recent to resume without gaps, and a token from
    /v1/events/token to prove which project you may read.
    """
    verified = tokens.verify(token)
    if not verified:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_stream_token",
                "detail": "Get a token from POST /v1/events/token.",
            },
        )
    project_id, expires_at = verified

    async def generate() -> AsyncIterator[str]:
        last = cursor
        idle = 0
        while True:
            # The token authorizes a window, not a permanent subscription. The
            # client re-issues and reconnects.
            if time.time() >= expires_at:
                yield "event: expired\ndata: {}\n\n"
                return

            for event in events.since(last, project_id):
                last = event["seq"]
                idle = 0
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

            await asyncio.sleep(0.25)
            idle += 1

            # Keep proxies and browsers from closing an idle connection.
            if idle >= 60:
                idle = 0
                yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
