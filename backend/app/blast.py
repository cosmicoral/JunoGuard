"""Blast radius.

Blocking is table stakes. The question a security reviewer actually asks is
"what would this have reached?" — so we answer it from the scope declared by
the local agent client.

No LLM and no secret values cross the API: only credential names and workspace
capability flags are accepted.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# The repository the agent is working in. A postinstall script runs with the
# working directory's .env files in reach, not the gateway's shell environment
# — so that is what we inspect.
SCAN_PATH = Path(os.getenv("JUNO_SCAN_PATH", Path.cwd())).expanduser()

ENV_FILES = (".env", ".env.local", ".env.development", ".env.production")

# Substrings that mark an environment variable as a credential worth naming.
CREDENTIAL_MARKERS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "PRIVATE",
    "DSN",
)

# Names that are noisy rather than sensitive. MAX_REQUEST_TOKENS and friends
# match the TOKEN marker but are limits, not secrets — naming one as a
# credential in scope undermines every other name on the list.
IGNORE = (
    "SSH_AUTH_SOCK",
    "KEYBOARD",
    "KEYMAP",
    "MAX_REQUEST_TOKENS",
    "MAX_TOKENS",
    "MAX_OUTPUT_TOKENS",
    "TOKENS_PER",
    "TOKEN_LIMIT",
    "PUBLIC_KEY",
    "KEY_LENGTH",
)

# Environment variables that imply cloud reach rather than a single API.
CLOUD_MARKERS = {
    "AWS_PROFILE": "AWS",
    "AWS_ACCESS_KEY_ID": "AWS",
    "GOOGLE_APPLICATION_CREDENTIALS": "GCP",
    "AZURE_CLIENT_SECRET": "Azure",
    "KUBECONFIG": "Kubernetes",
}


def _is_credential(name: str) -> bool:
    upper = name.upper()
    if any(skip in upper for skip in IGNORE):
        return False
    return any(marker in upper for marker in CREDENTIAL_MARKERS)


def _env_file_names(scan_path: Path = SCAN_PATH) -> set[str]:
    """Variable names declared in the repo's .env files.

    Names only — the values are exactly what we are trying to protect, and
    they must never reach a log, a response body, or a dashboard.
    """
    names: set[str] = set()
    for filename in ENV_FILES:
        path = scan_path / filename
        if not path.is_file():
            continue
        try:
            for line in path.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
                if key:
                    names.add(key)
        except OSError:
            continue
    return names


def _credentials_in_scope(candidates: set[str]) -> list[str]:
    return sorted(name for name in candidates if _is_credential(name))


def _summarise(creds: list[str], clouds: list[str]) -> str:
    if clouds:
        return f"full {' and '.join(clouds)} credential compromise"
    if len(creds) >= 3:
        return "full production credential compromise"
    if creds:
        return "provider credential theft"
    return "local source and filesystem access"


def _declared_scope(scope: dict[str, Any] | None) -> tuple[set[str], str, bool | None]:
    if scope is None:
        return set(os.environ) | _env_file_names(), "gateway_fallback", None

    raw_names = scope.get("credential_names")
    names = raw_names if isinstance(raw_names, list) else []
    reachable = {
        name
        for name in names[:200]
        if isinstance(name, str)
        and len(name) <= 128
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
    }
    access = str(scope.get("workspace_access") or "unknown")
    repository = scope.get("repository")
    write_access = access == "read_write"
    return reachable, "client_declared", write_access if repository is True else None


def compute(
    package: str,
    findings: list[str] | None = None,
    agent_scope: dict[str, Any] | None = None,
    sandbox_observations: list[str] | None = None,
) -> dict[str, Any]:
    """What the package would have reached in the declaring agent process."""
    reachable, scope_source, workspace_writable = _declared_scope(agent_scope)
    creds = _credentials_in_scope(reachable)
    clouds = sorted({label for var, label in CLOUD_MARKERS.items() if var in reachable})

    findings = findings or []
    observations = sandbox_observations or []
    evidence = [*findings, *observations]
    reads_env = any("environ" in item.lower() or "credential" in item.lower() for item in evidence)
    egress = any(
        word in item.lower()
        for item in evidence
        for word in ("outbound", "network", "post", "exfil")
    )
    if workspace_writable is True:
        write_access = "agent workspace (read/write)"
    elif workspace_writable is False:
        write_access = "agent workspace (read-only)"
    else:
        write_access = "workspace access not declared"

    return {
        # Cap the list: a wall of forty variable names reads as noise on a
        # projector. The count carries the weight.
        "credentials_in_scope": creds[:6],
        "credentials_total": len(creds),
        "cloud_access": clouds,
        "network_egress": (
            "unrestricted — attempt observed"
            if egress
            else "agent network access (no attempt observed)"
        ),
        "write_access": write_access,
        "reads_environment": reads_env,
        "scope_source": scope_source,
        "scope_is_attested": False,
        "summary": _summarise(creds, clouds),
    }
