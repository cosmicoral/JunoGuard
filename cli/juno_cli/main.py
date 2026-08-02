"""`juno` — JunoGuard on the command line.

The forwarders (`juno npm|pnpm|yarn install`, `juno pip install`) are the
point: scan first, and only shell out to the real package manager if every
package came back clean. A block prints the refusal, exits non-zero, and never
reaches the package manager. So does an unreachable gateway — a guard that
cannot be consulted is not permission to proceed.
"""

from __future__ import annotations

import os
import subprocess
import time

import typer

from . import __version__
from .client import JunoClient, JunoUnavailable
from .console import console, emit, to_rich
from .feed import SCRIPT, Event, clock_now, diff_status, render_event
from .render import S_BLOCK, S_DIM, S_FLAG, render_error, render_install, render_status

# 0 clean · 2 blocked by policy · 3 guard unreachable. Distinct so a CI job can
# tell "Juno said no" apart from "Juno was down", which are different problems.
EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_UNAVAILABLE = 3
# Distinct from a policy block: nothing was evaluated, so there is no verdict —
# only the absence of one, which is still a refusal.
EXIT_UNSCANNABLE = 5

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    help="JunoGuard — supervision for what your agent installs and spends.",
)
npm_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                      help="npm, guarded.")
pnpm_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                       help="pnpm, guarded.")
yarn_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                       help="yarn, guarded.")
pip_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                      help="pip, guarded.")
app.add_typer(npm_app, name="npm")
app.add_typer(pnpm_app, name="pnpm")
app.add_typer(yarn_app, name="yarn")
app.add_typer(pip_app, name="pip")

_FORWARD_FLAGS = {"allow_extra_args": True, "ignore_unknown_options": True}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"juno {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show the version and exit."
    ),
) -> None:
    pass


def _unreachable(subject: str, exc: JunoUnavailable, consequence: str) -> typer.Exit:
    emit(render_error(subject, exc.detail, consequence), stderr=True)
    return typer.Exit(EXIT_UNAVAILABLE)


def _scan_one(client: JunoClient, package: str, ecosystem: str, version: str | None) -> str:
    """Scan and render one package. Returns the decision."""
    try:
        payload = client.guard_install(package, ecosystem, version)
    except JunoUnavailable as exc:
        raise _unreachable(
            f"{package}  ({ecosystem})",
            exc,
            "The guard could not be consulted, so nothing was installed.\n"
            "Start the JunoGuard gateway, or re-run with JUNO_MOCK=1.",
        )

    decision = payload.get("decision", "flag")
    emit(render_install(payload, package, ecosystem))
    if decision != "allow":
        console.print()
    return decision


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show budget, spend, rate, and open incidents for this project."""
    client = JunoClient()
    try:
        payload = client.status()
    except JunoUnavailable as exc:
        raise _unreachable(
            "project status",
            exc,
            "No budget or incident data is available.\n"
            "Start the JunoGuard gateway, or re-run with JUNO_MOCK=1.",
        )
    emit(render_status(payload))
    if client.mock:
        console.print("\noffline fixtures (JUNO_MOCK=1) — not live gateway data", style=S_DIM)


@app.command()
def scan(
    package: str = typer.Argument(..., help="Package to scan, e.g. express."),
    ecosystem: str = typer.Option("npm", "--ecosystem", "-e", help="npm or pypi."),
    version: str | None = typer.Option(None, "--package-version", help="Exact version to scan."),
) -> None:
    """Scan a package without installing it."""
    decision = _scan_one(JunoClient(), package, ecosystem, version)
    raise typer.Exit(EXIT_BLOCKED if decision == "block" else EXIT_OK)


# Tokens we cannot scan by name: flags, their values, local paths, and direct
# git/http installs. Scoped npm names like @scope/pkg must survive this.
_UNSCANNABLE_PREFIXES = ("-", ".", "/", "~", "file:", "git+", "git:", "http:", "https:")


def _split_tokens(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Partition raw argv into scannable package names and everything else."""
    packages, passthrough = [], []
    for token in tokens:
        (passthrough if token.startswith(_UNSCANNABLE_PREFIXES) else packages).append(token)
    return packages, passthrough


# Our own flags, stripped before anything reaches npm or pip.
_OWN_FLAGS = {"--allow-unscanned", "--reason", "--operator"}


def _extract_override(tokens: list[str]) -> tuple[list[str], dict[str, str | bool]]:
    rest: list[str] = []
    override: dict[str, str | bool] = {"allowed": False}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token not in _OWN_FLAGS:
            rest.append(token)
        elif token == "--allow-unscanned":
            override["allowed"] = True
        else:
            index += 1
            if index < len(tokens):
                override[token.lstrip("-")] = tokens[index]
        index += 1
    return rest, override


def _refuse_unscannable(sources: list[str], manager: str, kind: str) -> typer.Exit:
    """Refuse an install nobody can scan, and say what would authorize it.

    Lockfile installs and path, URL or Git sources cannot be evaluated by name.
    Running the package manager anyway with a warning above it was the gap that
    made "an agent cannot route around the gate" untrue: an agent that reads the
    warning still gets its package.
    """
    console.print()
    console.print("JUNO · REFUSED — NOTHING TO SCAN", style=S_BLOCK)
    console.print()
    if kind == "lockfile":
        console.print(f"No package was named, so {manager} would resolve from a lockfile.")
    else:
        console.print(f"These sources cannot be scanned by name: {', '.join(sources)}")
    console.print(f"{manager} was not run.", style=S_BLOCK)
    console.print()
    console.print("An unscannable source needs a named human to take responsibility:", style=S_DIM)
    console.print(
        f'  juno {manager} install … --allow-unscanned --reason "<why>" --operator "<you>"'
    )
    console.print(
        "The override is recorded against the project. If it cannot be recorded,\n"
        "the install still does not happen.",
        style=S_DIM,
    )
    return typer.Exit(EXIT_UNSCANNABLE)


def _record_override(
    sources: list[str], ecosystem: str, manager: str, override: dict[str, str | bool]
) -> bool:
    reason = override.get("reason")
    operator = override.get("operator") or os.environ.get("JUNO_OPERATOR")
    if not reason or not operator:
        console.print("--allow-unscanned needs both --reason and --operator.", style=S_BLOCK)
        console.print(
            "  (--operator may come from the JUNO_OPERATOR environment variable.)", style=S_DIM
        )
        return False

    client = JunoClient()
    try:
        payload = client.report_unscanned(
            sources, ecosystem, manager, str(reason), str(operator)
        )
    except JunoUnavailable as exc:
        # An unrecordable override is exactly what an attacker would want, so
        # this fails closed rather than proceeding on trust.
        console.print(f"The override could not be recorded: {exc.detail}", style=S_BLOCK)
        console.print(
            f"{manager} was not run. An unlogged override is not an override.", style=S_BLOCK
        )
        return False

    console.print(f"override recorded — {payload.get('reason', 'logged')}", style=S_FLAG)
    if client.mock:
        console.print("JUNO_MOCK=1: nothing was actually recorded anywhere.", style=S_BLOCK)
        return False
    return True


def _forward(ctx: typer.Context, ecosystem: str, argv: list[str], manager: str) -> None:
    # Read raw argv rather than typed arguments so flag order survives intact —
    # `--prefix ./here` must reach npm exactly as the user wrote it.
    tokens, override = _extract_override(list(ctx.args))
    packages, passthrough = _split_tokens(tokens)
    unscanned = [t for t in passthrough if not t.startswith("-")]

    # No package named at all: a lockfile install, which resolves whatever the
    # lockfile says and is therefore entirely unscanned.
    if not packages and not unscanned:
        if not override["allowed"]:
            raise _refuse_unscannable([], manager, "lockfile")
        if not _record_override([f"{manager} lockfile"], ecosystem, manager, override):
            raise typer.Exit(EXIT_UNSCANNABLE)
        _exec([*argv, *tokens], manager)

    if unscanned and not override["allowed"]:
        raise _refuse_unscannable(unscanned, manager, "sources")
    if unscanned and not _record_override(unscanned, ecosystem, manager, override):
        raise typer.Exit(EXIT_UNSCANNABLE)

    client = JunoClient()
    blocked = [p for p in packages if _scan_one(client, p, ecosystem, None) == "block"]

    if blocked:
        console.print(
            f"{manager} was not run. {len(blocked)} of {len(packages)} "
            f"package{'s' if len(packages) != 1 else ''} blocked: {', '.join(blocked)}",
            style=S_BLOCK,
        )
        raise typer.Exit(EXIT_BLOCKED)

    _exec([*argv, *tokens], manager)


def _with_ignored_scripts(cmd: list[str], manager: str) -> list[str]:
    """Lifecycle scripts run with host credentials — keep them off by default."""
    if manager not in {"npm", "pnpm"}:
        return cmd
    if "--ignore-scripts" in cmd or "--no-ignore-scripts" in cmd:
        return cmd
    if len(cmd) < 2:
        return [*cmd, "--ignore-scripts"]
    return [cmd[0], cmd[1], "--ignore-scripts", *cmd[2:]]


def _exec(cmd: list[str], manager: str) -> None:
    gated = _with_ignored_scripts(cmd, manager)
    console.print(f"$ {' '.join(gated)}", style=S_DIM)
    try:
        result = subprocess.run(gated)
    except FileNotFoundError:
        console.print(f"{manager} is not on PATH", style=S_BLOCK)
        raise typer.Exit(EXIT_UNAVAILABLE)
    raise typer.Exit(result.returncode)


@npm_app.command("install", context_settings=_FORWARD_FLAGS)
def npm_install(ctx: typer.Context) -> None:
    """Usage: juno npm install PACKAGE... [NPM FLAGS]

    Scans every named package, then runs the real npm install only if all of
    them come back clean. Flags are passed through to npm untouched.
    """
    _forward(ctx, "npm", ["npm", "install"], "npm")


@npm_app.command("add", context_settings=_FORWARD_FLAGS, hidden=True)
def npm_add(ctx: typer.Context) -> None:
    """Alias for `juno npm install`."""
    _forward(ctx, "npm", ["npm", "install"], "npm")


@pnpm_app.command("install", context_settings=_FORWARD_FLAGS)
def pnpm_install(ctx: typer.Context) -> None:
    """Usage: juno pnpm install PACKAGE... [PNPM FLAGS]

    Scans every named package against the npm ecosystem, then runs the real
    pnpm install only if all of them come back clean.
    """
    _forward(ctx, "npm", ["pnpm", "install"], "pnpm")


@pnpm_app.command("add", context_settings=_FORWARD_FLAGS, hidden=True)
def pnpm_add(ctx: typer.Context) -> None:
    """Alias that preserves `pnpm add` semantics."""
    _forward(ctx, "npm", ["pnpm", "add"], "pnpm")


@pnpm_app.command("i", context_settings=_FORWARD_FLAGS, hidden=True)
def pnpm_i(ctx: typer.Context) -> None:
    """Alias for `juno pnpm install`."""
    _forward(ctx, "npm", ["pnpm", "install"], "pnpm")


@yarn_app.command("add", context_settings=_FORWARD_FLAGS)
def yarn_add(ctx: typer.Context) -> None:
    """Usage: juno yarn add PACKAGE... [YARN FLAGS]

    Scans every named package against the npm ecosystem, then runs the real
    yarn add only if all of them come back clean.
    """
    _forward(ctx, "npm", ["yarn", "add"], "yarn")


@yarn_app.command("install", context_settings=_FORWARD_FLAGS, hidden=True)
def yarn_install(ctx: typer.Context) -> None:
    """Lockfile or named-package yarn install, guarded."""
    _forward(ctx, "npm", ["yarn", "install"], "yarn")


@pip_app.command("install", context_settings=_FORWARD_FLAGS)
def pip_install(ctx: typer.Context) -> None:
    """Usage: juno pip install PACKAGE... [PIP FLAGS]

    Scans every named package, then runs the real pip install only if all of
    them come back clean. Flags are passed through to pip untouched.
    """
    _forward(ctx, "pypi", ["pip", "install"], "pip")


@app.command()
def watch(
    interval: float = typer.Option(2.0, "--interval", "-i", help="Seconds between polls."),
) -> None:
    """Tail the live decision feed."""
    client = JunoClient()
    console.print(
        f"watching {'offline fixtures' if client.mock else client.api_url}"
        "  ·  ctrl-c to stop",
        style=S_DIM,
    )
    console.print()
    try:
        if client.mock:
            _watch_mock(interval)
        else:
            _watch_live(client, interval)
    except KeyboardInterrupt:
        console.print("\nstopped watching", style=S_DIM)


def _watch_mock(interval: float) -> None:
    while True:
        for event in SCRIPT:
            print_event(event)
            time.sleep(max(0.2, interval * 0.6))


def _watch_live(client: JunoClient, interval: float) -> None:
    previous: dict | None = None
    while True:
        try:
            current = client.status()
        except JunoUnavailable as exc:
            print_event(Event("block", "guard", f"gateway unreachable — {exc.detail}"))
            time.sleep(interval)
            continue

        if previous is None:
            emit(render_status(current))
            console.print()
        else:
            for event in diff_status(previous, current):
                print_event(event)
        previous = current
        time.sleep(interval)


def print_event(event: Event) -> None:
    # soft_wrap so a long detail never reflows the aligned columns.
    console.print(to_rich([render_event(event, clock_now())]), soft_wrap=True)
