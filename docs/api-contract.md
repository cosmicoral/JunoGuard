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
    "severity": "malicious",   // malicious | suspicious | unknown | clean | unavailable
    "available": true,         // false when no scan happened at all
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

**Scanner unavailable.** `severity: "unknown"` means nobody has established a
reputation for the package. `severity: "unavailable"` with `available: false`
means no scan happened — a JunoGuard outage, not a finding. That is never
gradeable against the policy threshold: the install is refused, and the response
carries a retry contract rather than a proceedable flag.

```jsonc
{
  "decision": "block",
  "review_required": true,
  "retry_after_seconds": 60
}
```

---

## `POST /v1/guard/unscanned`

Records an operator's override for an install that **cannot** be scanned:
lockfile resolutions, local archives, and direct Git or URL sources.

Clients refuse these by default and do so locally — they have to, because this
gateway may be unreachable and a guard that cannot be consulted is not
permission to proceed. This endpoint exists so the exception a human makes is
auditable. **If the override cannot be recorded here, the client must refuse**;
an override nobody can find later is indistinguishable from no policy.

```jsonc
{
  "sources": ["./vendor/thing.tgz"],
  "ecosystem": "npm",
  "manager": "npm",
  "reason": "vendored tarball reviewed by hand",   // min 8 chars
  "operator": "Peter Machona"
}
```

Returns the decision envelope with `decision: "flag"`, `risk_level: "high"`, and
raises an incident so the gap in coverage appears in review.

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

Optional `Idempotency-Key` header. Replaying a key returns the original
response with `"idempotent_replay": true` and does not call the provider again,
so a client retry cannot buy a second completion.

Rate and daily-budget enforcement is atomic: the request reserves its
worst-case cost before the provider is called, and the reservation counts
toward both limits until the action is recorded. At most
`max_requests_per_min` concurrent requests reach the provider.

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

`spend_today_usd` counts **every charged action**, not only allowed ones. A
`flag` is proceedable — the provider is called and the money is spent — so a
flagged call advances the daily total exactly like an allowed one. Blocked calls
cost nothing and do not.

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

**These are human-control endpoints and they do not accept `X-Juno-Key`.** An
agent key lives in agent configs and CI environments; it authorizes asking for a
decision, not taking a project offline. A valid agent key gets `401` here.

Send an operator identity instead:

| Credential | Header | Use |
|---|---|---|
| Supabase session | `Authorization: Bearer <access token>` | Normal deployments; the role is read from `project_members` |
| Operator token | `X-Juno-Operator: <OPERATOR_TOKEN>` | Local deployments with no Supabase to sign into |

Roles are ordered `viewer < operator < owner`. **Suspend** needs `operator`.
**Resume** needs `owner` — stopping something should be easy and reversing it
deliberate. Anything less gets `403`.

```jsonc
{
  "reason": "Manual suspend from dashboard",
  "project_id": "uuid"        // optional only on a single-project deployment
}
```

Returns the **public project view** — never the agent key or its hash:

```jsonc
{
  "id": "uuid",
  "name": "Demo Project",
  "status": "suspended",
  "suspended_at": "2026-08-01T14:22:07Z",
  "suspended_reason": "Manual suspend from dashboard",
  "api_key_prefix": "jg_demo_key",
  "actor": {
    "actor_kind": "user",         // user | operator_token
    "actor_id": "auth.users uuid",
    "actor_role": "owner",
    "actor_email": "operator@example.com"
  }
}
```

While suspended, **both lanes** return `decision: "block"` with
`reason: "Project suspended"`.

---

## Live feed — `GET /v1/events/recent` · `GET /v1/events/stream`

The dashboard's **fallback** when Supabase Realtime is not configured. Prefer
Supabase when `VITE_SUPABASE_URL` is set; use this otherwise, so the demo never
depends on a credential arriving.

**Authenticated and project-scoped.** Both endpoints return only the caller's
own events — incident evidence carries credential names and blast-radius
detail. Anonymous requests get `401`.

`/v1/events/recent` takes the usual `X-Juno-Key`. `EventSource` cannot send
headers, so the stream takes a short-lived token instead of the project key —
a long-lived credential does not belong in a URL that lands in logs, proxies and
browser history:

```jsonc
// POST /v1/events/token          (X-Juno-Key)
{ "token": "…", "expires_in": 300 }
```

The token authorizes reading one project's feed for that window. When it
expires the stream emits an `expired` event and closes; the client takes a fresh
token and reconnects from its last cursor.

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
GET /v1/events/stream?cursor=42&token=…        text/event-stream
```

Three event types. `data` is the JSON payload.

| Event | Payload |
|---|---|
| `action` | The full action row — `id`, `decision`, `reason`, `risk_level`, `action_type`, `target`, `tokens_in`, `tokens_out`, `cost_usd`, `metadata` |
| `incident` | `action_id`, `severity`, `title`, `evidence` |
| `project` | `status`, `reason` — emitted on suspend and resume |

`metadata.blast_radius` on a blocked install carries the inline expand content.

```js
const { token } = await fetch(`${api}/v1/events/token`, {
  method: "POST",
  headers: { "X-Juno-Key": key },
}).then((r) => r.json())

const es = new EventSource(`${api}/v1/events/stream?cursor=0&token=${token}`)
es.addEventListener("action",   e => addRow(JSON.parse(e.data)))
es.addEventListener("project",  e => setStatus(JSON.parse(e.data).status))
es.addEventListener("expired",  () => reconnectWithFreshToken())
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
