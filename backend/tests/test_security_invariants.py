"""JG-013 — security invariants that must never regress."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import config, events, risk
from app.store import MemoryStore
import app.main as main_mod


def _llm(client: TestClient, headers: dict[str, str], **extra: Any) -> Any:
    body = {"prompt": "hello", "model": "gpt-4o-mini", "max_output_tokens": 16}
    body.update(extra)
    return client.post("/v1/guard/llm", headers=headers, json=body)


def _install(client: TestClient, headers: dict[str, str], package: str = "left-pad") -> Any:
    return client.post(
        "/v1/guard/install",
        headers=headers,
        json={"package": package, "ecosystem": "npm", "version": "1.0.0"},
    )


# --- Scanner outage cannot proceed (JG-004) ---------------------------------


def test_scanner_outage_blocks_install(
    client: TestClient, agent_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.risk.ossprey.scan",
        lambda *a, **k: {
            "available": False,
            "severity": "unavailable",
            "findings": ["scanner unreachable"],
            "package": "left-pad",
            "ecosystem": "npm",
            "version": "1.0.0",
        },
    )
    response = _install(client, agent_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "block"
    assert body["review_required"] is True
    assert body["retry_after_seconds"] == risk.SCANNER_RETRY_AFTER_SECONDS


# --- Charged flags count toward spend (JG-003) ------------------------------


def test_flagged_charges_count_in_daily_spend(memory_store: MemoryStore) -> None:
    now = datetime.now(timezone.utc).isoformat()
    memory_store.actions.extend(
        [
            {
                "id": "a1",
                "decision": "allow",
                "cost_usd": 0.10,
                "action_type": "llm_call",
                "created_at": now,
            },
            {
                "id": "a2",
                "decision": "flag",
                "cost_usd": 0.20,
                "action_type": "llm_call",
                "created_at": now,
            },
            {
                "id": "a3",
                "decision": "block",
                "cost_usd": 0.0,
                "action_type": "llm_call",
                "created_at": now,
            },
        ]
    )
    assert memory_store.daily_spend_usd(memory_store.project["id"]) == pytest.approx(0.30)


# --- Concurrency cannot exceed policy (JG-002) ------------------------------


def test_concurrent_reservations_respect_rate_limit(memory_store: MemoryStore) -> None:
    """Open reservations count toward the cap, under the per-project lock."""
    import time

    project_id = memory_store.project["id"]
    release = threading.Event()
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        reservation = memory_store.reserve(project_id, 0.01, 10.0, 3)
        with lock:
            outcomes.append(reservation.outcome)
        if reservation.outcome == "ok":
            assert release.wait(timeout=5)
            memory_store.release(reservation.reservation_id)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(attempt) for _ in range(12)]
        deadline = time.time() + 5
        while sum(1 for o in outcomes if o == "ok") < 3 and time.time() < deadline:
            time.sleep(0.01)
        assert sum(1 for o in outcomes if o == "ok") == 3
        # While those three are held, further reserves must be refused.
        assert memory_store.reserve(project_id, 0.01, 10.0, 3).outcome == "rate_exceeded"
        release.set()
        for future in futures:
            future.result(timeout=5)

    assert outcomes.count("ok") == 3
    assert outcomes.count("rate_exceeded") == 9


# --- Blocked calls never reach the provider ---------------------------------


def test_blocked_llm_never_calls_provider(
    client: TestClient,
    agent_headers: dict[str, str],
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(main_mod.provider, "complete", provider)

    memory_store.set_status(memory_store.project["id"], "suspended", "test")
    response = _llm(client, agent_headers)
    assert response.status_code == 200
    assert response.json()["decision"] == "block"
    provider.assert_not_called()


def test_rate_block_never_calls_provider(
    client: TestClient,
    agent_headers: dict[str, str],
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(main_mod.provider, "complete", provider)
    memory_store.policy["max_requests_per_min"] = 0
    response = _llm(client, agent_headers)
    assert response.json()["decision"] == "block"
    provider.assert_not_called()


# --- Suspended projects block both lanes ------------------------------------


def test_suspended_project_blocks_both_lanes(
    client: TestClient,
    agent_headers: dict[str, str],
    operator_headers: dict[str, str],
) -> None:
    suspend = client.post(
        "/v1/projects/suspend",
        headers=operator_headers,
        json={"reason": "security test suspend"},
    )
    assert suspend.status_code == 200
    body = suspend.json()
    assert body["status"] == "suspended"
    assert "api_key" not in body
    assert "api_key_hash" not in body

    install = _install(client, agent_headers)
    llm = _llm(client, agent_headers)
    assert install.json()["decision"] == "block"
    assert llm.json()["decision"] == "block"
    assert "suspended" in install.json()["reason"].lower()


def test_agent_key_cannot_suspend(
    client: TestClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(
        "/v1/projects/suspend",
        headers=agent_headers,
        json={"reason": "agent trying to kill switch"},
    )
    assert response.status_code == 401


def test_control_plane_checks_auth_before_request_shape(
    client: TestClient, agent_headers: dict[str, str]
) -> None:
    """401 regardless of whether the body names a project.

    The project lookup used to run first, so an unauthenticated caller on a
    multi-project deployment was told which field they had forgotten instead of
    that they had no business here at all.
    """
    for body in ({}, {"project_id": "1a2b3c4d-0000-0000-0000-000000000000"}):
        response = client.post("/v1/projects/suspend", headers=agent_headers, json=body)
        assert response.status_code == 401, body
        assert response.json()["detail"]["error"] == "operator_identity_required"


# --- Anonymous / cross-project reads fail -----------------------------------


def test_anonymous_event_reads_fail(client: TestClient) -> None:
    assert client.get("/v1/events/recent").status_code == 401
    assert client.post("/v1/events/token").status_code == 401
    assert client.get("/v1/events/stream?cursor=0").status_code == 401


def test_wrong_agent_key_rejected(client: TestClient) -> None:
    response = client.get(
        "/v1/events/recent", headers={"X-Juno-Key": "jg_not_a_real_key"}
    )
    assert response.status_code == 401


def test_stream_token_is_project_scoped(
    client: TestClient,
    agent_headers: dict[str, str],
    memory_store: MemoryStore,
) -> None:
    from app import tokens

    minted = client.post("/v1/events/token", headers=agent_headers).json()
    verified = tokens.verify(minted["token"])
    assert verified is not None
    assert verified[0] == memory_store.project["id"]

    events.publish("action", memory_store.project["id"], {"hello": "a"})
    events.publish("action", "other-project-id", {"hello": "b"})

    recent = client.get("/v1/events/recent", headers=agent_headers).json()
    assert all(e["project_id"] == memory_store.project["id"] for e in recent["events"])
    assert not any(e["data"].get("hello") == "b" for e in recent["events"])

    # Feed helpers themselves never cross projects.
    ours = events.since(0, memory_store.project["id"])
    theirs = events.since(0, "other-project-id")
    assert all(e["data"].get("hello") == "a" for e in ours)
    assert all(e["data"].get("hello") == "b" for e in theirs)

    assert tokens.verify("not-a-token") is None


# --- Mock / degraded / live remain distinguishable --------------------------


def test_health_reports_mock_mode(client: TestClient) -> None:
    health = client.get("/health").json()
    assert health["mode"] == "mock"
    assert health["store"] in {"memory", "supabase"}
    assert "scanner" in health
    assert "provider" in health


def test_production_readiness_fails_when_degraded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "JUNO_ENV", "production")
    monkeypatch.setattr(config, "USE_SUPABASE", False)
    monkeypatch.setattr(config, "USE_OSSPREY", False)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", [])
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["problems"]


def test_idempotent_llm_calls_provider_once(
    client: TestClient,
    agent_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def complete(prompt: str, model: str, max_output_tokens: int) -> dict[str, Any]:
        calls["n"] += 1
        return {"answer": "once", "tokens_in": 3, "tokens_out": 2}

    monkeypatch.setattr(main_mod.provider, "complete", complete)
    headers = {**agent_headers, "Idempotency-Key": "same-key-1"}
    first = _llm(client, headers)
    second = _llm(client, headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json().get("idempotent_replay") is True
    assert calls["n"] == 1
