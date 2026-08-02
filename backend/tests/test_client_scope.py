"""Python CLI and MCP clients declare the same names-only agent scope."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parents[2]
CLIENT_PATHS = (
    ROOT / "cli" / "juno_cli" / "client.py",
    ROOT / "mcp" / "juno_mcp" / "client.py",
)


def load_client(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"scope_client_{path.parent.name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", CLIENT_PATHS)
def test_python_client_scope_contains_names_not_values(
    path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_client(path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=super-secret-value\n"
        "export AWS_PROFILE=production\n"
        "MAX_REQUEST_TOKENS=4000\n"
    )
    monkeypatch.setenv("GITHUB_TOKEN", "another-secret-value")

    scope = module.collect_agent_scope(tmp_path)

    assert "OPENAI_API_KEY" in scope["credential_names"]
    assert "AWS_PROFILE" in scope["credential_names"]
    assert "GITHUB_TOKEN" in scope["credential_names"]
    assert "MAX_REQUEST_TOKENS" not in scope["credential_names"]
    assert scope["repository"] is True
    assert "super-secret-value" not in str(scope)
    assert "another-secret-value" not in str(scope)


@pytest.mark.parametrize("path", CLIENT_PATHS)
def test_python_guard_install_attaches_scope(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_client(path)
    declared = {
        "credential_names": ["TEST_SECRET"],
        "workspace_access": "read_write",
        "repository": True,
    }
    monkeypatch.setattr(module, "collect_agent_scope", lambda: declared)
    client = module.JunoClient(project_key="jg_test", mock=False)
    request = MagicMock(return_value={"decision": "allow"})
    monkeypatch.setattr(client, "_request", request)

    client.guard_install("example", "npm", "1.0.0")

    assert request.call_args.args[2]["agent_scope"] == declared
