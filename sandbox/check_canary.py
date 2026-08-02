"""Validate structured output from a sandbox boundary canary."""

from __future__ import annotations

import json
import sys

PREFIX = "JUNO_SANDBOX_RESULT="


def main() -> None:
    ecosystem = sys.argv[1]
    lines = sys.stdin.read().splitlines()
    payload = next((line[len(PREFIX) :] for line in lines if line.startswith(PREFIX)), None)
    if payload is None:
        raise SystemExit("sandbox did not emit structured evidence")
    evidence = json.loads(payload)
    if evidence.get("status") != "completed":
        raise SystemExit(f"sandbox canary failed: {evidence}")

    lifecycles = {
        item.get("lifecycle") for item in evidence.get("scripts_executed", [])
    }
    files = evidence.get("files_created", [])
    if ecosystem == "npm":
        if "postinstall" not in lifecycles:
            raise SystemExit("npm canary did not execute postinstall")
        if "sandbox-canary-created.txt" not in files:
            raise SystemExit("npm canary file creation was not observed")
    elif ecosystem == "pypi":
        required = {"build", "install", "import:junoguard_canary"}
        if not required.issubset(lifecycles):
            raise SystemExit("PyPI canary did not complete build, install, and import")
        if not {"canary-build.txt", "canary-import.txt"}.issubset(files):
            raise SystemExit("PyPI canary file creation was not observed")
    else:
        raise SystemExit(f"unknown canary ecosystem: {ecosystem}")


if __name__ == "__main__":
    main()
