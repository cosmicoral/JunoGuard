# JunoGuard

> The supervision layer for AI coding agents. Juno watches what your agent installs, what it spends, and what it can reach — and stops it before damage lands.

**Built for the Cursor Cybersecurity London Hackathon — 1 August 2026, London.**

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
   Modal sandbox     Cost calculator
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

AI runs on the **cold path** only — Modal sandboxes and analyses packages that have already been flagged, out of band, where latency and cost do not matter. Fast and free where it has to be, deep where it is worth it.

---

## What Juno Does

### Lane A — Supply chain

Every package the agent tries to install is intercepted **before** it reaches disk.

- Pre-install interception over MCP — the agent cannot route around it
- [Ossprey](https://ossprey.com) SBOM generation and malware verdict
- Block on known-malicious, flag on unknown
- **Structured refusal** returned to the agent — a machine-readable reason, so it self-corrects to a safe alternative instead of retrying blindly
- Flagged packages detonated in a **Modal** sandbox for deeper analysis, off the hot path

### Lane B — Tokens and cost

A hijacked agent burns tokens abnormally. Burst detection here is exfiltration telemetry, not a billing feature.

- Provider API keys held server-side, never reaching the client
- Input and output token accounting
- Cost calculation from a local pricing table
- Per-request and daily budget caps
- Maximum tokens per request
- Request rate limiting
- Burst and anomaly detection

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

Computed from the agent's actual scope. No LLM required.

### Oversight and response

- Incident records with severity, evidence, and timeline
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
| Sandboxed analysis | Modal |
| Database, auth, realtime | Supabase (PostgreSQL, RLS, Realtime) |
| Dashboard | React, Vite |

---

## MCP Surface

What the agent sees:

| Tool | Purpose |
|---|---|
| `guard_install(package, ecosystem)` | Supply-chain lane — scan and gate an install |
| `guard_llm(prompt, model, max_tokens)` | Cost and abuse lane — proxied model call |
| `guard_status()` | Spend today, budget remaining, project status |

`guard_status` matters: the agent can check its own budget before acting, rather than discovering the limit by hitting it.

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
# Frontend — Google sign-in and live data use Supabase; FastAPI is optional
cd frontend
npm install
npm run dev          # configure frontend/.env.local for dashboard access
```

Google sign-in and protected dashboard access require `VITE_SUPABASE_URL` and
`VITE_SUPABASE_ANON_KEY`. Those same variables switch the data feed from mock
mode to Supabase Realtime. See [`frontend/README.md`](frontend/README.md) for
OAuth setup and demo controls.

Health check:

```bash
curl http://localhost:8000/health
```

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
