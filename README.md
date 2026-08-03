# JunoGuard

> The supervision layer for AI coding agents. Juno watches what your agent installs, what it spends, and what it can reach — and stops it before damage lands.

**Built for the Cursor Cybersecurity London Hackathon — 1 August 2026, London.**

[![npm](https://img.shields.io/npm/v/@heysalad/junoguard?color=e3b341&label=%40heysalad%2Fjunoguard)](https://www.npmjs.com/package/@heysalad/junoguard)
[![node](https://img.shields.io/node/v/@heysalad/junoguard?color=3fb950)](https://www.npmjs.com/package/@heysalad/junoguard)
[![license](https://img.shields.io/npm/l/@heysalad/junoguard?color=8a929c)](packages/junoguard/LICENSE)

```bash
# See a real block, with no gateway and no key
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package

# Wire it into every AI coding agent on your machine
npx @heysalad/junoguard init
```

`init` detects Cursor, Claude Code, Codex, VS Code and Windsurf, and writes the
MCP config each one expects. Full docs: **[packages/junoguard](packages/junoguard)**.

---

## Meet Juno

**Juno** is the agent inside JunoGuard. She sits between your AI coding agent and the outside world, evaluates every action it tries to take, and decides: **allow, flag, or block**.

The name is not decoration. Juno *Moneta* — "Juno the Warner" — was the goddess whose temple on the Capitoline minted Rome's coins. The root *monere*, to warn, gives us both **money** and **monitor**. A guard that watches spend and raises warnings has no better namesake.

---

## The Problem

An AI coding agent is a program with your credentials, your shell, and no judgement.

Give Cursor or Claude Code a task and it will happily:

- install packages you have never heard of, from registries anyone can publish to
- run postinstall scripts with full access to your environment
- read whatever a dependency's README tells it to read
- make model calls in a loop until something stops it

Each of those is a live attack surface, and they chain:

```text
Prompt injection hidden in a dependency README
        |
        v
Agent installs a malicious package
        |
        v
Postinstall script reads the environment
        |
        v
API keys, cloud credentials, and source exfiltrated
        |
        v
Stolen keys burn budget until someone notices the bill
```

Nothing in the default developer setup interrupts that chain. Registry trust is implicit. The agent's effective permissions are invisible. Provider billing dashboards show the damage only after the requests have already happened.

JunoGuard is the interrupt.

---

## The Solution

Every action an agent takes flows through one gate.

```text
        AI Coding Agent  (Cursor / Claude Code)
                  |
                  |  MCP
                  v
        +---------------------+
        |        JUNO         |
        |   decision engine   |
        +---------------------+
           |               |
   Lane A  |               |  Lane B
  supply   |               |  tokens
   chain   |               |  & cost
           v               v
   Ossprey scan      Policy engine
                     Cost calculator
           |               |
           +-------+-------+
                   |
                   v
        allow  /  flag  /  block
                   |
                   v
        Supabase: actions, incidents, policy
                   |
                   v
             Live dashboard
```

Both lanes answer the same question — *should this action be allowed to proceed?* — so both share one policy object, one incident table, and one kill switch.

---

## Core Principle

**We do not spend AI tokens to protect AI tokens.**

Every hot-path decision is deterministic: package verdicts, token estimation, cost calculation, rate limiting, budget enforcement, project suspension.

```text
Additional LLM calls on the hot path:  0
```

There is no AI on the hot path or in sandbox analysis. When the optional
sandbox is enabled, non-clean npm and PyPI packages take a bounded,
deterministic container detonation step before a proceedable flag is returned.
The package code runs in an ecosystem-specific isolated worker image, never in
the gateway process.

Two execution backends exist for that detonation, and they answer different
questions. The **local Docker** worker (`sandbox/`) runs before the verdict is
returned, so its evidence can turn a suspicious package into a block — but it
needs a Docker daemon wherever the gateway runs. The **Modal** worker
(`modal_worker/`) runs after the response on the cold path, so it cannot prevent the
install it reports on; what it buys is isolation off the gateway's own host, no
Docker dependency, and evidence that can retroactively block a package that
already proceeded. See
[What is actually implemented](#what-is-actually-implemented).

---

## What Juno Does

### Lane A — Supply chain

Every package the agent tries to install is intercepted **before** it reaches disk.

- Pre-install interception over MCP — **advisory**: it depends on the agent
  calling the tool. `juno npm|pnpm|yarn|pip …` closes the gap for installs that
  go through the CLI. `juno wrap on` adds project-local PATH shims so bare
  package-manager invocations hit the same gate; absolute paths to the real
  binary still bypass. `juno init` also writes Cursor `beforeShellExecution`
  and Claude Code `PreToolUse` Bash hooks that deny ungated installs inside
  those agent shells. A kernel boundary that every agent genuinely cannot step
  around is not implemented.
- [Ossprey](https://ossprey.com) malware verdict
- Registry-backed CycloneDX 1.6 SBOM for the exact package coordinate
- Optional Docker detonation of non-clean npm lifecycle scripts and PyPI
  build/install/import paths with no network, no capabilities, bounded
  resources, and no project or credential mounts
- Block on known-malicious, and on unknown by default
- Sources that cannot be scanned — lockfile installs, local archives, Git and
  URL sources — are **refused**, not waved through. Proceeding takes a named
  operator override, and the override is recorded as an audited gap in coverage.
- **Structured refusal** returned to the agent — a machine-readable reason, so it self-corrects to a safe alternative instead of retrying blindly
- A scanner outage is refused, not downgraded to a warning: no verdict means no install

### Lane B — Tokens and cost

A hijacked agent burns tokens abnormally. Burst detection here is exfiltration telemetry, not a billing feature.

- Provider API keys held server-side, never reaching the client
- Input and output token accounting
- Cost calculation from a local pricing table
- Per-request and daily budget caps
- Maximum tokens per request
- Request rate limiting
- Burst and rate limiting

### Blast radius

Blocking is table stakes. Juno tells you **what would have happened**:

```text
@ossprey/test-package — BLOCKED

Postinstall script would have executed with access to:
  - OPENAI_API_KEY, SUPABASE_SERVICE_ROLE_KEY, AWS_PROFILE=prod
  - Outbound network: unrestricted
  - Write access to the open repository

Estimated blast radius: full production credential compromise
```

Computed from the local client’s declared scope. JunoGuard clients send only
credential names and workspace capability flags — never secret values or local
paths. The declaration is useful evidence, not remote attestation. No LLM
required.

### Oversight and response

- Incident records with severity, evidence, and timeline
- Expandable CycloneDX SBOM, sandbox observations, and blast-radius evidence in
  the live install feed
- **Kill switch** — suspend a project instantly; both lanes go dark; manual reset required
- Live dashboard over Supabase Realtime
- Spend and blocks in a single view

---

## Stack

| Layer | Technology |
|---|---|
| Agent interface | MCP server (Cursor, Claude Code) |
| Gateway | Python, FastAPI, Pydantic, HTTPX |
| Supply-chain scanning | Ossprey |
| Database, auth, realtime | Supabase (PostgreSQL, RLS, Realtime) |
| Dashboard | React, Vite |

---

## What Is Actually Implemented

Every present-tense claim above maps to a code path. This table says which, and
what is still an intention.

| Capability | State | Where |
|---|---|---|
| Pre-install verdicts, block/flag/allow | **live** | `backend/app/risk.py`, `ossprey.py` |
| Scanner outage refuses the install | **live** | `ossprey.py`, `risk.py` |
| Unscannable sources refused, audited override | **live** | `packages/junoguard/src/cli.ts`, `POST /v1/guard/unscanned` |
| Guarded npm / pnpm / yarn / pip forwarders | **live** | `juno npm|pnpm|yarn …`, `juno pip …` in TypeScript and Python CLIs |
| Flagged installs refused without override | **live** | CLI/wrap only proceed on `allow`; `--allow-flagged` records an audited exception |
| Token, per-request and daily budget caps | **live** | `risk.py`, atomic reserve in `store.py` |
| Burst / rate limiting | **live** | `store.reserve`, SQL `reserve_action` |
| Kill switch with operator roles and audit | **live** | `auth.py`, `control_events` |
| Live dashboard, install evidence, signed-in product navigation, Supabase Realtime and SSE | **live** | `frontend/`, `POST /v1/events/token` |
| Ossprey verdicts with an API key | **live** | `backend/app/ossprey.py` — OSSBOM submit, poll to a verdict, block before the install lands. The first scan of a version takes seconds to about a minute and is then cached; one that outruns the budget is refused as unscanned, never allowed |
| Ossprey verdicts without an API key | **mock** | `ossprey._mock_verdict` — deterministic fixtures |
| Model provider calls without a key | **mock** | `provider.MOCK_ANSWER` |
| Agent-scoped blast radius | **live (client-declared)** | Clients report names-only local scope; `backend/app/blast.py` enriches it with scanner and sandbox evidence |
| Registry-backed CycloneDX SBOM generation | **live** | `backend/app/sbom.py`; runs for mock and Ossprey verdicts, fail-closed on clean installs when the registry cannot identify the package |
| Sandbox detonation of non-clean npm and PyPI packages, local Docker | **live (opt-in)** | `backend/app/sandbox.py`, hardened images in `sandbox/`; gates the verdict |
| Sandbox detonation on Modal, cold path | **live** | `modal_worker/detonate.py`, reached from a hosted gateway with `PUBLIC_BASE_URL` set; a blocked install's report lands on the action's `metadata.detonation` and on the linked incident's `evidence` |
| PATH wrap for bare package-manager installs | **live (opt-in)** | `juno wrap on` → `.junoguard/bin` shims; absolute paths still bypass |
| Cursor shell install gate | **live (opt-in via init)** | `beforeShellExecution` deny for ungated npm/pnpm/yarn/pip installs; `failClosed: true` |
| Claude Code shell install gate | **live (opt-in via init)** | `PreToolUse` Bash deny for ungated installs via the same `juno hook shell` classifier |
| Guarded JS installs default to `--ignore-scripts` | **live** | `juno npm|pnpm …` adds `--ignore-scripts` unless overridden |
| Tool-definition integrity on our own MCP surface | **live** | Names, descriptions and schemas hashed into a shipped `tools.lock.json`; the server verifies itself before serving and refuses to start on a mismatch (`juno mcp --verify`, exit `78`). CI checks both the TypeScript and Python servers |
| Kernel / package-manager hook an agent cannot bypass | **planned** | Absolute host escapes and agents without a shell hook remain outside this boundary |

`GET /health` reports `mode: mock` whenever the Ossprey or provider credentials
are absent, so the running system says which of these it is.

---

## MCP Surface

What the agent sees:

| Tool | Purpose |
|---|---|
| `guard_install(package, ecosystem)` | Supply-chain lane — scan and gate an install |
| `guard_llm(prompt, model, max_tokens)` | Cost and abuse lane — proxied model call |
| `guard_status()` | Spend today, budget remaining, project status |

`guard_status` matters: the agent can check its own budget before acting, rather than discovering the limit by hitting it.

These three definitions are hash-pinned in `tools.lock.json`. The server checks
itself against that lock before it serves anything and refuses to start if the
surface has moved — a tool description is an instruction to the model, so a
silent change to one is a silent change to agent behaviour. Run
`juno mcp --verify` against your installed copy to ask whether it is still the
server you approved. See [docs/threat-landscape.md](docs/threat-landscape.md) §2.4.

Shipped as [`@heysalad/junoguard`](https://www.npmjs.com/package/@heysalad/junoguard) —
one npm package containing both the MCP server and the `juno` CLI:

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

The package is a client. It renders decisions; the gateway makes them. Live use
needs a running gateway and a project key — there is no default key, and an
unconfigured guard refuses rather than waving actions through.

---

## Repository layout

| Path | What it is |
|---|---|
| `packages/junoguard/` | The published npm package — MCP server + `juno` CLI (TypeScript) |
| `backend/` | The gateway: policy engine, budgets, kill switch (FastAPI) |
| `frontend/` | Landing page and live dashboard (React, Vite) |
| `mcp/`, `cli/` | The original Python implementations, kept working |
| `docs/api-contract.md` | The frozen client/gateway contract |

---

## Data Model

```text
projects        id, name, status (active | suspended)

policies        project_id, daily_budget_usd, per_request_budget_usd,
                max_request_tokens, max_requests_per_min, block_severity

agent_actions   id, project_id, action_type (llm_call | package_install),
                target, decision, reason, risk_level,
                tokens_in, tokens_out, cost_usd, created_at

incidents       id, project_id, action_id, severity, title,
                evidence (jsonb), status (open | resolved), created_at
```

One action table for both lanes — which is what lets a single kill switch cover everything an agent can do.

---

## Quick Start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add Supabase and Ossprey credentials
uvicorn app.main:app --reload
```

```bash
# Frontend — OAuth sign-in and live data use Supabase; FastAPI is optional
cd frontend
npm install
npm run dev          # configure frontend/.env.local for dashboard access
```

Google/GitHub sign-in and protected dashboard access require
`VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. Those same variables switch
the data feed from mock mode to Supabase Realtime. See
[`frontend/README.md`](frontend/README.md) for OAuth setup and demo controls.

Health check:

```bash
curl http://localhost:8000/health
```

Optional npm and PyPI detonation requires Docker and is off by default. Build
both pinned workers:

```bash
docker build -t junoguard-sandbox:latest sandbox
docker build -f sandbox/Dockerfile.python \
  -t junoguard-python-sandbox:latest sandbox
```

Then set `SANDBOX_ENABLED=true` on a gateway using a dedicated or rootless
Docker daemon. See
[`sandbox/README.md`](sandbox/README.md) for the boundary and operational limits.

---

## Hackathon Notes

Built against the Cursor Cybersecurity London Hackathon themes of AI security, autonomous security operations, credential protection, human oversight, and real-world developer tooling.

Cost figures are estimates derived from a configured pricing table. They are not provider invoices.

Mock provider mode is the default, so the system runs end to end without a live model key.

---

## Status

Hackathon prototype. Built in one day.

Formerly TokenGuard — the cost-control engine survives as Lane B.

---

**JunoGuard** — your agent moves fast. Juno makes sure it does not move off a cliff.
