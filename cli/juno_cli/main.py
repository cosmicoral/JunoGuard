"""`juno` — JunoGuard on the command line.

The forwarders (`juno npm install`, `juno pip install`) are the point: scan
first, and only shell out to the real package manager if every package came
back clean. A block prints the refusal, exits non-zero, and never reaches npm
or pip. So does an unreachable gateway — a guard that cannot be consulted is
not permission to proceed.
"""

from __future__ import annotations

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

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    help="JunoGuard — supervision for what your agent installs and spends.",
)
npm_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                      help="npm, guarded.")
pip_app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                      help="pip, guarded.")
app.add_typer(npm_app, name="npm")
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


def _forward(ctx: typer.Context, ecosystem: str, argv: list[str], manager: str) -> None:
    # Read raw argv rather than typed arguments so flag order survives intact —
    # `--prefix ./here` must reach npm exactly as the user wrote it.
    tokens = list(ctx.args)
    packages, passthrough = _split_tokens(tokens)

    if not packages:
        # A lockfile install, or a path/URL install. Say the run was unguarded
        # rather than implying Juno approved it.
        console.print(f"no scannable package named — running {manager} unguarded", style=S_FLAG)
        _exec([*argv, *tokens], manager)

    unscanned = [t for t in passthrough if not t.startswith("-")]
    if unscanned:
        console.print(
            f"not scanned (path or URL install): {', '.join(unscanned)}", style=S_FLAG
        )

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


def _exec(cmd: list[str], manager: str) -> None:
    console.print(f"$ {' '.join(cmd)}", style=S_DIM)
    try:
        result = subprocess.run(cmd)
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
