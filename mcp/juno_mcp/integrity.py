"""Tool-definition integrity for our own MCP surface.

A tool description is not documentation. The model reads it as instruction, so
whoever controls it steers the agent. The two attacks that follow are named in
docs/threat-landscape.md §2.4:

* **Tool poisoning** — instructions hidden in a description the user never reads.
* **Rug pull** — a server approved while benign later redefines its tools and
  inherits the approval. Most clients do not alert on the change.

We are an MCP surface, so both apply to us. This module pins what we serve.
Every tool's name, description and schema is hashed into `tools.lock.json`,
which is committed and reviewable; the server verifies itself against that lock
before it will answer anything.

What that buys, stated honestly:

* A dependency update, a tampered install, or an edit that reaches the package
  after review cannot silently change what the agent is told — the server
  refuses to start and says which tool moved.
* The lock is a git-tracked artefact, so re-pinning is a diff somebody has to
  approve. That is the trust root: not this file, the review.

What it does not buy: an attacker who can edit the source *and* the lock in the
same reviewed commit is not stopped by a hash. That is a code-review problem,
and the lock is what makes it visible in one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOCK_PATH = Path(__file__).with_name("tools.lock.json")

LOCK_VERSION = 1
ALGORITHM = "sha256"

# Everything the model or the client can be steered by. `icons`, `meta` and
# `execution` are deliberately excluded: they are presentation and transport
# detail that the SDK may set differently between versions, and pinning them
# would produce noisy failures that teach people to re-pin without reading.
SIGNIFICANT_FIELDS = (
    "name",
    "title",
    "description",
    "input_schema",
    "output_schema",
    "annotations",
)


def _as_dict(tool: Any) -> dict[str, Any]:
    if hasattr(tool, "model_dump"):
        return tool.model_dump(mode="json")
    if isinstance(tool, dict):
        return dict(tool)
    raise TypeError(f"cannot read tool definition from {type(tool)!r}")


def canonical(tool: Any) -> dict[str, Any]:
    """The part of a tool definition that can change agent behaviour."""
    raw = _as_dict(tool)
    # Accept either snake_case (SDK objects) or camelCase (wire JSON).
    aliases = {"input_schema": "inputSchema", "output_schema": "outputSchema"}
    out: dict[str, Any] = {}
    for field_name in SIGNIFICANT_FIELDS:
        value = raw.get(field_name)
        if value is None and field_name in aliases:
            value = raw.get(aliases[field_name])
        out[field_name] = value
    return out


def _encode(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(tool: Any) -> str:
    return hashlib.sha256(_encode(canonical(tool))).hexdigest()


def build_manifest(tools: list[Any]) -> dict[str, Any]:
    """A per-tool digest plus one digest over the whole surface.

    The combined digest covers the tool *set*, so adding or removing a tool is a
    change even though every surviving tool still matches.
    """
    per_tool = {}
    for tool in tools:
        entry = canonical(tool)
        name = entry["name"]
        if name in per_tool:
            raise ValueError(f"duplicate tool name: {name}")
        per_tool[name] = digest(tool)

    combined = hashlib.sha256(_encode(dict(sorted(per_tool.items())))).hexdigest()
    return {
        "lock_version": LOCK_VERSION,
        "algorithm": ALGORITHM,
        "tools": dict(sorted(per_tool.items())),
        "surface": combined,
    }


@dataclass
class Report:
    """What changed, in the terms an operator needs to decide if it is fine."""

    ok: bool
    reason: str = ""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "tool definitions match tools.lock.json"
        parts = []
        if self.added:
            parts.append(f"added: {', '.join(sorted(self.added))}")
        if self.removed:
            parts.append(f"removed: {', '.join(sorted(self.removed))}")
        if self.changed:
            parts.append(f"redefined: {', '.join(sorted(self.changed))}")
        detail = "; ".join(parts)
        return f"{self.reason}{' — ' if self.reason and detail else ''}{detail}"


def load_lock(path: Path = LOCK_PATH) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {}


def verify(tools: list[Any], lock: dict[str, Any] | None) -> Report:
    """Compare the live surface against the pinned one.

    A missing or unreadable lock is a failure, not a pass. "We could not check"
    is the same answer as "it does not match" everywhere else in this product.
    """
    if lock is None:
        return Report(False, "tools.lock.json is missing")
    if not lock or "tools" not in lock:
        return Report(False, "tools.lock.json is unreadable")
    if lock.get("lock_version") != LOCK_VERSION:
        return Report(
            False, f"tools.lock.json is version {lock.get('lock_version')!r}, expected {LOCK_VERSION}"
        )
    if lock.get("algorithm") != ALGORITHM:
        return Report(False, f"unsupported digest algorithm {lock.get('algorithm')!r}")

    current = build_manifest(tools)
    pinned_tools: dict[str, str] = lock["tools"]
    live_tools: dict[str, str] = current["tools"]

    added = sorted(set(live_tools) - set(pinned_tools))
    removed = sorted(set(pinned_tools) - set(live_tools))
    changed = sorted(
        name
        for name in set(live_tools) & set(pinned_tools)
        if live_tools[name] != pinned_tools[name]
    )

    if added or removed or changed:
        return Report(
            False,
            "the tool surface does not match the reviewed definitions",
            added=added,
            removed=removed,
            changed=changed,
        )

    # Belt and braces: the set matched tool by tool, so this can only disagree if
    # the lock's own combined digest was edited by hand.
    if lock.get("surface") != current["surface"]:
        return Report(False, "tools.lock.json surface digest does not match its own entries")

    return Report(True)


# Development escape hatch. Deliberately an environment variable rather than a
# config file setting: serving an unverified tool surface should take a
# conscious act at the command line, and leave a trace in the shell history.
UNPINNED_ENV = "JUNO_MCP_ALLOW_UNPINNED"

# EX_CONFIG. A refusal to start is the alert — the MCP client shows the server
# red, which is louder than a log line nobody reads.
REFUSE_EXIT_CODE = 78


@dataclass
class Decision:
    """Whether to serve, and what to tell the operator either way."""

    serve: bool
    message: str = ""


def gate(report: Report, allow_unpinned: bool = False) -> Decision:
    """Turn a verification result into a serve-or-refuse decision.

    Kept here, away from the SDK, so the policy is testable without an MCP
    runtime — the reason this module imports nothing but the standard library.
    """
    if report.ok:
        return Decision(True)

    if allow_unpinned:
        return Decision(
            True,
            f"juno-mcp: WARNING — {report.summary()}. "
            f"Serving anyway because {UNPINNED_ENV} is set.",
        )

    return Decision(
        False,
        f"juno-mcp: refusing to start — {report.summary()}.\n"
        f"  The tool descriptions an agent reads are instructions, so a change here "
        f"is a change to agent behaviour.\n"
        f"  Review the diff. If it is intended, re-pin with: "
        f"python -m juno_mcp --update-lock\n"
        f"  To serve unverified anyway (development only): {UNPINNED_ENV}=1",
    )


def write_lock(tools: list[Any], path: Path = LOCK_PATH) -> dict[str, Any]:
    manifest = build_manifest(tools)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
