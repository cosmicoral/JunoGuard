#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

tar -czf "$work/npm-canary.tgz" -C "$root/sandbox/fixtures/canary" package
python3 - "$root" "$work/pypi-canary.tar.gz" <<'PY'
import sys
import tarfile
from pathlib import Path

root = Path(sys.argv[1])
destination = sys.argv[2]
source = root / "sandbox" / "fixtures" / "pypi-canary"
with tarfile.open(destination, "w:gz") as archive:
    archive.add(source, arcname="junoguard-pypi-canary-1.0.0")
PY

run_worker() {
  local artifact="$1"
  local destination="$2"
  local image="$3"
  docker run --rm \
    --network=none \
    --read-only \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --pids-limit=64 \
    --memory=256m \
    --cpus=0.5 \
    --user=65534:65534 \
    --tmpfs=/work:rw,nosuid,noexec,size=128m,mode=1777 \
    --tmpfs=/tmp:rw,nosuid,noexec,size=32m,mode=1777 \
    --mount="type=bind,src=$artifact,dst=$destination,readonly" \
    "$image"
}

npm_output="$(run_worker "$work/npm-canary.tgz" /input/package.tgz junoguard-sandbox:latest)"
printf '%s\n' "$npm_output"
printf '%s\n' "$npm_output" | python3 "$root/sandbox/check_canary.py" npm

pypi_output="$(run_worker "$work/pypi-canary.tar.gz" /input/package.tar.gz junoguard-python-sandbox:latest)"
printf '%s\n' "$pypi_output"
printf '%s\n' "$pypi_output" | python3 "$root/sandbox/check_canary.py" pypi
