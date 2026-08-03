# @heysalad/junoguard

> Supervision for AI coding agents. Juno watches what your agent installs and what it spends, and stops it before damage lands.

An AI coding agent is a program with your credentials, your shell, and no
judgement. It will install packages from registries anyone can publish to, run
postinstall scripts with full access to your environment, and make model calls
in a loop until something stops it.

JunoGuard is the something.

## Try it in ten seconds

No gateway, no account, no key — offline fixtures, no network at all:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

## Then wire it into your agent

```bash
npx @heysalad/junoguard init --mock     # offline, to see it working end to end
npx @heysalad/junoguard init            # against your own gateway (see below)
```

That writes MCP config for every AI coding agent it finds on your machine.
From then on, every package your agent tries to install **through Juno** is
checked first.

> **MCP enforcement is advisory.** It works by the agent choosing to call the
> tool. Nothing at the OS or package-manager level stops an agent that shells out
> to `npm install` directly, and this package does not claim otherwise. Use
> `juno wrap on` (PATH shims) or `juno npm|pnpm|yarn install` / `juno pip install`
> in scripts and CI where you control the command. Absolute paths to the real
> package manager still bypass the wrap. Treat the MCP server as policy the
> agent is asked to respect rather than a boundary it cannot cross.
>
> Where Juno *is* consulted it fails closed: an unreachable gateway, an
> unavailable scanner, or a source that cannot be scanned at all all end with the
> package manager not running.

> **This package is a client.** It renders decisions; it does not make them.
> Live use needs a JunoGuard gateway — yours, self-hosted — and a project key.
> There is no hosted service and no default key: shipping one would point your
> installs at someone else's server with a credential you did not choose.
> Without either, every action is refused rather than waved through.

---

## What your agent sees

When it tries to install something malicious:

```text
╭─ JUNO · BLOCKED ─────────────────────────────────────╮
│  @ossprey/test-package  (npm)                        │
╰──────────────────────────────────────────────────────╯

VERDICT    malicious  ·  via Ossprey
           Obfuscated postinstall script
           Outbound POST on install

BLAST RADIUS  if this had installed
           credentials in scope   OPENAI_API_KEY,
                                  SUPABASE_SERVICE_ROLE_KEY
           network egress         unrestricted
           write access           open repository

           → full production credential compromise

This package was not installed. Choose a different dependency.
```

Blocking is table stakes. The blast radius — what would have happened — is
computed from the local client's declared scope, with no LLM involved. The
client sends credential names and workspace capability flags only; secret
values and local filesystem paths never enter the request. Because MCP itself
is advisory, this scope declaration is evidence rather than remote attestation.

That last line matters more than it looks. It is written for the agent, not
just for you: it says plainly that nothing was installed and that it should
pick something else, so the agent self-corrects instead of retrying blindly or
reaching for a different package manager.

An allow is one quiet line, because allows happen constantly:

```text
✓ juno · allow — express (npm) · clean
```

---

## Connect it to your agent

```bash
npx @heysalad/junoguard init              # detect installed agents, configure each
npx @heysalad/junoguard init cursor       # or name them
npx @heysalad/junoguard init --global     # user-level instead of project-level
npx @heysalad/junoguard init --dry-run    # show what would change, write nothing
```

| Agent | Project scope | User scope |
|---|---|---|
| Cursor | `.cursor/mcp.json` | `~/.cursor/mcp.json` |
| Claude Code | `.mcp.json` | `claude mcp add -s user junoguard -- npx -y @heysalad/junoguard mcp` |
| Codex | — | `~/.codex/config.toml` |
| VS Code | `.vscode/mcp.json` | user `mcp.json` |
| Windsurf | — | `~/.codeium/windsurf/mcp_config.json` |

`init` merges into whatever is already there and never replaces an existing
`junoguard` entry without `--force`. If a config file cannot be parsed, it
prints the snippet for you to paste rather than overwriting your settings.

Restart the agent, or refresh its MCP panel, to pick up the change.

Prefer to wire it yourself:

```json
{
  "mcpServers": {
    "junoguard": {
      "command": "npx",
      "args": ["-y", "@heysalad/junoguard", "mcp"]
    }
  }
}
```

### Tools

| Tool | Purpose |
|---|---|
| `guard_install(package, ecosystem, version)` | Scan a dependency before it reaches disk |
| `guard_llm(prompt, model, max_output_tokens)` | Proxied model call under budget and burst policy |
| `guard_status()` | Spend today, budget remaining, rate, open incidents |

`guard_status` matters: the agent can check its own budget before a run of
expensive work, rather than discovering the limit by hitting it.

### Tool-definition integrity

A tool description is not documentation — your model reads it as instruction.
Which makes an MCP server a target twice over:

- **Tool poisoning** — instructions hidden in a description no human reads.
- **Rug pull** — a server you approved while benign later redefines its tools
  and keeps your approval. Most clients never tell you.

We are an MCP server, so we hold ourselves to it. Every tool's name,
description and JSON Schema is hashed into `tools.lock.json`, which ships in
this package. The server verifies itself against that lock **before it serves
anything** and refuses to start if the surface has moved:

```bash
npx -y @heysalad/junoguard mcp --verify
```

Exit `0` means the tools your agent is about to be given are byte-for-byte the
ones in our repository. A mismatch exits `78`, names the tool that changed, and
the server does not start — your client shows it red, which is the alert. Our
CI runs the same check on every push, so the code and the lock cannot drift.

You can run that command against your installed copy any time. It is the
question "is this still the server I approved?", and it has an answer.

**What it does not do:** an attacker who changes the source *and* the lock in
one reviewed commit is not stopped by a hash. The lock is what makes that
visible in a diff. Signed definitions are the next step.

---

## The CLI

```bash
npm i -g @heysalad/junoguard
```

```bash
juno status                    # budget, spend, rate limit, incidents
juno scan express              # scan without installing
juno scan requests -e pypi     # scan a PyPI package
juno npm install react zod     # scan, then run the real npm
juno pnpm add react zod        # scan, then run the real pnpm
juno yarn add react zod        # scan, then run the real yarn
juno pip install requests      # scan, then run the real pip
juno wrap on                   # PATH shims so bare installs hit the gate
juno init cursor               # MCP config + Cursor shell install hook
juno watch                     # tail the live decision feed
```

`juno npm|pnpm install` adds `--ignore-scripts` by default so an allowed
package still cannot run host lifecycle scripts unless you pass
`--no-ignore-scripts` deliberately. Flagged packages are refused for
unattended installs; proceed only with
`--allow-flagged --reason … --operator …`.

The forwarder is the one that matters. It scans every named package and only
shells out to the real package manager if all of them come back clean:

```console
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

Flags reach the package manager untouched and in their original order. Local
paths and git/http installs cannot be scanned by name, and the CLI says so out
loud rather than implying they were approved.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | allowed (or flagged — flags do not stop the install) |
| `2` | blocked by policy |
| `3` | the guard could not be consulted |
| `4` | no project key configured |

These are deliberately distinct: "Juno said no", "Juno was down" and "you never
set Juno up" are three different problems. All of them stop the install.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `JUNO_PROJECT_KEY` | **none — required for live use** | Sent as `X-Juno-Key` |
| `JUNO_API_URL` | `http://localhost:8000` | Gateway base URL |
| `JUNO_MOCK` | unset | `1` for offline fixtures — no network, no key needed |
| `JUNO_TIMEOUT` | `100` | Seconds before a gateway call gives up |
| `JUNO_MCP_ALLOW_UNPINNED` | unset | `1` serves an unverified tool surface (development only) |

There is deliberately no default project key. Without one, every surface
returns a `JUNO · NOT CONFIGURED` refusal and the CLI exits `4` — it does not
fall back to running your package manager unguarded.

### Running a gateway

The gateway is the policy engine: Ossprey verdicts, budgets, rate limits, the
kill switch. It is a separate FastAPI service in the
[project repository](https://github.com/cosmicoral/TokenGuard).

```bash
git clone https://github.com/cosmicoral/TokenGuard
cd TokenGuard/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add Supabase and Ossprey credentials
uvicorn app.main:app --reload
```

Then point this package at it:

```bash
export JUNO_API_URL=http://localhost:8000
export JUNO_PROJECT_KEY=<your project key>
npx @heysalad/junoguard init
```

### Offline mode

`JUNO_MOCK=1` makes every surface return realistic canned responses with no
network — useful for trying the tool, and for demos where the gateway may not
be up.

| Input | Result |
|---|---|
| `@ossprey/test-package` | **block** · malicious · full blast radius |
| `@ossprey/suspicious-package` | **flag** · unknown provenance |
| any other package | **allow** · clean |
| `guard_llm` with `max_output_tokens > 2000` | **block** · per-request cap |
| `guard_llm` otherwise | **allow** · fixture answer, clearly labelled |

Fixture verdicts render as *"via Ossprey (offline fixture)"*, never as a live
scan, and the fixture model answer says outright that no model was called.

---

## Design

**A block is not an error.** The gateway returns HTTP 200 with
`decision: "block"`, and the MCP tools return it as a normal successful result.
Throwing would surface as a tool failure, and a failed tool is something an
agent retries.

**The return value is the interface.** What the tools return is rendered
straight into the agent's chat, so visual weight matches severity: an allow is
a single quiet line, a flag is a square-bordered caution, a block is a
rounded-border refusal with the blast radius under it.

**An unreachable guard is not permission.** If the gateway cannot be consulted,
every surface returns a refusal-shaped `JUNO · UNAVAILABLE` panel and the CLI
exits non-zero without running your package manager. Failing open would defeat
the point.

**No LLM on the hot path.** Package verdicts, token accounting, cost, rate
limiting and budget enforcement are all deterministic. We do not spend AI
tokens to protect AI tokens.

---

Requires Node 18+. Talks to a JunoGuard gateway; see the
[project README](https://github.com/cosmicoral/TokenGuard) for running one.

MIT.
