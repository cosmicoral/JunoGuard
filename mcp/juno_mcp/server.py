"""JunoGuard MCP server.

Three tools over stdio. Whatever these return is rendered straight into the
Cursor chat, so the return value is the product surface, not a debug dump.

Design notes that matter:

* A block is a successful call. It returns HTTP 200 from the gateway and a
  rendered refusal from here. It never raises — an exception would show up as a
  tool failure and the agent would retry.
* If the gateway is unreachable, we still return a string, but one shaped like
  a refusal. An unconsultable guard is not permission to proceed.
* The refusal text is written for the agent, not just the human: it states
  plainly that nothing was installed and that it should pick an alternative.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

try:  # mcp SDK >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import integrity
from .client import JunoClient, JunoNotConfigured, JunoUnavailable
from .render import render_error, render_install, render_llm, render_status, to_plain

mcp = _Server("junoguard")

# One INFO line per guarded call would bury anything real in Cursor's MCP log.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _client() -> JunoClient:
    # Built per call so environment changes take effect without a restart.
    return JunoClient()


def _unavailable(subject: str, exc: JunoUnavailable, consequence: str) -> str:
    return to_plain(render_error(subject, exc.detail, consequence))


def _consult_failure(subject: str, exc: Exception, consequence: str) -> str:
    if isinstance(exc, JunoNotConfigured):
        return _unavailable(subject, JunoUnavailable(exc.detail), consequence)
    if isinstance(exc, JunoUnavailable):
        return _unavailable(subject, exc, consequence)
    raise exc


@mcp.tool()
def guard_install(package: str, ecosystem: str = "npm", version: str | None = None) -> str:
    """Check a package with JunoGuard BEFORE installing it. Required for every install.

    Call this first, every time, for any dependency you are about to add — npm,
    pnpm, yarn, pip, poetry, uv, or a manifest edit. Only run the real package
    manager if this returns an allow.

    Args:
        package: Package name, e.g. "express" or "@ossprey/test-package".
        ecosystem: "npm" or "pypi". Defaults to "npm".
        version: Optional exact version. Omit for latest.

    Returns a decision. If it is a block, the package was NOT installed: do not
    retry it and do not try another package manager — choose a different
    dependency, or tell the user no safe option exists.
    """
    try:
        payload = _client().guard_install(package, ecosystem, version)
    except (JunoNotConfigured, JunoUnavailable) as exc:
        return _consult_failure(
            f"{package}  ({ecosystem})",
            exc,
            "The guard could not be consulted, so this install is not approved.\n"
            "Do not install this package. Start the JunoGuard gateway, or set\n"
            "JUNO_MOCK=1 for offline mode, then try again.",
        )
    return to_plain(render_install(payload, package, ecosystem))


@mcp.tool()
def guard_llm(prompt: str, model: str | None = None, max_output_tokens: int = 300) -> str:
    """Make a model call through JunoGuard, with budget and burst policy applied.

    The provider key stays server-side and never reaches this client. Token
    counts, cost, and the running daily spend come back with the answer.

    Args:
        prompt: The prompt to send.
        model: Model id. Omit to use the gateway deployment default.
        max_output_tokens: Output cap for this call. Defaults to 300.

    If the result is a block, no model call was made and nothing was charged.
    Do not retry the same call — reduce it, or stop and ask the operator.
    """
    label = model or "gateway default"
    try:
        payload = _client().guard_llm(prompt, model, max_output_tokens)
    except (JunoNotConfigured, JunoUnavailable) as exc:
        return _consult_failure(
            f"model call  ·  {label}",
            exc,
            "The guard could not be consulted, so this call was not made.\n"
            "Start the JunoGuard gateway, or set JUNO_MOCK=1 for offline mode.",
        )
    return to_plain(render_llm(payload, label))


@mcp.tool()
def guard_status() -> str:
    """Check this project's JunoGuard budget, spend, rate limit, and incidents.

    Cheap and safe to poll. Call it before a run of expensive work so you know
    the remaining budget instead of discovering the limit by hitting it. If the
    project is suspended, stop: every install and model call will be blocked.
    """
    try:
        payload = _client().status()
    except (JunoNotConfigured, JunoUnavailable) as exc:
        return _consult_failure(
            "project status",
            exc,
            "The guard could not be consulted. Assume no budget is available\n"
            "and do not proceed with guarded work.",
        )
    return to_plain(render_status(payload))


def tool_definitions() -> list:
    """The tool surface exactly as a client would receive it."""
    return asyncio.run(mcp.list_tools())


def check_integrity() -> integrity.Report:
    return integrity.verify(tool_definitions(), integrity.load_lock())


def _allow_unpinned() -> bool:
    return os.getenv(integrity.UNPINNED_ENV, "").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    """Verify our own tool definitions, then serve.

    A guard that cannot vouch for what it is telling the agent has nothing to
    offer it, so this fails closed like everything else here: the server refuses
    to start and names the tool that moved, rather than serving a surface nobody
    reviewed. Cursor shows it red, which is the alert.
    """
    decision = integrity.gate(check_integrity(), _allow_unpinned())
    if decision.message:
        print(decision.message, file=sys.stderr)
    if not decision.serve:
        raise SystemExit(integrity.REFUSE_EXIT_CODE)

    mcp.run()


def cli(argv: list[str] | None = None) -> int:
    """`--verify` for CI, `--update-lock` to re-pin after a reviewed change."""
    args = list(sys.argv[1:] if argv is None else argv)

    if "--verify" in args:
        report = check_integrity()
        print(f"juno-mcp: {report.summary()}")
        return 0 if report.ok else 1

    if "--update-lock" in args:
        manifest = integrity.write_lock(tool_definitions())
        print(
            f"juno-mcp: pinned {len(manifest['tools'])} tools "
            f"({', '.join(manifest['tools'])}) -> {integrity.LOCK_PATH.name}\n"
            f"  surface {manifest['surface']}\n"
            f"  Commit this file: it is the reviewed record of what agents are told."
        )
        return 0

    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
