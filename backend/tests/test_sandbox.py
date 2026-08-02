"""Security boundary tests for npm lifecycle detonation."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app import config, sandbox

PYTHON_RUNNER = runpy.run_path(
    str(Path(__file__).parents[2] / "sandbox" / "python_runner.py")
)


def npm_artifact(url: str, payload: bytes) -> sandbox.Artifact:
    return sandbox.Artifact(
        ecosystem="npm",
        version="1.2.3",
        kind="npm-tarball",
        url=url,
        digest_algorithm="sha512",
        digest=hashlib.sha512(payload).digest(),
        suffix=".tgz",
        filename="package.tgz",
    )


def prepared_npm_artifact(path: Path) -> sandbox.PreparedArtifact:
    return sandbox.PreparedArtifact(
        descriptor=npm_artifact(
            "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
            b"fixture",
        ),
        path=path,
    )


def pypi_artifact(url: str, payload: bytes) -> sandbox.Artifact:
    return sandbox.Artifact(
        ecosystem="pypi",
        version="1.2.3",
        kind="pypi-wheel",
        url=url,
        digest_algorithm="sha256",
        digest=hashlib.sha256(payload).digest(),
        suffix=".whl",
        filename="example-1.2.3-py3-none-any.whl",
    )


def test_download_verifies_registry_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"a harmless package tarball fixture"
    monkeypatch.setattr(
        sandbox,
        "_registry_metadata",
        lambda *a, **k: npm_artifact(
            "https://registry.npmjs.org/example/-/example-1.2.3.tgz", payload
        ),
    )
    monkeypatch.setattr(sandbox, "_chunks", lambda url: iter([payload[:10], payload[10:]]))

    prepared = sandbox._download("example", "npm", "1.2.3", tmp_path)

    assert prepared.descriptor.version == "1.2.3"
    assert prepared.path.read_bytes() == payload
    assert prepared.path.stat().st_mode & 0o777 == 0o444


def test_download_rejects_tarball_off_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sandbox,
        "_registry_metadata",
        lambda *a, **k: npm_artifact("https://attacker.invalid/payload.tgz", b"fake"),
    )

    with pytest.raises(sandbox.SandboxError, match="leaves the configured registry origin"):
        sandbox._download("example", "npm", "1.2.3", tmp_path)


def test_download_rejects_pypi_digest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = pypi_artifact(
        "https://files.pythonhosted.org/example-1.2.3.whl", b"expected"
    )
    monkeypatch.setattr(sandbox, "_registry_metadata", lambda *a, **k: descriptor)
    monkeypatch.setattr(sandbox, "_chunks", lambda url: iter([b"tampered"]))

    with pytest.raises(sandbox.SandboxError, match="does not match"):
        sandbox._download("example", "pypi", "1.2.3", tmp_path)


def test_pypi_artifacts_stay_on_approved_hosts() -> None:
    assert sandbox._allowed_artifact(
        "https://files.pythonhosted.org/packages/example.tar.gz", "pypi"
    )
    assert not sandbox._allowed_artifact("https://attacker.invalid/example.whl", "pypi")
    assert not sandbox._allowed_artifact(
        "http://files.pythonhosted.org/example.whl", "pypi"
    )


def test_pypi_metadata_prefers_sdist(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.return_value = {
        "info": {"version": "1.2.3"},
        "urls": [
            {
                "packagetype": "bdist_wheel",
                "filename": "example-1.2.3-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/example.whl",
                "digests": {"sha256": "11" * 32},
            },
            {
                "packagetype": "sdist",
                "filename": "example-1.2.3.tar.gz",
                "url": "https://files.pythonhosted.org/example.tar.gz",
                "digests": {"sha256": "22" * 32},
            },
        ],
    }
    monkeypatch.setattr(sandbox.httpx, "get", MagicMock(return_value=response))

    artifact = sandbox._pypi_metadata("example", None)

    assert artifact.kind == "pypi-sdist"
    assert artifact.suffix == ".tar.gz"
    assert artifact.digest == bytes.fromhex("22" * 32)


def test_pypi_metadata_accepts_only_pure_python_wheel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.return_value = {
        "info": {"version": "1.2.3"},
        "urls": [
            {
                "packagetype": "bdist_wheel",
                "filename": "example-1.2.3-cp312-cp312-macosx.whl",
                "url": "https://files.pythonhosted.org/native.whl",
                "digests": {"sha256": "11" * 32},
            }
        ],
    }
    monkeypatch.setattr(sandbox.httpx, "get", MagicMock(return_value=response))

    with pytest.raises(sandbox.SandboxError, match="no supported sdist"):
        sandbox._pypi_metadata("example", "1.2.3")


def test_docker_command_enforces_isolation(tmp_path: Path) -> None:
    artifact = tmp_path / "package.tgz"
    command = sandbox._docker_command(
        "junoguard-test", prepared_npm_artifact(artifact)
    )
    joined = " ".join(command)

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--pull=never" in command
    assert "--user=65534:65534" in command
    assert str(artifact) in joined


def test_pypi_docker_command_uses_dedicated_image_and_literal_mount(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "package.whl"
    prepared = sandbox.PreparedArtifact(
        descriptor=pypi_artifact(
            "https://files.pythonhosted.org/example-1.2.3.whl", b"fixture"
        ),
        path=artifact_path,
    )

    command = sandbox._docker_command("junoguard-test", prepared)

    assert command[-1] == config.SANDBOX_PYPI_IMAGE
    assert (
        f"--mount=type=bind,src={artifact_path},"
        "dst=/input/example-1.2.3-py3-none-any.whl,readonly"
    ) in command


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

    assert sandbox._run(prepared_npm_artifact(tmp_path / "package.tgz")) == evidence


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
    result = sandbox._run(prepared_npm_artifact(tmp_path / "package.tgz"))

    assert result["status"] == "timed_out"
    assert len(calls) == 2
    assert calls[1][1:3] == ["rm", "-f"]


def test_detonate_never_passes_package_name_to_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = "example; touch /host/pwned"

    def download(
        name: str, ecosystem: sandbox.Ecosystem, version: str | None, directory: Path
    ) -> sandbox.PreparedArtifact:
        destination = directory / "package.tgz"
        destination.write_bytes(b"fixture")
        descriptor = npm_artifact(
            "https://registry.npmjs.org/example/-/example-1.0.0.tgz",
            b"fixture",
        )
        return sandbox.PreparedArtifact(
            descriptor=sandbox.Artifact(
                **{**descriptor.__dict__, "version": "1.0.0"}
            ),
            path=destination,
        )

    runner = MagicMock(return_value={"status": "completed", "scripts_executed": []})
    monkeypatch.setattr(sandbox, "_download", download)
    monkeypatch.setattr(sandbox, "_run", runner)

    result = sandbox.detonate(package, "npm", "1.0.0")

    assert result["package"] == package
    mounted_path = runner.call_args.args[0]
    assert package not in str(mounted_path.path)
    assert str(mounted_path.path).startswith(tempfile_prefix())


def tempfile_prefix() -> str:
    """The platform-independent parent used by TemporaryDirectory."""
    import tempfile

    return str(Path(tempfile.gettempdir()))


def test_python_worker_rejects_zip_path_traversal(tmp_path: Path) -> None:
    artifact = tmp_path / "malicious.zip"
    destination = tmp_path / "output"
    destination.mkdir()
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("../escaped.py", "raise SystemExit")

    with pytest.raises(PYTHON_RUNNER["ArtifactRejected"], match="outside"):
        PYTHON_RUNNER["extract_zip"](artifact, destination)

    assert not (tmp_path / "escaped.py").exists()
