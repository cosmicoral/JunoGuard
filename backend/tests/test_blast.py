"""Agent-scoped blast-radius tests: names in, never secret values out."""

from __future__ import annotations

from app import blast


def test_client_declared_scope_excludes_gateway_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GATEWAY_ONLY_SECRET", "must-not-shape-agent-scope")
    scope = {
        "credential_names": ["OPENAI_API_KEY", "AWS_PROFILE", "MAX_REQUEST_TOKENS"],
        "workspace_access": "read_write",
        "repository": True,
    }

    result = blast.compute("example", ["Reads process environment"], agent_scope=scope)

    assert result["credentials_in_scope"] == ["OPENAI_API_KEY"]
    assert result["cloud_access"] == ["AWS"]
    assert result["write_access"] == "agent workspace (read/write)"
    assert result["scope_source"] == "client_declared"
    assert "GATEWAY_ONLY_SECRET" not in str(result)
    assert "must-not-shape-agent-scope" not in str(result)


def test_invalid_declared_names_are_discarded() -> None:
    result = blast.compute(
        "example",
        agent_scope={
            "credential_names": [
                "VALID_SECRET",
                "BAD=secret-value",
                "../../TOKEN",
                "space token",
            ],
            "workspace_access": "unknown",
            "repository": None,
        },
    )

    assert result["credentials_in_scope"] == ["VALID_SECRET"]
    assert result["write_access"] == "workspace access not declared"


def test_sandbox_observations_enrich_network_and_environment_evidence() -> None:
    result = blast.compute(
        "example",
        findings=[],
        agent_scope={
            "credential_names": [],
            "workspace_access": "read_only",
            "repository": True,
        },
        sandbox_observations=[
            "package attempted network access; sandbox network was disabled",
            "output referenced credential or host-sensitive material",
        ],
    )

    assert result["network_egress"] == "unrestricted — attempt observed"
    assert result["reads_environment"] is True
    assert result["write_access"] == "agent workspace (read-only)"
