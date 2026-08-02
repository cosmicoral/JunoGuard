"""Detonate npm lifecycle scripts inside a locked-down Docker container.

The gateway downloads the immutable registry tarball itself, verifies its
published digest, and mounts only that file into a container with no network,
no capabilities, a read-only root, bounded resources, and ephemeral tmpfs
storage. No project files or gateway environment variables enter the sandbox.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote, urlparse

import httpx

from . import config

RESULT_PREFIX = "JUNO_SANDBOX_RESULT="
DOWNLOAD_TIMEOUT_SECONDS = 10.0


class SandboxError(RuntimeError):
    """A detonation could not be completed safely."""


def _registry_metadata(package: str, version: str | None) -> dict[str, Any]:
    coordinate = version or "latest"
    url = (
        f"{config.NPM_REGISTRY_URL}/{quote(package.strip(), safe='@')}/"
        f"{quote(coordinate, safe='')}"
    )
    response = httpx.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    dist = body.get("dist") if isinstance(body.get("dist"), dict) else {}
    resolved = str(body.get("version") or "").strip()
    tarball = str(dist.get("tarball") or "").strip()
    integrity = str(dist.get("integrity") or "").strip()
    shasum = str(dist.get("shasum") or "").strip()
    if not resolved or not tarball or not (integrity or shasum):
        raise SandboxError("registry metadata lacks a version, tarball, or package digest")
    return {
        "version": resolved,
        "tarball": tarball,
        "integrity": integrity,
        "shasum": shasum,
    }


def _allowed_tarball(url: str) -> bool:
    registry = urlparse(config.NPM_REGISTRY_URL)
    candidate = urlparse(url)
    return (
        candidate.scheme == "https"
        and candidate.hostname is not None
        and candidate.hostname == registry.hostname
        and candidate.username is None
        and candidate.password is None
    )


def _chunks(url: str) -> Iterator[bytes]:
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            if chunk:
                yield chunk


def _expected_digest(metadata: dict[str, Any]) -> tuple[str, bytes]:
    integrity = metadata["integrity"]
    if "-" in integrity:
        algorithm, encoded = integrity.split("-", 1)
        if algorithm in {"sha256", "sha384", "sha512"}:
            try:
                return algorithm, base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise SandboxError("registry package integrity is malformed") from exc

    shasum = metadata["shasum"].lower()
    if len(shasum) == 40 and all(char in "0123456789abcdef" for char in shasum):
        return "sha1", bytes.fromhex(shasum)
    raise SandboxError("registry package digest uses an unsupported format")


def _download(package: str, version: str | None, destination: Path) -> str:
    try:
        metadata = _registry_metadata(package, version)
        if not _allowed_tarball(metadata["tarball"]):
            raise SandboxError("registry tarball URL leaves the configured registry origin")
        algorithm, expected = _expected_digest(metadata)
        digest = hashlib.new(algorithm)
        size = 0
        with destination.open("wb") as artifact:
            for chunk in _chunks(metadata["tarball"]):
                size += len(chunk)
                if size > config.SANDBOX_MAX_ARTIFACT_BYTES:
                    raise SandboxError(
                        f"package tarball exceeds {config.SANDBOX_MAX_ARTIFACT_BYTES} bytes"
                    )
                digest.update(chunk)
                artifact.write(chunk)
        if digest.digest() != expected:
            raise SandboxError("downloaded package does not match its registry digest")
        destination.chmod(0o444)
        return str(metadata["version"])
    except SandboxError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed behind one typed error
        raise SandboxError(f"package artifact could not be prepared: {exc}") from exc


def _docker_command(name: str, artifact: Path) -> list[str]:
    return [
        config.SANDBOX_DOCKER_BIN,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--cpus=0.5",
        "--user=65534:65534",
        "--tmpfs=/work:rw,nosuid,noexec,size=128m,mode=1777",
        "--tmpfs=/tmp:rw,nosuid,noexec,size=32m,mode=1777",
        f"--mount=type=bind,src={artifact},dst=/input/package.tgz,readonly",
        config.SANDBOX_IMAGE,
    ]


def _remove_container(name: str) -> None:
    try:
        subprocess.run(
            [config.SANDBOX_DOCKER_BIN, "rm", "-f", name],
            capture_output=True,
            check=False,
            timeout=5,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except Exception:  # noqa: BLE001 - cleanup is best effort after a timeout
        pass


def _run(artifact: Path) -> dict[str, Any]:
    name = f"junoguard-{uuid.uuid4().hex[:16]}"
    try:
        process = subprocess.run(
            _docker_command(name, artifact),
            capture_output=True,
            text=True,
            check=False,
            timeout=config.SANDBOX_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired:
        _remove_container(name)
        return {
            "status": "timed_out",
            "scripts_executed": [],
            "observations": ["sandbox exceeded its wall-clock time limit"],
        }
    except FileNotFoundError as exc:
        raise SandboxError(f"Docker executable not found: {config.SANDBOX_DOCKER_BIN}") from exc
    except Exception as exc:  # noqa: BLE001
        raise SandboxError(f"sandbox container could not start: {exc}") from exc

    for line in reversed(process.stdout.splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                result = json.loads(line.removeprefix(RESULT_PREFIX))
            except json.JSONDecodeError as exc:
                raise SandboxError("sandbox returned malformed result JSON") from exc
            if not isinstance(result, dict):
                raise SandboxError("sandbox result was not an object")
            return result

    detail = (process.stderr or process.stdout or "no output").strip()[-500:]
    raise SandboxError(f"sandbox exited without an evidence result: {detail}")


def detonate(package: str, ecosystem: str, version: str | None = None) -> dict[str, Any]:
    """Download, verify, and execute lifecycle scripts in the sandbox."""
    if ecosystem != "npm":
        raise SandboxError("sandbox detonation currently supports npm packages only")

    with tempfile.TemporaryDirectory(prefix="junoguard-sandbox-") as directory:
        artifact = Path(directory) / "package.tgz"
        resolved = _download(package, version, artifact)
        result = _run(artifact)

    return {
        **result,
        "engine": "docker",
        "package": package,
        "version": resolved,
        "isolation": {
            "network": "none",
            "root_filesystem": "read_only",
            "capabilities": "none",
            "host_mounts": ["verified package artifact (read-only)"],
            "memory_mb": 256,
            "cpus": 0.5,
            "pids": 64,
        },
    }
