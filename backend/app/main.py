"""JunoGuard gateway.

Implements docs/api-contract.md. Three sessions build against that contract in
parallel, so treat it as frozen.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config, pricing, provider, risk
from .store import store

app = FastAPI(title="JunoGuard API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- auth -------------------------------------------------------------------


def current_project(x_juno_key: str = Header(default="")) -> dict[str, Any]:
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

    if verdict.incident:
        store.record_incident(
            {
                "project_id": project["id"],
                "action_id": action_id,
                "status": "open",
                **verdict.incident,
            }
        )

    if verdict.suspend:
        store.set_status(project["id"], "suspended", verdict.reason)

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

    return _envelope(action_id, verdict, status) | {
        "verdict": verdict.metadata.get("verdict"),
        "blast_radius": verdict.metadata.get("blast_radius"),
    }


@app.post("/v1/guard/llm")
def guard_llm(
    payload: LLMRequest, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """Lane B. Proxied model call, evaluated before the key is ever used."""
    policy = store.get_policy(project["id"])
    spend_today = store.daily_spend_usd(project["id"])

    if project["status"] == "suspended":
        verdict = risk.SUSPENDED
    else:
        verdict = risk.evaluate_llm(
            payload.prompt,
            payload.model,
            payload.max_output_tokens,
            policy,
            spend_today,
            store.requests_last_min(project["id"]),
        )

    answer: str | None = None
    tokens_in = int(verdict.metadata.get("tokens_in") or 0)
    tokens_out = 0
    cost = 0.0

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

    return _envelope(action_id, verdict, project["status"]) | {
        "answer": answer,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "spend_today_usd": round(spend_today + cost, 6),
        "daily_budget_usd": policy["daily_budget_usd"],
    }


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
    payload: SuspendRequest, project: dict[str, Any] = Depends(current_project)
) -> dict[str, Any]:
    """The kill switch. Both lanes go dark until this is manually reversed."""
    return store.set_status(project["id"], "suspended", payload.reason)


@app.post("/v1/projects/resume")
def resume(project: dict[str, Any] = Depends(current_project)) -> dict[str, Any]:
    return store.set_status(project["id"], "active", None)
