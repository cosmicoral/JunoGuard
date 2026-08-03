# `juno` — JunoGuard on the command line

Same guard as the MCP server, same visual language, for humans and CI.

```bash
cd cli
python3 -m venv .venv
./.venv/bin/pip install -e .
```

To get `juno` on your PATH, either add `cli/.venv/bin` to it, or install with
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install --editable ./cli
```

---

## Commands

```bash
juno status                             # budget, spend, rate, incidents
juno scan express                       # scan without installing
juno scan requests -e pypi              # scan a PyPI package
juno npm install react zod              # scan, then run the real npm
juno pip install requests               # scan, then run the real pip
juno watch                              # tail the live decision feed
```

### The forwarder

`juno npm install` is the one that matters. It scans every named package
first, and only shells out to the real `npm` if all of them come back clean.
On a block it prints the refusal, exits non-zero, and never reaches npm.

```bash
$ juno npm install express @ossprey/test-package
✓ juno · allow — express (npm) · clean
╭─ JUNO · BLOCKED ─────────────────────────────────────╮
│  @ossprey/test-package  (npm)                        │
╰──────────────────────────────────────────────────────╯
...
npm was not run. 1 of 2 packages blocked: @ossprey/test-package
$ echo $?
2
```

Flags are passed through to the package manager untouched and in their
original order. Local paths and git/http installs cannot be scanned by name;
the CLI says so out loud rather than implying they were approved.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | allowed |
| `2` | blocked or flagged by policy (flagged installs need `--allow-flagged`) |
| `3` | the guard could not be consulted |
| `4` | no project key configured |
| `5` | source cannot be scanned (lockfile / local / git / URL) without an audited override |

`2`, `3`, and `5` all stop the install — an unreachable or unscanned path is not
permission to proceed. CI should treat them as distinct failures.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `JUNO_API_URL` | `http://localhost:8000` | Gateway base URL |
| `JUNO_PROJECT_KEY` | **none — required for live use** | Sent as `X-Juno-Key` |
| `JUNO_MOCK` | unset (live) | `1` for offline fixtures, no network at all |
| `JUNO_TIMEOUT` | `100` | Seconds before a gateway call gives up |

```bash
JUNO_MOCK=1 juno npm install @ossprey/test-package
```

Offline fixtures are identical to the MCP server's — see
[../mcp/README.md](../mcp/README.md) for the full table. `juno status` prints a
dim reminder when it is showing fixtures rather than live data.

---

## `juno watch`

Live mode polls `GET /v1/guard/status` and emits an event whenever something
moves: a block, a new incident, billable spend, a burst above the rate limit.
That is the only feed the frozen API contract exposes — a first-class
`GET /v1/actions?since=` endpoint would make this richer.

Offline mode replays a scripted run, so the feed still moves with no gateway.

---

`juno_cli/render.py` and `juno_cli/client.py` are byte-identical copies of the
files in `mcp/juno_mcp/`. Edit both.
