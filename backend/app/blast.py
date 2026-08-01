"""Blast radius.

Blocking is table stakes. The question a security reviewer actually asks is
"what would this have reached?" — so we answer it from the agent's real scope.

No LLM, no guessing: we read what is actually in the environment.
"""

from __future__ import annotations

import os
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

# Names that are noisy rather than sensitive.
IGNORE = ("SSH_AUTH_SOCK", "KEYBOARD", "KEYMAP")

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


def _env_file_names() -> set[str]:
    """Variable names declared in the repo's .env files.

    Names only — the values are exactly what we are trying to protect, and
    they must never reach a log, a response body, or a dashboard.
    """
    names: set[str] = set()
    for filename in ENV_FILES:
        path = SCAN_PATH / filename
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


def _credentials_in_scope() -> list[str]:
    candidates = set(os.environ) | _env_file_names()
    return sorted(name for name in candidates if _is_credential(name))


def _summarise(creds: list[str], clouds: list[str]) -> str:
    if clouds:
        return f"full {' and '.join(clouds)} credential compromise"
    if len(creds) >= 3:
        return "full production credential compromise"
    if creds:
        return "provider credential theft"
    return "local source and filesystem access"


def compute(package: str, findings: list[str] | None = None) -> dict[str, Any]:
    """What the postinstall script would have had, had it run."""
    reachable = set(os.environ) | _env_file_names()
    creds = _credentials_in_scope()
    clouds = sorted({label for var, label in CLOUD_MARKERS.items() if var in reachable})

    findings = findings or []
    reads_env = any("environ" in f.lower() or "env" in f.lower() for f in findings)
    egress = any(
        word in f.lower() for f in findings for word in ("outbound", "network", "post", "exfil")
    )

    return {
        # Cap the list: a wall of forty variable names reads as noise on a
        # projector. The count carries the weight.
        "credentials_in_scope": creds[:6],
        "credentials_total": len(creds),
        "cloud_access": clouds,
        "network_egress": "unrestricted" if egress or not findings else "observed on install",
        "write_access": "open repository",
        "reads_environment": reads_env,
        "summary": _summarise(creds, clouds),
    }
