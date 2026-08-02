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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import quote, urlparse

import httpx

from . import config

RESULT_PREFIX = "JUNO_SANDBOX_RESULT="
DOWNLOAD_TIMEOUT_SECONDS = 10.0
Ecosystem = Literal["npm", "pypi"]


@dataclass(frozen=True)
class Artifact:
    """An immutable registry artifact prepared for one sandbox run."""

    ecosystem: Ecosystem
    version: str
    kind: Literal["npm-tarball", "pypi-sdist", "pypi-wheel"]
    url: str
    digest_algorithm: str
    digest: bytes
    suffix: str
    filename: str


@dataclass(frozen=True)
class PreparedArtifact:
    descriptor: Artifact
    path: Path


class SandboxError(RuntimeError):
    """A detonation could not be completed safely."""


def _npm_metadata(package: str, version: str | None) -> Artifact:
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
    algorithm, digest = _npm_digest(integrity, shasum)
    return Artifact(
        ecosystem="npm",
        version=resolved,
        kind="npm-tarball",
        url=tarball,
        digest_algorithm=algorithm,
        digest=digest,
        suffix=".tgz",
        filename="package.tgz",
    )


def _pypi_metadata(package: str, version: str | None) -> Artifact:
    encoded = quote(package.strip(), safe="")
    suffix = f"/{quote(version, safe='')}" if version else ""
    response = httpx.get(
        f"{config.PYPI_URL}/pypi/{encoded}{suffix}/json",
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    info = body.get("info") if isinstance(body.get("info"), dict) else {}
    resolved = str(info.get("version") or version or "").strip()
    files = body.get("urls") if isinstance(body.get("urls"), list) else []

    sdist = next(
        (
            item
            for item in files
            if isinstance(item, dict)
            and item.get("packagetype") == "sdist"
            and str(item.get("filename") or "").endswith((".tar.gz", ".zip"))
        ),
        None,
    )
    wheel = next(
        (
            item
            for item in files
            if isinstance(item, dict)
            and item.get("packagetype") == "bdist_wheel"
            and str(item.get("filename") or "").endswith("-py3-none-any.whl")
        ),
        None,
    )
    selected = sdist or wheel
    if not resolved or not isinstance(selected, dict):
        raise SandboxError(
            "PyPI release has no supported sdist or pure py3-none-any wheel"
        )

    filename = str(selected.get("filename") or "")
    artifact_url = str(selected.get("url") or "").strip()
    digests = selected.get("digests") if isinstance(selected.get("digests"), dict) else {}
    sha256 = str(digests.get("sha256") or "").lower()
    if (
        not artifact_url
        or not filename
        or Path(filename).name != filename
        or any(not (char.isalnum() or char in "._+-") for char in filename)
        or len(sha256) != 64
        or any(char not in "0123456789abcdef" for char in sha256)
    ):
        raise SandboxError("PyPI artifact metadata lacks a valid SHA-256 digest")

    return Artifact(
        ecosystem="pypi",
        version=resolved,
        kind="pypi-sdist" if selected is sdist else "pypi-wheel",
        url=artifact_url,
        digest_algorithm="sha256",
        digest=bytes.fromhex(sha256),
        suffix=".tar.gz" if filename.endswith(".tar.gz") else Path(filename).suffix,
        filename=filename,
    )


def _registry_metadata(
    package: str, ecosystem: Ecosystem, version: str | None
) -> Artifact:
    if ecosystem == "npm":
        return _npm_metadata(package, version)
    if ecosystem == "pypi":
        return _pypi_metadata(package, version)
    raise SandboxError(f"unsupported sandbox ecosystem: {ecosystem}")


def _allowed_artifact(url: str, ecosystem: Ecosystem) -> bool:
    registry_url = config.NPM_REGISTRY_URL if ecosystem == "npm" else config.PYPI_URL
    registry = urlparse(registry_url)
    candidate = urlparse(url)
    allowed_hosts = {registry.hostname}
    if ecosystem == "pypi" and registry.hostname in {"pypi.org", "www.pypi.org"}:
        allowed_hosts.add("files.pythonhosted.org")
    return (
        candidate.scheme == "https"
        and candidate.hostname is not None
        and candidate.hostname in allowed_hosts
        and candidate.username is None
        and candidate.password is None
    )


def _chunks(url: str) -> Iterator[bytes]:
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            if chunk:
                yield chunk


def _npm_digest(integrity: str, shasum: str) -> tuple[str, bytes]:
    if "-" in integrity:
        algorithm, encoded = integrity.split("-", 1)
        if algorithm in {"sha256", "sha384", "sha512"}:
            try:
                return algorithm, base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise SandboxError("registry package integrity is malformed") from exc

    shasum = shasum.lower()
    if len(shasum) == 40 and all(char in "0123456789abcdef" for char in shasum):
        return "sha1", bytes.fromhex(shasum)
    raise SandboxError("registry package digest uses an unsupported format")


def _download(
    package: str, ecosystem: Ecosystem, version: str | None, directory: Path
) -> PreparedArtifact:
    try:
        descriptor = _registry_metadata(package, ecosystem, version)
        if not _allowed_artifact(descriptor.url, ecosystem):
            raise SandboxError("registry artifact URL leaves the configured registry origin")
        digest = hashlib.new(descriptor.digest_algorithm)
        size = 0
        destination = directory / f"package{descriptor.suffix}"
        with destination.open("wb") as artifact:
            for chunk in _chunks(descriptor.url):
                size += len(chunk)
                if size > config.SANDBOX_MAX_ARTIFACT_BYTES:
                    raise SandboxError(
                        f"package artifact exceeds {config.SANDBOX_MAX_ARTIFACT_BYTES} bytes"
                    )
                digest.update(chunk)
                artifact.write(chunk)
        if digest.digest() != descriptor.digest:
            raise SandboxError("downloaded package does not match its registry digest")
        destination.chmod(0o444)
        return PreparedArtifact(descriptor=descriptor, path=destination)
    except SandboxError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed behind one typed error
        raise SandboxError(f"package artifact could not be prepared: {exc}") from exc


def _docker_command(name: str, artifact: PreparedArtifact) -> list[str]:
    if artifact.descriptor.ecosystem == "npm":
        destination = "/input/package.tgz"
        image = config.SANDBOX_IMAGE
    else:
        destination = (
            f"/input/{artifact.descriptor.filename}"
            if artifact.descriptor.kind == "pypi-wheel"
            else f"/input/package{artifact.descriptor.suffix}"
        )
        image = config.SANDBOX_PYPI_IMAGE
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
        f"--mount=type=bind,src={artifact.path},dst={destination},readonly",
        image,
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


def _run(artifact: PreparedArtifact) -> dict[str, Any]:
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
    if ecosystem not in {"npm", "pypi"}:
        raise SandboxError(f"unsupported sandbox ecosystem: {ecosystem}")

    with tempfile.TemporaryDirectory(prefix="junoguard-sandbox-") as directory:
        prepared = _download(package, ecosystem, version, Path(directory))
        result = _run(prepared)

    return {
        **result,
        "engine": "docker",
        "package": package,
        "version": prepared.descriptor.version,
        "artifact_kind": prepared.descriptor.kind,
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
