#!/usr/bin/env python3
"""JunoGuard demo driver.

One keystroke per beat, so the demo is not five terminal commands typed under
pressure. Run `python demo.py story` for the full narrative.

    python demo.py seed      backfill history so the feed is not empty
    python demo.py story     the full attack narrative, timed
    python demo.py burst     the Lane B beat on its own
    python demo.py reset     resume the project and start clean
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8000"
KEY = "jg_demo_key_cursorhack2026"

DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
GREY = "\033[90m"
OFF = "\033[0m"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Juno-Key": KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read())
    except urllib.error.URLError as exc:
        die(f"Gateway unreachable at {API} — {exc}")
    return {}


def die(message: str) -> None:
    print(f"{RED}✕ {message}{OFF}")
    print(f"{GREY}  start it with: cd backend && uvicorn app.main:app{OFF}")
    sys.exit(1)


def say(text: str = "") -> None:
    print(text)


def beat(seconds: float = 1.2) -> None:
    time.sleep(seconds)


def rule(label: str = "") -> None:
    say(f"\n{GREY}{'─' * 62}{OFF}")
    if label:
        say(f"{BOLD}{label}{OFF}\n")


def show(result: dict, label: str) -> None:
    decision = result["decision"]
    colour = {"allow": GREEN, "flag": YELLOW, "block": RED}[decision]
    mark = {"allow": "✓", "flag": "!", "block": "✕"}[decision]
    say(f"  {colour}{mark} {decision.upper():<6}{OFF} {label}")
    if decision != "allow":
        say(f"    {GREY}{result['reason']}{OFF}")


def show_blast(result: dict) -> None:
    radius = result.get("blast_radius")
    if not radius:
        return
    creds = radius["credentials_in_scope"]
    total = radius["credentials_total"]
    say(f"\n  {BOLD}BLAST RADIUS{OFF}  {GREY}if this had installed{OFF}")
    if creds:
        shown = ", ".join(creds)
        extra = f" (+{total - len(creds)} more)" if total > len(creds) else ""
        say(f"    credentials    {RED}{shown}{extra}{OFF}")
    if radius["cloud_access"]:
        say(f"    cloud          {RED}{', '.join(radius['cloud_access'])}{OFF}")
    say(f"    network        {radius['network_egress']}")
    say(f"    write access   {radius['write_access']}")
    say(f"\n    {RED}{BOLD}→ {radius['summary']}{OFF}")


# --- beats ------------------------------------------------------------------


def cmd_seed(count: int = 28) -> None:
    result = call("POST", f"/v1/demo/seed?count={count}")
    say(f"{GREEN}✓{OFF} seeded {result['seeded']} historical actions")


def cmd_reset() -> None:
    call("POST", "/v1/projects/resume")
    say(f"{GREEN}✓{OFF} project resumed")


def cmd_burst() -> None:
    rule("LANE B — a hijacked agent burns tokens abnormally")

    # The window is the last 60 seconds. Running this straight after `story`
    # trips the limiter almost immediately, which undersells the build-up.
    warm = call("GET", "/v1/guard/status")["requests_last_min"]
    if warm > 2:
        say(f"  {YELLOW}! {warm} requests already in the 60s window.{OFF}")
        say(f"  {GREY}  Wait a minute for a clean build-up before demoing.{OFF}\n")

    for i in range(12):
        result = call(
            "POST",
            "/v1/guard/llm",
            {"prompt": "summarise this file", "model": "gpt-4o"},
        )
        show(result, f"llm_call  gpt-4o  {GREY}#{i + 1}{OFF}")
        if result["decision"] == "block":
            beat(0.35)
            break
        beat(0.25)
    say(f"\n  {GREY}Burst detection is not a billing feature. This is the{OFF}")
    say(f"  {GREY}signature of an agent that is no longer under control.{OFF}")


def cmd_story() -> None:
    health = call("GET", "/health")
    say(f"{GREY}JunoGuard {health['status']} · mode: {health['mode']}{OFF}")

    rule("NORMAL DEVELOPMENT")
    for pkg in ["zod", "hono"]:
        show(call("POST", "/v1/guard/install", {"package": pkg}), f"install  {pkg}")
        beat(0.7)
    show(
        call("POST", "/v1/guard/llm", {"prompt": "Add error handling to the upload route"}),
        "llm_call  gpt-4o",
    )
    beat(1.6)

    rule("THE AGENT HITS AN INJECTED DEPENDENCY")
    say(f"  {GREY}A README in the dependency tree instructs the agent to{OFF}")
    say(f"  {GREY}install a helper package. The agent complies.{OFF}\n")
    beat(1.8)

    result = call("POST", "/v1/guard/install", {"package": "@ossprey/test-package"})
    show(result, "install  @ossprey/test-package")
    beat(0.9)
    show_blast(result)
    beat(2.2)

    rule("AUTOMATIC RESPONSE")
    status = call("GET", "/v1/guard/status")
    say(f"  project        {RED}{BOLD}{status['status'].upper()}{OFF}")
    say(f"  blocked today  {status['blocked_today']}")
    say(f"  open incidents {status['open_incidents']}")
    beat(1.4)

    say(f"\n  {GREY}Both lanes are now dark. The same gate covers everything:{OFF}\n")
    show(call("POST", "/v1/guard/llm", {"prompt": "hello"}), "llm_call  gpt-4o")
    beat(0.6)
    show(call("POST", "/v1/guard/install", {"package": "react"}), "install  react")

    rule()
    say(f"  {BOLD}One agent. Two attack surfaces. One kill switch.{OFF}")
    say(f"  {GREY}python demo.py reset{OFF} to restore service.\n")


COMMANDS = {
    "seed": cmd_seed,
    "story": cmd_story,
    "burst": cmd_burst,
    "reset": cmd_reset,
}


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "story"
    if name not in COMMANDS:
        say(f"usage: python demo.py [{' | '.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[name]()
