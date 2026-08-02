"""Security boundary tests for npm lifecycle detonation."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app import config, sandbox


def test_download_verifies_registry_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"a harmless package tarball fixture"
    integrity = base64.b64encode(hashlib.sha512(payload).digest()).decode()
    monkeypatch.setattr(
        sandbox,
        "_registry_metadata",
        lambda *a, **k: {
            "version": "1.2.3",
            "tarball": "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
            "integrity": f"sha512-{integrity}",
            "shasum": "",
        },
    )
    monkeypatch.setattr(sandbox, "_chunks", lambda url: iter([payload[:10], payload[10:]]))
    destination = tmp_path / "package.tgz"

    resolved = sandbox._download("example", "1.2.3", destination)

    assert resolved == "1.2.3"
    assert destination.read_bytes() == payload
    assert destination.stat().st_mode & 0o777 == 0o444


def test_download_rejects_tarball_off_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sandbox,
        "_registry_metadata",
        lambda *a, **k: {
            "version": "1.2.3",
            "tarball": "https://attacker.invalid/payload.tgz",
            "integrity": "sha512-ZmFrZQ==",
            "shasum": "",
        },
    )

    with pytest.raises(sandbox.SandboxError, match="leaves the configured registry origin"):
        sandbox._download("example", "1.2.3", tmp_path / "package.tgz")


def test_docker_command_enforces_isolation(tmp_path: Path) -> None:
    artifact = tmp_path / "package.tgz"
    command = sandbox._docker_command("junoguard-test", artifact)
    joined = " ".join(command)

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--pull=never" in command
    assert "--user=65534:65534" in command
    assert str(artifact) in joined


def test_run_parses_structured_container_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = {
        "status": "completed",
        "scripts_executed": [{"lifecycle": "postinstall", "exit_code": 0}],
        "observations": [],
    }
    process = subprocess.CompletedProcess(
        ["docker"], 0, stdout=f"noise\n{sandbox.RESULT_PREFIX}{json.dumps(evidence)}\n", stderr=""
    )
    monkeypatch.setattr(sandbox.subprocess, "run", MagicMock(return_value=process))

    assert sandbox._run(tmp_path / "package.tgz") == evidence


def test_timeout_force_removes_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(sandbox.subprocess, "run", run)
    result = sandbox._run(tmp_path / "package.tgz")

    assert result["status"] == "timed_out"
    assert len(calls) == 2
    assert calls[1][1:3] == ["rm", "-f"]


def test_detonate_never_passes_package_name_to_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = "example; touch /host/pwned"

    def download(name: str, version: str | None, destination: Path) -> str:
        destination.write_bytes(b"fixture")
        return "1.0.0"

    runner = MagicMock(return_value={"status": "completed", "scripts_executed": []})
    monkeypatch.setattr(sandbox, "_download", download)
    monkeypatch.setattr(sandbox, "_run", runner)

    result = sandbox.detonate(package, "npm", "1.0.0")

    assert result["package"] == package
    mounted_path = runner.call_args.args[0]
    assert package not in str(mounted_path)
    assert str(mounted_path).startswith(tempfile_prefix())


def tempfile_prefix() -> str:
    """The platform-independent parent used by TemporaryDirectory."""
    import tempfile

    return str(Path(tempfile.gettempdir()))
