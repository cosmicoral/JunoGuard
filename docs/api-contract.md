# JunoGuard API Contract

Frozen interface between the gateway and its clients. The MCP server, the CLI,
and the dashboard are all clients of this. Change it only by agreement — three
sessions are building against it in parallel.

Base URL: `http://localhost:8000`

## Auth

Every guarded call carries a project key:

```
X-Juno-Key: jg_demo_key_cursorhack2026
```

Unknown or missing key → `401`.

## Decision envelope

Every guarded action returns the same envelope. Clients branch on `decision`.

```jsonc
{
  "action_id": "uuid",
  "decision": "allow" | "flag" | "block",
  "reason": "Human-readable, shown directly to the agent.",
  "risk_level": "low" | "medium" | "high" | "critical",
  "project_status": "active" | "suspended"
}
```

A blocked action still returns **HTTP 200**. The block is data, not an error —
clients must not treat it as a failure. Reserve non-2xx for real faults.

---

## `POST /v1/guard/install`

Lane A. Called before a package reaches disk.

**Request**

```jsonc
{
  "package": "@ossprey/test-package",
  "ecosystem": "npm",          // npm | pypi
  "version": null              // optional
}
```

**Response** — decision envelope, plus:

```jsonc
{
  "verdict": {
    "source": "ossprey",       // ossprey | cache | mock
    "severity": "malicious",   // malicious | suspicious | unknown | clean
    "findings": ["Obfuscated postinstall script", "Outbound POST on install"]
  },
  "blast_radius": {
    "credentials_in_scope": ["OPENAI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
    "network_egress": "unrestricted",
    "write_access": "open repository",
    "summary": "full production credential compromise"
  }
}
```

`blast_radius` is null when the decision is `allow`.

---

## `POST /v1/guard/llm`

Lane B. Proxied model call.

**Request**

```jsonc
{
  "prompt": "…",
  "model": "gpt-4o",
  "max_output_tokens": 300
}
```

**Response** — decision envelope, plus:

```jsonc
{
  "answer": "…",               // null when blocked
  "tokens_in": 1204,
  "tokens_out": 287,
  "cost_usd": 0.000431,
  "spend_today_usd": 0.4231,
  "daily_budget_usd": 1.0
}
```

---

## `GET /v1/guard/status`

Cheap. Safe to poll. Lets the agent check its own budget before acting.

```jsonc
{
  "project": "Demo Project",
  "status": "active",
  "spend_today_usd": 0.4231,
  "daily_budget_usd": 1.0,
  "remaining_usd": 0.5769,
  "requests_last_min": 47,
  "max_requests_per_min": 8,
  "blocked_today": 1,
  "open_incidents": 1
}
```

---

## `POST /v1/projects/suspend` · `POST /v1/projects/resume`

The kill switch. Used by the dashboard.

```jsonc
{ "reason": "Manual suspend from dashboard" }
```

Returns the updated project. While suspended, **both lanes** return
`decision: "block"` with `reason: "Project suspended"`.

---

## Live feed — `GET /v1/events/recent` · `GET /v1/events/stream`

The dashboard's **fallback** when Supabase Realtime is not configured. Prefer
Supabase when `VITE_SUPABASE_URL` is set; use this otherwise, so the demo never
depends on a credential arriving. No auth — local only.

Backfill first so the feed is never empty on load:

```jsonc
// GET /v1/events/recent?limit=50
{
  "cursor": 42,
  "events": [ { "seq": 41, "type": "action", "data": { … } } ]
}
```

Then stream from that cursor:

```
GET /v1/events/stream?cursor=42        text/event-stream
```

Three event types. `data` is the JSON payload.

| Event | Payload |
|---|---|
| `action` | The full action row — `id`, `decision`, `reason`, `risk_level`, `action_type`, `target`, `tokens_in`, `tokens_out`, `cost_usd`, `metadata` |
| `incident` | `action_id`, `severity`, `title`, `evidence` |
| `project` | `status`, `reason` — emitted on suspend and resume |

`metadata.blast_radius` on a blocked install carries the inline expand content.

```js
const es = new EventSource("http://localhost:8000/v1/events/stream?cursor=0")
es.addEventListener("action",   e => addRow(JSON.parse(e.data)))
es.addEventListener("project",  e => setStatus(JSON.parse(e.data).status))
```

---

## `GET /health`

```jsonc
{ "status": "ok", "service": "JunoGuard", "mode": "live" }
```

`mode` is `mock` when no Ossprey or provider credentials are configured.

---

## Error shape

```jsonc
{ "error": "invalid_project_key", "detail": "No project matches that key." }
```

`401` bad key · `422` validation · `502` upstream unreachable.
Never `4xx`/`5xx` for a policy block.
