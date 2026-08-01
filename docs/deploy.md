# Deploying JunoGuard

Three pieces: a Postgres schema, a gateway process, and a static frontend. The
gateway is deliberately able to boot with nothing configured — that is what lets
the demo survive a missing credential — so **production has to be told it is
production**, or it will happily serve policy decisions from a store that dies
with the process.

```
JUNO_ENV=production
```

`GET /ready` then returns `503` with a list of problems until the deployment can
actually do its job. Point the platform's health check at `/ready`, not
`/health`: `/health` answers "the process is up", `/ready` answers "this
deployment is fit to supervise anything".

---

## 1. Database

Apply the migrations in order. They are written to be re-runnable, so applying
them to an already-migrated database is a no-op.

```bash
DATABASE_URL='postgres://…' ./supabase/apply.sh --dry-run   # list them
DATABASE_URL='postgres://…' ./supabase/apply.sh             # apply
```

The first migration in the directory creates the baseline schema, so this works
on an empty database as well as an existing one.

Then create a project and grant yourself access. The agent key is never stored —
only its hash — so generate it, hash it, and keep the plaintext in your own
secret manager:

```sql
-- Generate a key outside the database (e.g. openssl rand -hex 24), then:
select set_config('junoguard.demo_project_key', 'jg_live_yourkeyhere', false);
-- Or insert directly (the hash is what the gateway matches against):
insert into projects (name, api_key_hash, api_key_prefix)
values ('Production', encode(digest('jg_live_yourkeyhere','sha256'),'hex'),
        left('jg_live_yourkeyhere', 12));

insert into policies (project_id) select id from projects where name = 'Production';

-- Without a membership row, a signed-in user sees nothing. That is intended.
insert into project_members (project_id, user_id, role)
select p.id, '<auth.users uuid>', 'owner' from projects p where p.name = 'Production';
```

Rotating a key is an update to `api_key_hash` plus `key_rotated_at`. Revoking one
is setting `key_revoked_at`; the gateway stops matching it immediately.

---

## 2. Gateway

```bash
docker build -t junoguard-gateway ./backend
docker run -p 8000:8000 --env-file ./backend/.env.production junoguard-gateway
```

### Required in production

| Variable | Why |
|---|---|
| `JUNO_ENV=production` | Turns on the readiness checks below |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Durable persistence. Without it, decisions and audit history die with the process |
| `OSSPREY_API_KEY` | Real package verdicts. Without it, every verdict is a mock fixture |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins. There is no wildcard; an unlisted origin gets no CORS headers |
| `STREAM_TOKEN_SECRET` | Signs event-stream tokens. Unset means a random per-process secret, which breaks across replicas and on restart |
| `OPERATOR_TOKEN` **or** Supabase auth | Somebody has to be able to use the kill switch |

### Also worth setting

`DAILY_BUDGET_USD`, `PER_REQUEST_BUDGET_USD`, `MAX_REQUEST_TOKENS`,
`BURST_LIMIT_PER_MINUTE`, `BLOCK_SEVERITY` (defaults to `unknown`),
`SUSPEND_ON_MALWARE`, `PROVIDER_API_KEY` with `MOCK_PROVIDER=false`.

**Never** put `SUPABASE_SERVICE_ROLE_KEY`, `OPERATOR_TOKEN` or
`STREAM_TOKEN_SECRET` in a `VITE_`-prefixed variable. Every `VITE_` value is
compiled into the public browser bundle.

### Replica constraint

Rate limiting, budget reservations, idempotency and every audit record live in
Postgres, so they are correct across replicas. Two things are not:

1. **The SSE event buffer is per-process.** A dashboard connected to replica A
   never sees events published by replica B. Either run **one replica**, or
   configure the dashboard for Supabase Realtime (`VITE_SUPABASE_URL`), which
   reads from the database and is replica-independent.
2. **Stream tokens** are only portable across replicas if `STREAM_TOKEN_SECRET`
   is set to the same value everywhere.

Run one replica unless the dashboard is on Supabase Realtime.

---

## 3. Frontend

Static build, deployed on Vercel (`frontend/vercel.json` handles SPA routing).

```
VITE_JUNO_MODE=live
VITE_SUPABASE_URL=…
VITE_SUPABASE_ANON_KEY=…
VITE_API_URL=https://gateway.example
```

Declare the mode. `live` makes sign-in mandatory, and a live build whose Supabase
credentials go missing reports a configuration error rather than opening the
console — removing a variable is not a way past the gate.

---

## 4. Smoke test

Run these against the deployed pair before believing any of it:

```bash
API=https://gateway.example
KEY=…            # the project key whose hash is in the database
ORIGIN=https://console.example

# Readiness — must be 200, not 503
curl -fsS $API/ready | jq

# CORS from the real frontend origin — must return access-control-allow-origin
curl -sSI -X OPTIONS $API/v1/guard/install \
  -H "Origin: $ORIGIN" -H 'Access-Control-Request-Method: POST' | grep -i access-control

# Agent lane
curl -fsS -X POST $API/v1/guard/install -H "X-Juno-Key: $KEY" \
  -H 'Content-Type: application/json' -d '{"package":"react"}' | jq .decision

# The canary must be refused
curl -fsS -X POST $API/v1/guard/install -H "X-Juno-Key: $KEY" \
  -H 'Content-Type: application/json' -d '{"package":"@ossprey/test-package"}' | jq .decision

# Feed auth — must be 401 without a credential
curl -sS -o /dev/null -w '%{http_code}\n' $API/v1/events/recent

# Kill switch must refuse an agent key, and accept an operator
curl -sS -o /dev/null -w '%{http_code}\n' -X POST $API/v1/projects/suspend \
  -H "X-Juno-Key: $KEY" -H 'Content-Type: application/json' -d '{"reason":"smoke test"}'
```

Expected: `ready`, an allow-origin header, `allow`, `block`, `401`, `401`.

Then in the browser: sign in, confirm the dashboard shows your project (not a
"NO PROJECT ACCESS" notice), suspend and resume it, and confirm the control
history line names you.
