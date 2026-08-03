"""JunoGuard gateway.

Implements docs/api-contract.md. Three sessions build against that contract in
parallel, so treat it as frozen.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any, AsyncIterator, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import auth, config, demo, detonation, events, pricing, provider, risk, tokens
from . import store as store_module
from .store import public_project, store

app = FastAPI(title="JunoGuard API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    # A deployed frontend origin has to be named in ALLOWED_ORIGINS. Localhost
    # stays matched by pattern for development — Vite silently moves to 5174+
    # when the default is taken, and a CORS rejection there is invisible in the
    # UI — but that pattern is off by default in production.
    allow_origins=config.ALLOWED_ORIGINS,
    allow_origin_regex=(
        r"http://(localhost|127\.0\.0\.1)(:\d+)?" if config.ALLOW_LOCALHOST_ORIGINS else None
    ),
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
    # Authentication is checked before anything about the request's shape.
    # Otherwise a caller with no operator credential gets told which field they
    # forgot, which is both a worse answer and a more informative one than an
    # unauthenticated caller has earned.
    if not (authorization or operator_token):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "operator_identity_required",
                "detail": "Human control actions need a signed-in operator. An "
                "agent key is not accepted here.",
            },
        )

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


CredentialName = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
]


class AgentScope(BaseModel):
    """Names and capabilities declared by the calling agent; never secret values."""

    credential_names: list[CredentialName] = Field(default_factory=list, max_length=200)
    workspace_access: Literal["read_only", "read_write", "unknown"] = "unknown"
    repository: bool | None = None


class InstallRequest(BaseModel):
    package: str = Field(min_length=1, max_length=214)
    ecosystem: Literal["npm", "pypi"] = "npm"
    version: str | None = None
    agent_scope: AgentScope | None = None


class UnscannedRequest(BaseModel):
    """An operator's authorization for an install that cannot be scanned."""

    sources: list[str] = Field(min_length=1, max_length=50)
    ecosystem: Literal["npm", "pypi"] = "npm"
    manager: str = Field(default="npm", max_length=32)
    # Long enough to be an explanation rather than a keystroke to get past a
    # prompt. "yes" is not a reason.
    reason: str = Field(min_length=8, max_length=500)
    operator: str = Field(min_length=1, max_length=120)


class LLMRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=200_000)
    # Defaults to whatever this deployment is actually pointed at. A hardcoded
    # `gpt-4o` was a silent bet that the provider is OpenAI: against a Workers AI
    # base URL every unqualified call 404s on a model that host has never heard
    # of. A client may still name any model the provider accepts.
    model: str = config.PROVIDER_MODEL
    max_output_tokens: int = Field(default=300, ge=1, le=32_000)


class SuspendRequest(BaseModel):
    reason: str = "Manual suspend from dashboard"
    # Which project to act on. Optional only where the deployment holds exactly
    # one — a local memory-store run.
    project_id: str | None = None


class ResumeRequest(BaseModel):
    project_id: str | None = None
    # Required when the project is carrying an open high or critical incident:
    # bringing a project back after a malware block is a decision that should
    # have a sentence attached to it.
    reason: str | None = None
    # The incident the operator is attesting to have reviewed. An operator
    # (rather than an owner) may only resume by naming one.
    incident_id: str | None = None


# --- helpers ----------------------------------------------------------------


def _persist(
    project: dict[str, Any], verdict: risk.Verdict, *, publish: bool = True, **row: Any
) -> str:
    """Record the decision, then any incident it raised, then any suspension.

    Order matters: the incident references the action, and the dashboard's
    Realtime feed should show the action land before the project goes dark.

    `publish=False` records the row without announcing it, for an action whose
    outcome is not known yet — a model call about to be attempted. The event is
    published by _finalize once there is something true to say about it.
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

    if publish:
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


def _finalize(
    project: dict[str, Any],
    action_id: str,
    verdict: risk.Verdict,
    fields: dict[str, Any],
) -> None:
    """Settle a recorded attempt, and only now announce it.

    Updates the existing row rather than writing a second one, so an attempted
    provider call leaves exactly one durable audit record whatever happens to it.
    """
    store.update_action(action_id, fields)
    events.publish(
        "action",
        project["id"],
        {
            "id": action_id,
            "decision": verdict.decision,
            "reason": verdict.reason,
            "risk_level": verdict.risk_level,
            **fields,
        },
    )


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
    """Liveness. Says what is real, so nobody has to guess from the outside."""
    return {
        "status": "ok",
        "service": "JunoGuard",
        "mode": config.mode(),
        "environment": config.JUNO_ENV,
        "store": "supabase" if isinstance(store, store_module.SupabaseStore) else "memory",
        "scanner": "ossprey" if config.USE_OSSPREY else "mock",
        "sbom": "registry",
        "sandbox": "docker" if config.SANDBOX_ENABLED else "disabled",
        "blast_radius": "client_declared",
        "provider": "mock" if config.MOCK_PROVIDER or not config.PROVIDER_API_KEY else "live",
    }


@app.get("/ready")
def ready(response: Response) -> dict[str, Any]:
    """Readiness. In production, degraded infrastructure is not ready.

    The gateway is deliberately able to boot with nothing configured — that is
    what makes the demo survive a missing credential. The same property in
    production would mean serving policy decisions from a store that dies with
    the process, and reporting 200 while doing it.
    """
    problems: list[str] = []

    if config.IS_PRODUCTION:
        if not isinstance(store, store_module.SupabaseStore):
            problems.append(
                "persistence is the in-memory store: decisions, incidents and "
                "control history would not survive a restart"
            )
        if not config.USE_OSSPREY:
            problems.append("no Ossprey credentials: package verdicts would be mock fixtures")
        if not config.ALLOWED_ORIGINS:
            problems.append("ALLOWED_ORIGINS is empty: no browser origin can reach this gateway")
        if not config.STREAM_TOKEN_SECRET:
            problems.append(
                "STREAM_TOKEN_SECRET is unset: event-stream tokens would not survive a "
                "restart or work across replicas"
            )
        if not (config.OPERATOR_TOKEN or config.USE_SUPABASE):
            problems.append("no operator identity is possible: the kill switch is unusable")

    if problems:
        response.status_code = 503
        return {"status": "degraded", "problems": problems}

    return {"status": "ready", "environment": config.JUNO_ENV}


def _maybe_detonate(
    background: BackgroundTasks,
    project: dict[str, Any],
    action_id: str,
    verdict: risk.Verdict,
    package: str,
    ecosystem: str,
    version: str | None,
) -> None:
    """Queue cold-path detonation, after the decision and after the response.

    A background task rather than an inline call: the agent has already been
    told what happens to its install, and nothing about that answer may depend
    on a sandbox that takes two minutes.
    """
    if not detonation.should_detonate("package_install", verdict.decision, verdict.metadata):
        return
    background.add_task(
        detonation.request_detonation,
        action_id=action_id,
        project_id=project["id"],
        package=package,
        ecosystem=ecosystem,
        version=version,
    )


@app.post("/v1/guard/install")
def guard_install(
    payload: InstallRequest,
    background: BackgroundTasks,
    project: dict[str, Any] = Depends(current_project),
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
            agent_scope=payload.agent_scope.model_dump() if payload.agent_scope else None,
        )

    action_id = _persist(
        project,
        verdict,
        action_type="package_install",
        target=payload.package,
    )

    _maybe_detonate(
        background, project, action_id, verdict,
        payload.package, payload.ecosystem, payload.version,
    )

    # Re-read: a malicious verdict may have just suspended the project.
    status = "suspended" if verdict.suspend else project["status"]

    body = _envelope(action_id, verdict, status) | {
        "verdict": verdict.metadata.get("verdict"),
        "sbom": verdict.metadata.get("sbom"),
        "sandbox": verdict.metadata.get("sandbox"),
        "blast_radius": verdict.metadata.get("blast_radius"),
    }

    # A refusal the agent should retry rather than route around says so
    # structurally, not only in prose it might not parse.
    if verdict.metadata.get("review_required"):
        body["review_required"] = True
        body["retry_after_seconds"] = verdict.metadata.get("retry_after_seconds")

    return body


@app.post("/v1/guard/unscanned")
def guard_unscanned(
    payload: UnscannedRequest, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """Record an operator override for an install that could not be scanned.

    Clients refuse unscannable sources on their own — they have to, since this
    gateway may be down. This endpoint exists so that the exception a human makes
    is auditable: if the override cannot be recorded here, the client refuses
    rather than proceeding unlogged.
    """
    if project["status"] == "suspended":
        verdict = risk.SUSPENDED
    else:
        verdict = risk.unscanned_override(
            payload.sources, payload.reason, payload.operator, payload.manager
        )

    action_id = _persist(
        project,
        verdict,
        action_type="package_install",
        target=", ".join(payload.sources)[:200],
    )
    status = "suspended" if project["status"] == "suspended" else "active"
    return _envelope(action_id, verdict, status)


@app.post("/v1/detonations/{action_id}")
async def detonation_report(
    action_id: str, request: Request, authorization: str = Header(default="")
) -> dict[str, Any]:
    """Receive a sandbox report and attach it to the action it belongs to.

    Everything about this endpoint assumes the caller is hostile. The report was
    assembled in a container where a package's install script had just run, so
    it is bearer-authenticated, size-capped, and reduced to known fields with
    known types before it reaches the audit trail. A package that wants to write
    its own incident evidence gets a truncated string in a fixed schema instead.
    """
    if not detonation.callback_authorized(authorization):
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_callback_token", "detail": "Not a known detonation worker."},
        )

    body = await request.json()
    try:
        report = detonation.validate_report(body.get("report"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error": "invalid_report", "detail": str(exc)}
        ) from exc

    action = store.get_action(action_id)
    if not action:
        raise HTTPException(
            status_code=404, detail={"error": "unknown_action", "detail": "No such action."}
        )

    metadata = dict(action.get("metadata") or {})
    metadata["detonation"] = report
    store.update_action(action_id, {"metadata": metadata})

    # An incident raised for this action gets the evidence too — that is where a
    # reviewer looks, and inferred blast radius is exactly what this replaces.
    if report.get("severity") in {"high", "critical"} or action.get("decision") != "allow":
        store.update_incident_for_action(action_id, {"evidence": metadata})

    events.publish(
        "detonation",
        action["project_id"],
        {"action_id": action_id, **report},
    )
    return {"status": "recorded", "action_id": action_id, "severity": report.get("severity")}


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

    tokens_in = int(verdict.metadata.get("tokens_in") or 0)

    # Blocked: nothing is attempted, so the record is complete the moment it is
    # written.
    if verdict.decision == "block":
        if reservation is not None:
            store.release(reservation.reservation_id)
        action_id = _persist(
            project,
            verdict,
            action_type="llm_call",
            target=payload.model,
            tokens_in=tokens_in,
            tokens_out=0,
            cost_usd=0.0,
        )
        return _envelope(action_id, verdict, project["status"]) | {
            "answer": None,
            "tokens_in": tokens_in,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "spend_today_usd": round(spend_today, 6),
            "daily_budget_usd": policy["daily_budget_usd"],
        }

    # Proceeding: write the attempt down *before* calling the provider. If the
    # provider raises or times out, the attempt is still on the record — the old
    # code only recorded successes, so a provider outage left no trace of the
    # call, the possible charge, or the decision that allowed it.
    action_id = _persist(
        project,
        verdict,
        publish=False,
        action_type="llm_call",
        target=payload.model,
        tokens_in=tokens_in,
        tokens_out=0,
        # Reserved rather than spent. Replaced by the real figure on success, and
        # kept as a conservative estimate if the charge is unknowable.
        cost_usd=0.0,
        metadata=verdict.metadata | {"provider_status": "attempted"},
    )

    try:
        result = provider.complete(payload.prompt, payload.model, payload.max_output_tokens)
    except Exception as exc:  # noqa: BLE001 - every failure must be recorded
        status, charged = provider.classify_failure(exc)
        # An ambiguous failure is charged at the estimate: the provider may well
        # have billed for work we never saw, and understating spend is the
        # dangerous direction for a budget cap.
        cost = est_cost if charged else 0.0
        _finalize(
            project,
            action_id,
            verdict,
            {
                "cost_usd": cost,
                "metadata": verdict.metadata
                | {
                    "provider_status": status,
                    "provider_error": str(exc)[:500],
                    "cost_is_estimate": charged,
                },
            },
        )
        if reservation is not None:
            store.release(reservation.reservation_id)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "provider_unavailable",
                "detail": f"The model provider did not complete this request: {exc}",
                # The audit row and the client's error name the same thing.
                "correlation_id": action_id,
                "action_id": action_id,
                "charge_status": status,
            },
        ) from exc

    answer = result["answer"]
    tokens_in = result["tokens_in"]
    tokens_out = result["tokens_out"]
    cost = pricing.cost_usd(payload.model, tokens_in, tokens_out)

    _finalize(
        project,
        action_id,
        verdict,
        {
            "action_type": "llm_call",
            "target": payload.model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost,
            "metadata": verdict.metadata | {"provider_status": "succeeded"},
        },
    )

    # Released only after the charge is on the record, so it is never invisible
    # to a concurrent request. Briefly counting both is the safe direction.
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
    previous = project["status"]
    updated = store.set_status(project["id"], "suspended", payload.reason)
    store.record_control_event(
        {
            "project_id": project["id"],
            "action": "suspend",
            "previous_status": previous,
            "next_status": "suspended",
            "reason": payload.reason,
            **actor.audit(),
        }
    )
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
    """Bringing a project back is the higher bar of the two.

    Stopping something should be easy and reversing it should be deliberate. An
    owner may resume outright. An operator may only resume by naming the incident
    they reviewed — which is what makes them a reviewed operator rather than
    someone who found the button.
    """
    reviewed = bool(payload.reason and payload.incident_id)
    minimum = "operator" if reviewed else "owner"
    project, actor = controlled_project(
        payload.project_id, authorization, x_juno_operator, minimum, "Resuming a project"
    )
    if not reviewed and not actor.can("owner"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "review_required",
                "detail": "An operator may resume only with a reason and the "
                "incident_id they reviewed. An owner may resume outright.",
            },
        )

    # A project carrying an open high or critical incident does not come back
    # without a sentence explaining why it should.
    blocking = store.open_critical_incidents(project["id"])
    if blocking and not (payload.reason and len(payload.reason.strip()) >= 8):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "reason_required",
                "detail": (
                    f"This project has {len(blocking)} open high or critical "
                    f"incident(s). Resuming requires a reason of at least 8 "
                    f"characters."
                ),
                "open_incidents": blocking[:5],
            },
        )

    previous = project["status"]
    updated = store.set_status(project["id"], "active", None)
    store.record_control_event(
        {
            "project_id": project["id"],
            "action": "resume",
            "previous_status": previous,
            "next_status": "active",
            "reason": payload.reason,
            "incident_id": payload.incident_id,
            **actor.audit(),
        }
    )
    events.publish(
        "project",
        project["id"],
        {"status": "active", "reason": payload.reason} | actor.audit(),
    )
    return public_project(updated) | {"actor": actor.audit()}


@app.get("/v1/projects/control-events")
def control_events(
    project_id: str | None = None,
    limit: int = 20,
    authorization: str = Header(default=""),
    x_juno_operator: str = Header(default=""),
) -> dict[str, Any]:
    """Who changed this project's state, when, why, and after reviewing what."""
    project, _ = controlled_project(
        project_id, authorization, x_juno_operator, "viewer", "Reading control history"
    )
    return {"events": store.recent_control_events(project["id"], limit)}


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
