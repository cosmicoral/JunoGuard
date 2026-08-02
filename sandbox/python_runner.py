"""Inspect one PyPI artifact inside JunoGuard's networkless worker."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

INPUT = Path("/input")
WORK = Path("/work")
SOURCE = WORK / "source"
DIST = WORK / "dist"
SITE = WORK / "site"
RESULT_PREFIX = "JUNO_SANDBOX_RESULT="
OUTPUT_LIMIT = 4_000
FILE_LIMIT = 200
ARCHIVE_FILE_LIMIT = 2_000
ARCHIVE_SIZE_LIMIT = 64 * 1024 * 1024
STEP_TIMEOUT_SECONDS = 3


class ArtifactRejected(ValueError):
    """The mounted archive is unsafe or unsupported."""


def clipped(value: Any) -> str:
    return str(value or "")[-OUTPUT_LIMIT:]


def emit(result: dict[str, Any]) -> None:
    print(f"{RESULT_PREFIX}{json.dumps(result, separators=(',', ':'))}", flush=True)


def safe_relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ArtifactRejected("archive contains a path outside its extraction root")
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        raise ArtifactRejected("archive contains an empty path")
    return Path(*parts)


def validate_members(entries: Iterable[tuple[str, int]]) -> None:
    seen: set[Path] = set()
    total_size = 0
    for count, (name, size) in enumerate(entries, start=1):
        if count > ARCHIVE_FILE_LIMIT:
            raise ArtifactRejected("archive contains too many entries")
        relative = safe_relative(name)
        if relative in seen:
            raise ArtifactRejected("archive contains duplicate entries")
        seen.add(relative)
        total_size += max(size, 0)
        if total_size > ARCHIVE_SIZE_LIMIT:
            raise ArtifactRejected("archive expands beyond the size limit")


def extract_tar(artifact: Path, destination: Path) -> None:
    with tarfile.open(artifact, mode="r:*") as archive:
        members = archive.getmembers()
        for member in members:
            if not (member.isfile() or member.isdir()):
                raise ArtifactRejected("archive contains a link or special file")
        validate_members((member.name, member.size) for member in members)
        for member in members:
            target = destination / safe_relative(member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ArtifactRejected("archive member could not be read")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)


def extract_zip(artifact: Path, destination: Path) -> None:
    with zipfile.ZipFile(artifact) as archive:
        entries = archive.infolist()
        for entry in entries:
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArtifactRejected("archive contains a symbolic link")
            if entry.flag_bits & 0x1:
                raise ArtifactRejected("archive contains an encrypted entry")
        validate_members((entry.filename, entry.file_size) for entry in entries)
        for entry in entries:
            target = destination / safe_relative(entry.filename)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)


def files_under(root: Path) -> list[str]:
    found: list[str] = []
    if not root.exists():
        return found
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not (Path(current) / name).is_symlink()
        )
        for name in [*directories, *sorted(files)]:
            found.append(str((Path(current) / name).relative_to(root)))
            if len(found) >= FILE_LIMIT:
                return sorted(found)
    return sorted(found)


def run_step(label: str, command: list[str]) -> dict[str, Any]:
    environment = {
        "HOME": "/tmp",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        process = subprocess.run(
            command,
            cwd=WORK,
            env=environment,
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_SECONDS,
            check=False,
        )
        return {
            "lifecycle": label,
            "exit_code": process.returncode,
            "signal": None,
            "timed_out": False,
            "stdout": clipped(process.stdout),
            "stderr": clipped(process.stderr),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "lifecycle": label,
            "exit_code": None,
            "signal": None,
            "timed_out": True,
            "stdout": clipped(error.stdout),
            "stderr": clipped(error.stderr),
        }


def source_root() -> Path:
    candidates = sorted(
        {
            marker.parent
            for pattern in ("pyproject.toml", "setup.py", "setup.cfg")
            for marker in SOURCE.rglob(pattern)
            if len(marker.relative_to(SOURCE).parts) <= 2
        }
    )
    if not candidates:
        raise ArtifactRejected("sdist has no Python build metadata")
    shallowest = min(len(path.relative_to(SOURCE).parts) for path in candidates)
    roots = [path for path in candidates if len(path.relative_to(SOURCE).parts) == shallowest]
    if len(roots) != 1:
        raise ArtifactRejected("sdist has an ambiguous project root")
    return roots[0]


def wheel_modules(wheel: Path) -> list[str]:
    modules: set[str] = set()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        top_level = next(
            (name for name in names if name.endswith(".dist-info/top_level.txt")),
            None,
        )
        if top_level:
            modules.update(
                line.strip()
                for line in archive.read(top_level).decode("utf-8", "replace").splitlines()
            )
        for name in names:
            path = PurePosixPath(name)
            if len(path.parts) == 1 and path.suffix == ".py":
                modules.add(path.stem)
            if len(path.parts) == 2 and path.name == "__init__.py":
                modules.add(path.parts[0])
    return sorted(module for module in modules if module.isidentifier())[:20]


def observations_for(executions: list[dict[str, Any]], created: list[str]) -> list[str]:
    output = "\n".join(
        f"{item.get('stdout', '')}\n{item.get('stderr', '')}" for item in executions
    )
    observations: list[str] = []
    if any(item["timed_out"] for item in executions):
        observations.append("Python build, install, or import exceeded time limit")
    if any(item["exit_code"] not in {0, None} for item in executions):
        observations.append("Python build, install, or import exited non-zero")
    if any(
        marker in output.lower()
        for marker in ("network is unreachable", "name or service not known", "connection refused")
    ):
        observations.append("Python package attempted network access; sandbox network was disabled")
    if any(
        marker in output
        for marker in (
            "/etc/passwd",
            "/etc/shadow",
            "OPENAI_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        )
    ):
        observations.append("Python output referenced credential or host-sensitive material")
    if created:
        observations.append(f"Python package created {len(created)} file(s)")
    return observations


def main() -> None:
    artifacts = [path for path in INPUT.iterdir() if path.is_file()]
    if len(artifacts) != 1:
        raise ArtifactRejected("sandbox requires exactly one package artifact")
    artifact = artifacts[0]
    before = set(files_under(WORK))
    executions: list[dict[str, Any]] = []
    wheel: Path | None = None

    SOURCE.mkdir(parents=True, exist_ok=True)
    if artifact.name.endswith((".tar.gz", ".zip")):
        if artifact.name.endswith(".tar.gz"):
            extract_tar(artifact, SOURCE)
        else:
            extract_zip(artifact, SOURCE)
        DIST.mkdir(parents=True, exist_ok=True)
        build = run_step(
            "build",
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(DIST),
                str(source_root()),
            ],
        )
        executions.append(build)
        built = sorted(DIST.glob("*.whl"))
        if build["exit_code"] == 0 and len(built) == 1:
            wheel = built[0]
    elif artifact.name.endswith("-py3-none-any.whl"):
        extract_zip(artifact, SOURCE)
        wheel = artifact
    else:
        raise ArtifactRejected("artifact is not a supported sdist or pure Python wheel")

    if wheel is not None:
        SITE.mkdir(parents=True, exist_ok=True)
        install = run_step(
            "install",
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                str(SITE),
                str(wheel),
            ],
        )
        executions.append(install)
        if install["exit_code"] == 0:
            for module in wheel_modules(wheel):
                executions.append(
                    run_step(
                        f"import:{module}",
                        [
                            sys.executable,
                            "-I",
                            "-c",
                            (
                                "import importlib,sys;"
                                f"sys.path.insert(0,{str(SITE)!r});"
                                "importlib.import_module(sys.argv[1])"
                            ),
                            module,
                        ],
                    )
                )

    created = sorted(set(files_under(WORK)) - before)
    emit(
        {
            "status": "completed",
            "scripts_executed": executions,
            "files_created": created[:FILE_LIMIT],
            "observations": observations_for(executions, created),
        }
    )


if __name__ == "__main__":
    try:
        main()
    except (ArtifactRejected, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        emit(
            {
                "status": "artifact_rejected",
                "scripts_executed": [],
                "files_created": [],
                "observations": [str(error)],
                "stderr": clipped(error),
            }
        )
