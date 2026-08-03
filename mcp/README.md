# JunoGuard MCP server

Three tools over stdio. Wire this into Cursor and every package your agent
installs, and every model call it makes, goes through Juno first.

| Tool | What it does |
|---|---|
| `guard_install(package, ecosystem, version)` | Lane A — scan a dependency before it reaches disk |
| `guard_llm(prompt, model, max_output_tokens)` | Lane B — proxied model call under budget and burst policy |
| `guard_status()` | Spend today, budget remaining, rate, open incidents |

---

## Setup

```bash
cd mcp
python3 -m venv .venv
./.venv/bin/pip install -e .
```

Verify it starts:

```bash
JUNO_MOCK=1 ./.venv/bin/python -m juno_mcp
```

It will sit silently waiting for JSON-RPC on stdin. That is correct — press
Ctrl-C.

---

## Connect it to Cursor

Project-scoped config lives at `.cursor/mcp.json`. Prefer the published npm
client when you can; the Python module is for local gateway development:

```json
{
  "mcpServers": {
    "junoguard": {
      "command": "npx",
      "args": ["-y", "@heysalad/junoguard", "mcp"],
      "env": {
        "JUNO_API_URL": "http://localhost:8000",
        "JUNO_PROJECT_KEY": "YOUR_PROJECT_KEY"
      }
    }
  }
}
```

For a checkout of this repo instead of npm:

```json
{
  "mcpServers": {
    "junoguard": {
      "command": "/absolute/path/to/mcp/.venv/bin/python",
      "args": ["-m", "juno_mcp"],
      "env": {
        "JUNO_API_URL": "http://localhost:8000",
        "JUNO_PROJECT_KEY": "YOUR_PROJECT_KEY"
      }
    }
  }
}
```

Then:

1. **Edit `JUNO_PROJECT_KEY`** to a real project key from your gateway. There is
   no default key — an empty value refuses live calls.
2. If you use the Python module, **edit the `command` path** to an absolute
   path to `mcp/.venv/bin/python`. Cursor does not expand `~` or
   `${workspaceFolder}` reliably here.
3. Open the repo in Cursor.
4. **Cursor Settings → MCP & Integrations.** `junoguard` will be listed but
   **disabled** — Cursor does not auto-start a project MCP server the first
   time it sees one, since `.cursor/mcp.json` is untrusted repo content.
   **Toggle it on.** This click is required once per machine; nothing else
   will start the server.
5. It should go green with three tools. If it stays red, hit refresh.
6. In the Agent pane, ask: *"check junoguard status"*. You should get the
   status panel back.

Do this before the demo, not during it.

To prove the block path end to end, ask the agent:

> install @ossprey/test-package

It calls `guard_install`, gets the refusal, and — because the refusal says so
explicitly — stops rather than retrying.

### If it does not connect

- **Red dot, no tools.** The `command` path is wrong or the venv is missing.
  Run the absolute path from a terminal; it must start without a traceback.
  If it prints `refusing to start`, the tool surface no longer matches
  `tools.lock.json` — see [Tool-definition integrity](#tool-definition-integrity).
- **Tools listed but every call returns `JUNO · UNAVAILABLE`.** That is
  correct behaviour with no gateway running. Start the backend, or set
  `"JUNO_MOCK": "1"` in `.cursor/mcp.json` and refresh.
- Cursor caches the server process. After editing `mcp.json`, always hit
  refresh in MCP settings.

---

## Tool-definition integrity

A tool description is not documentation — the model reads it as instruction. So
the two MCP-specific attacks in [docs/threat-landscape.md](../docs/threat-landscape.md) §2.4
apply to us as much as to anyone:

- **Tool poisoning** — instructions hidden in a description no human reads.
- **Rug pull** — a server approved while benign later redefines its tools and
  keeps the approval. Most clients never alert on the change.

Every tool's name, description and schema is hashed into
[`juno_mcp/tools.lock.json`](juno_mcp/tools.lock.json), which is committed. The
server verifies itself against that lock **before it serves anything**, and
refuses to start if the surface has moved:

```bash
python -m juno_mcp --verify        # exit 0 if the surface matches the lock
python -m juno_mcp --update-lock   # re-pin after a reviewed change
```

CI verifies the lock with **Python 3.12** and the hashed deps in
`mcp/requirements.txt`. Re-pin with that same environment or the verify job
will fail even when your local Python version differs.

A refusal exits `78` and names the tool that changed. Cursor shows the server
red — that is the alert. CI runs `--verify` on every push, so drift between the
code and the lock fails the build.

Changing a tool description is therefore a two-part commit: the change, and the
re-pinned lock. The diff is the review.

`JUNO_MCP_ALLOW_UNPINNED=1` serves an unverified surface with a warning. It is
for developing new tools, not for getting past a failure you have not read.

**What this does not do:** an attacker who edits the source *and* the lock in
one reviewed commit is not stopped by a hash. The lock is what makes that
visible in a diff. Signed definitions (ETDI) are the next increment.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `JUNO_API_URL` | `http://localhost:8000` | Gateway base URL |
| `JUNO_PROJECT_KEY` | **none — required for live use** | Sent as `X-Juno-Key` |
| `JUNO_MOCK` | unset (live) | `1` for offline fixtures, no network at all |
| `JUNO_TIMEOUT` | `100` | Seconds before a gateway call gives up |
| `JUNO_MCP_ALLOW_UNPINNED` | unset | `1` serves an unverified tool surface (development only) |

---

## Offline mode

`JUNO_MOCK=1` makes every tool return realistic canned responses with no
network. This is the demo's insurance policy — it works with the gateway down,
half-built, or unplugged.

| Input | Result |
|---|---|
| `@ossprey/test-package` | **block** · malicious · full blast radius |
| `@ossprey/suspicious-package` | **flag** · unknown provenance |
| any other package | **allow** · clean |
| `guard_llm` with `max_output_tokens > 2000` | **block** · per-request cap |
| `guard_llm` with a prompt over ~20k tokens | **flag** · above baseline |
| `guard_llm` otherwise | **allow** · fixture answer, clearly labelled |
| `guard_status` | active project, $0.4231 of $1.00 spent, 1 block, 1 incident |

Fixture verdicts render as *"via Ossprey (offline fixture)"*, never as a live
scan, and the fixture LLM answer says outright that no model was called.

---

## Design notes

**A block is not an error.** The gateway returns HTTP 200 with
`decision: "block"`, and these tools return it as a normal successful result.
Raising would surface in Cursor as a tool failure, and a failed tool is
something an agent retries.

**The return value is the interface.** What these tools return is rendered
straight into the Cursor chat. Weight matches severity: an allow is a single
quiet line because it happens constantly, a flag is a square-bordered caution,
a block is a rounded-border refusal with the full blast radius under it.

**The refusal is written for the agent.** It states that the package was not
installed and that the agent should choose a different dependency — enough to
self-correct instead of retrying blindly or reaching for another package
manager.

**An unreachable guard is not permission.** If the gateway cannot be consulted,
the tools return a `JUNO · UNAVAILABLE` panel shaped like a refusal, telling
the agent not to proceed. Failing open would defeat the point.

`juno_mcp/render.py` and `juno_mcp/client.py` are byte-identical copies of the
files in `cli/juno_cli/`, so both surfaces stay one product. Edit both.
