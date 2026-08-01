# JunoGuard Bug Log

Audit date: 2026-08-01  
Audited commit: `ff696ff` (`main`)  
Scope: gateway, policy engine, persistence, Supabase schema/RLS, OAuth UI,
dashboard data paths, CLI, MCP server, dependency manifests, tracked files, and
Git history.

This log converts the current review findings into fixable engineering
comments. Each issue includes evidence, a proposed mitigation, and a concrete
verification condition. Status values are `OPEN`, `IN PROGRESS`, `FIXED`, or
`ACCEPTED RISK`.

## Severity guide

- **P0 / Critical** — breaks a core security boundary or permits cross-project
  access, secret disclosure, or policy bypass.
- **P1 / High** — materially weakens a safety guarantee, production operation,
  or the submitted product claim.
- **P2 / Medium** — reliability, auditability, deployment, or maintainability
  gap that should be fixed before a production pilot.
- **P3 / Low** — hardening or quality improvement with limited immediate risk.

## Executive summary

| ID | Priority | Status | Finding |
|---|---:|---|---|
| JG-001 | P0 | FIXED | Authenticated users can read every project, including plaintext agent API keys |
| JG-002 | P0 | FIXED | Rate and budget enforcement is non-atomic under concurrency |
| JG-003 | P0 | FIXED | Charged `flag` decisions are excluded from daily spend |
| JG-004 | P0 | FIXED | Scanner outage produces a proceedable `flag` instead of failing closed |
| JG-005 | P1 | FIXED | Event backfill and SSE stream are unauthenticated and global |
| JG-006 | P1 | FIXED | OAuth does not protect kill-switch operations; the browser ships an agent key |
| JG-007 | P1 | FIXED | OAuth regression makes the default mock/offline dashboard unreachable |
| JG-008 | P1 | OPEN | A configured live dashboard silently degrades to mock data |
| JG-009 | P1 | OPEN | CLI and MCP enforcement can be bypassed by supported install paths |
| JG-010 | P1 | OPEN | Package verdict cache can preserve a stale `latest` allow indefinitely |
| JG-011 | P1 | FIXED | Realtime subscriptions are not project-scoped and can mix tenant data |
| JG-012 | P1 | OPEN | Product claims include Modal, SBOM, and unbypassable enforcement that are not implemented |
| JG-013 | P1 | OPEN | No project-owned automated tests protect security invariants |
| JG-014 | P2 | OPEN | Provider failures produce no action or audit event |
| JG-015 | P2 | OPEN | Critical suspend/resume actions lack actor, role, reason, and audit history |
| JG-016 | P2 | OPEN | Production deployment is blocked by localhost-only CORS and missing hosting config |
| JG-017 | P2 | OPEN | Frontend toolchain has known high/moderate development-server vulnerabilities |
| JG-018 | P2 | OPEN | Python dependencies are unpinned and builds are not reproducible |
| JG-019 | P2 | OPEN | Supabase bootstrap SQL is not safely rerunnable |

## Confirmed findings

### JG-001 — Cross-project data and agent API keys are readable

**Priority:** P0 / Critical  
**Status:** FIXED

> **Review comment:** Authentication has been added, but authorization is still
> global. Any Supabase user in the `authenticated` role can select every row in
> `projects`, `policies`, `agent_actions`, and `incidents`. Because `projects`
> stores `api_key` in plaintext, a signed-in user can retrieve the control key
> for every project.

**Evidence**

- `supabase/schema.sql` stores `projects.api_key` as plaintext.
- All four read policies use only `auth.uid() is not null`; they do not check
  project membership.
- `frontend/src/lib/useJuno.ts` orders projects by creation time and selects the
  first row rather than selecting a project assigned to the current user.
- `POST /v1/projects/suspend` and `/resume` return the full in-memory/Supabase
  project representation. The reproduced response keys included `api_key`.

**Mitigation**

1. Add `project_members(project_id, user_id, role)` with viewer/operator/owner
   roles.
2. Replace each RLS predicate with an `exists` membership check for the row's
   `project_id`.
3. Revoke browser select access to `projects.api_key`; preferably move agent
   credentials into a separate service-role-only table.
4. Hash agent API keys, store only a prefix for identification, and add
   rotation/revocation.
5. Return an explicit public project DTO from suspend/resume rather than the
   persistence row.

**Verification**

- A user belonging to project A receives zero rows for project B.
- `select('*')` through the browser anon client never returns an agent key or
  key hash.
- Suspend/resume response bodies never contain `api_key`.

### JG-002 — Rate and budget checks race under concurrency

**Priority:** P0 / Critical  
**Status:** FIXED

> **Review comment:** Policy evaluation reads the current request count and
> spend, calls the provider, and persists the action as separate operations.
> Concurrent requests can all observe the same pre-limit state and proceed.

**Reproduction**

- Policy limit: 8 requests/minute.
- Twenty concurrent `/v1/guard/llm` calls were released together with a 50 ms
  provider delay.
- Result: `{'allow': 20}`.

**Mitigation**

- Move reservation and enforcement into one database transaction or atomic RPC.
- Lock the project/policy row, calculate spend/rate, reserve the worst-case
  charge, and return the decision before the provider call.
- Finalize the reservation with actual usage after the provider responds.
- For the memory backend, perform evaluate-and-record under a project-scoped
  lock so its semantics match production.
- Add an idempotency key to prevent client retries from creating duplicate
  provider charges.

**Verification**

- With a limit of 8, at most 8 of 20 simultaneous requests reach the provider.
- Replaying one idempotency key returns the original result without a second
  charge.

### JG-003 — Flagged provider charges disappear from daily spend

**Priority:** P0 / Critical  
**Status:** FIXED

> **Review comment:** `flag` is a proceedable decision and the provider is
> called for it, but both spend implementations total only rows whose decision
> is `allow`. Once the 80% warning threshold is crossed, charged calls can stop
> advancing the daily total and bypass the cap.

**Reproduction**

- Record a flagged LLM action with `cost_usd=0.90` in `MemoryStore`.
- `daily_spend_usd()` returns `0`.

**Evidence**

- `backend/app/main.py` calls the provider for every decision except `block`.
- `backend/app/store.py` filters daily spend to `decision == "allow"`.
- `supabase/schema.sql` applies the same `decision = 'allow'` filter.
- `frontend/src/lib/useJuno.ts` derives its Supabase total through
  `sumAllowedCost`, creating the same display error.

**Mitigation**

- Define billable spend as every action with positive `cost_usd`, independent
  of decision label.
- Update the memory store, SQL RPC, frontend rollup, mock rollup, and API docs
  together.

**Verification**

- Allowed and flagged charged calls both increase spend.
- Blocked calls with zero cost do not.
- The request that would exceed the daily cap never reaches the provider.

### JG-004 — Scanner outage fails open to a proceedable flag

**Priority:** P0 / Critical  
**Status:** FIXED

> **Review comment:** The Ossprey error handler says it never fails open, but it
> converts an outage into severity `unknown`. Under the default `malicious`
> threshold, `unknown` becomes `flag`, with a reason saying the package was
> installed with caution.

**Reproduction**

- Force `ossprey.scan()` to return `unknown` with “Scanner unreachable”.
- Evaluate using the default policy.
- Result: `decision=flag`.

**Mitigation**

- Introduce an explicit `review` decision, or block scanner-unavailable results.
- Set the production default threshold to `unknown`.
- Distinguish “unknown package reputation” from “scanner unavailable”; an
  infrastructure failure should never be interpreted as package evidence.

**Verification**

- No package reaches the package manager while the scanner is unavailable.
- The agent receives a structured retry-later/review-required response.

### JG-005 — Event feed leaks global action and incident data

**Priority:** P1 / High  
**Status:** FIXED

> **Review comment:** `/v1/events/recent` and `/v1/events/stream` require no
> authentication and the in-process event buffer has no project field filter.
> Incident evidence can include credential names and blast-radius details.

**Reproduction**

- Generate an authenticated install event.
- Call `/v1/events/recent` without `X-Juno-Key` or an OAuth token.
- Result: HTTP 200 with the event payload.

**Mitigation**

- Authenticate the feed using the human JWT or a short-lived signed stream
  token.
- Store `project_id` on every event and filter before backfill or streaming.
- If bearer headers are required, replace browser `EventSource` with a fetch
  streaming client or issue a single-use stream URL.

**Verification**

- Anonymous requests return 401.
- A project A token never receives project B events.

### JG-006 — OAuth does not authorize kill-switch operations

**Priority:** P1 / High  
**Status:** FIXED

> **Review comment:** The dashboard route requires a Supabase session, but the
> kill switch ignores that session and sends a hardcoded agent key from the
> JavaScript bundle. Anyone who obtains that public value can call suspend or
> resume without signing in.

**Mitigation**

- Remove `JUNO_KEY` from browser code.
- Accept the Supabase JWT on human-control endpoints and verify project role.
- Reserve agent keys for agent guard calls only.
- Require operator/owner role for suspend and owner or reviewed-operator role
  for resume.

**Verification**

- A viewer receives 403 for suspend and resume.
- A valid agent key cannot call human-control endpoints.
- An operator action records the OAuth user ID.

### JG-007 — OAuth breaks the default mock/offline dashboard

**Priority:** P1 / High  
**Status:** FIXED

> **Review comment:** Documentation says the frontend runs in mock mode without
> credentials, but `/dashboard` is now always wrapped in `ProtectedRoute`.
> Without Supabase configuration the route redirects to sign-in, and both
> provider buttons are disabled. There is no path to the dashboard.

**Browser reproduction**

1. Build with no `VITE_SUPABASE_URL` or anon key.
2. Open `/dashboard`.
3. The app redirects to `/auth/sign-in`.
4. Both OAuth buttons are disabled and the page says Supabase is not configured.

**Mitigation**

- In explicit mock/demo mode, allow a clearly labelled local dashboard without
  authentication.
- In live Supabase mode, keep `ProtectedRoute` mandatory.
- Make the mode an explicit build/runtime setting rather than inferring it from
  missing credentials.

**Verification**

- Clean checkout + `npm run dev` can reach the labelled mock dashboard.
- A live build cannot bypass sign-in by removing a credential at runtime.

### JG-008 — Live gateway failure silently becomes mock success

**Priority:** P1 / High  
**Status:** OPEN

> **Review comment:** When `VITE_API_URL` is configured but the gateway cannot
> be reached, the dashboard seeds mock history and continues. A security
> operator can mistake simulation data for a working control plane.

**Mitigation**

- Do not cross from configured-live to mock automatically.
- Render a full-width `DEGRADED — GATEWAY UNREACHABLE` state, freeze live
  counters, and disable suspend/resume.
- Keep a separate, explicit “enter demo simulation” action if stage resilience
  is required.

**Verification**

- Disconnecting a configured gateway never produces new mock “allow” events.
- The interface visibly distinguishes LIVE, DEGRADED, and DEMO states.

### JG-009 — Supported install paths bypass the guard

**Priority:** P1 / High  
**Status:** OPEN

> **Review comment:** MCP enforcement depends on agent compliance. The CLI runs
> lockfile-only installs and local/Git/URL installs unguarded, so the product
> cannot accurately claim that an agent cannot route around the gate.

**Mitigation**

- Make strict refusal the default for unscannable sources.
- Require a named, logged operator override for unsupported installs.
- Scan lockfile resolutions and direct archive/Git sources by digest or SBOM.
- Document MCP as an advisory policy tool until an OS/package-manager boundary
  is implemented.

**Verification**

- `juno npm install`, direct URLs, Git sources, and local archives fail closed
  when they cannot be scanned.

### JG-010 — `latest` package verdicts can remain stale indefinitely

**Priority:** P1 / High  
**Status:** OPEN

> **Review comment:** The process-global Ossprey cache has no TTL. The cache key
> uses `latest` when no version is supplied. A package allowed today can keep
> that cached allow after a malicious version is published.

**Mitigation**

- Resolve an immutable version/digest before caching.
- Add short TTLs and bounded eviction.
- Do not cache scanner-unavailable results.
- Include scanner policy/version in the cache key.

**Verification**

- Publishing or selecting a new version forces a fresh verdict.
- Cache entries expire and memory remains bounded.

### JG-011 — Realtime subscriptions are not project-scoped

**Priority:** P1 / High  
**Status:** FIXED

> **Review comment:** Initial Supabase queries filter by the selected project,
> but Realtime subscriptions listen to all action, incident, and project rows.
> Action and incident callbacks insert every received row into the current
> dashboard. Combined with global authenticated RLS, one user's dashboard can
> mix other projects' events.

**Mitigation**

- Apply a `project_id=eq.<id>` Realtime filter to each subscription.
- Reject callback rows whose project ID does not match as defense in depth.
- Select the project through membership rather than creation order.

**Verification**

- Injecting a project B event never changes project A counters or feed.

### JG-012 — Documentation overstates implemented guarantees

**Priority:** P1 / High  
**Status:** OPEN

> **Review comment:** README and landing content claim Modal sandbox detonation,
> SBOM generation, and interception an agent cannot bypass. No Modal code or
> sandbox worker exists, the Ossprey adapter consumes a verdict rather than an
> SBOM, and JG-009 documents bypass paths.

**Mitigation**

- Implement and test the integrations, or mark them explicitly as roadmap.
- Add a capability table with `live`, `mock`, and `planned` states.
- Ensure the demo labels the evidence source on screen.

**Verification**

- Every present-tense product claim maps to a code path and automated or manual
  verification step.

### JG-013 — No automated security-invariant tests

**Priority:** P1 / High  
**Status:** OPEN

> **Review comment:** `pytest` discovers no project tests, and there is no
> frontend test configuration. The current budget, concurrency, auth, and
> failure-mode regressions therefore pass CI because there is no CI and no
> regression suite.

**Mitigation**

- Add backend unit tests for decision rules and store rollups.
- Add API integration tests for auth, project isolation, SSE, suspend/resume,
  idempotency, and concurrent limits.
- Add frontend route/data-source tests and one browser smoke test.
- Run all checks in a required GitHub Actions workflow.

**Minimum acceptance suite**

- Scanner outage cannot proceed.
- Charged flags count toward spend.
- Concurrency cannot exceed policy.
- Blocked calls never reach the provider.
- Suspended projects block both lanes.
- Anonymous/cross-project reads fail.
- Mock, degraded, and live routes remain distinguishable.

### JG-014 — Provider failures are absent from the audit trail

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** If the provider raises or times out, `_persist` is never
> reached. The API fails without recording an attempted action, failure event,
> or ambiguous-charge state.

**Reproduction**

- Replace `provider.complete` with a function that raises.
- Call `/v1/guard/llm`.
- Event sequence remains unchanged.

**Mitigation**

- Reserve and record the attempt before the provider call.
- Finalize it as succeeded, failed, or unknown-charge.
- Return a stable 502 error shape with a correlation ID.

**Verification**

- Every attempted provider call has exactly one durable audit record.

### JG-015 — Critical control actions lack accountable human review

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** Resume has no reason payload, and neither suspend nor
> resume records the human actor, linked incident, previous state, or approval.

**Mitigation**

- Add immutable `control_events` with actor, role, reason, incident, previous
  state, next state, and timestamp.
- Require a reason to resume after critical incidents.
- Consider step-up confirmation or two-person review for production-critical
  projects.

**Verification**

- The dashboard can answer who changed state, why, and which incident was
  reviewed.

### JG-016 — Production deployment path is incomplete

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** Gateway CORS allows only localhost, no hosting/container
> configuration is present, and in-memory state/event delivery is tied to one
> process. A production frontend origin currently receives a 400 preflight.

**Reproduction**

- CORS preflight from `http://localhost:5173`: HTTP 200.
- CORS preflight from `https://junoguard.example`: HTTP 400, no allow-origin.

**Mitigation**

- Configure an explicit production-origin allowlist.
- Add deploy manifests, migration execution, readiness checks, and secret
  injection documentation.
- Use durable storage/pub-sub or explicitly constrain the pilot to one gateway
  replica.

**Verification**

- A clean production deployment passes health, auth callback, guarded action,
  Realtime/SSE, and kill-switch smoke tests.

### JG-017 — Known frontend development-tool vulnerabilities

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** `npm audit` reports one high and one moderate issue through
> Vite/esbuild, including development-server file disclosure/path handling.

**Mitigation**

- Upgrade Vite to a supported non-vulnerable release and retest the build and
  browser routes.
- Until upgraded, never expose the Vite development server beyond localhost.

**Verification**

- `npm audit` reports no high findings.

### JG-018 — Python dependency resolution is not reproducible

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** Backend requirements are unpinned and CLI/MCP manifests
> specify lower bounds without lockfiles. A future install can silently select
> incompatible or vulnerable major versions.

**Mitigation**

- Generate reviewed lock/constraints files for each Python deliverable.
- Pin the supported Python version.
- Run dependency audit and tests on scheduled updates.

**Verification**

- Two clean environments resolve identical package versions and pass checks.

### JG-019 — Supabase bootstrap SQL is not safely rerunnable

**Priority:** P2 / Medium  
**Status:** OPEN

> **Review comment:** `alter publication ... add table` is not guarded against a
> table already being present in the publication. Reapplying the bootstrap can
> stop midway even though tables and policies use partial idempotency patterns.

**Mitigation**

- Move all schema evolution to ordered migrations.
- Wrap publication membership changes in catalog checks.
- Test applying migrations to an empty database and upgrading an existing one.

**Verification**

- Migration up is repeatable in CI and leaves the expected schema/RLS state.

## Test and audit log

### Passed

- Frontend TypeScript/Vite production build completed successfully.
- Public landing page rendered and exposed the expected console link.
- Backend mock-mode smoke flow passed:
  - health: 200
  - missing project key: 401
  - clean install: allow
  - known malicious package: block + suspend
  - LLM while suspended: block
  - resume: active
- CLI mock blocked the Ossprey canary with exit code 2.
- MCP server imported successfully with the installed SDK.
- Python `pip-audit` found no known vulnerabilities in backend requirements or
  the current backend virtual environment.
- Tracked-file secret scan found no verified credential. Its two heuristic
  matches were the Azure credential *variable name* used by blast-radius logic
  and the intentional public demo key.
- Git-history high-signal scan found no OpenAI-style key, GitHub PAT, AWS access
  key, or private-key block.
- `backend/.env` is ignored and is not tracked.
- Bandit found no high-severity issue. Its medium `urlopen` finding is limited
  to the demo driver using a constant local API base URL; the other findings are
  expected demo/subprocess patterns or false positives.

### Failed or warned

- `pytest`: no project tests collected.
- Browser `/dashboard` without Supabase: redirected to disabled OAuth sign-in;
  default mock dashboard unavailable (JG-007).
- Unauthenticated recent events: HTTP 200 (JG-005).
- Production-origin CORS preflight: HTTP 400 (JG-016).
- Twenty simultaneous LLM calls at an 8/min cap: all 20 allowed (JG-002).
- Flagged action with `$0.90` cost: reported daily spend `$0` (JG-003).
- Scanner-unavailable verdict under default policy: `flag` (JG-004).
- Provider exception: no action/event persisted (JG-014).
- `npm audit`: 1 high, 1 moderate development-tool vulnerability (JG-017).
- Frontend build warned that the main JavaScript chunk exceeds 500 kB. This is
  a performance warning rather than a security defect, but route-based code
  splitting should be considered after the security backlog.
- Ruff reported 11 style/lint findings. Most FastAPI `Depends` warnings are a
  framework idiom rather than bugs; the remaining import, executable-bit, and
  explicit `check=False` findings are maintenance cleanup.

## Recommended fix order

1. JG-001, JG-002, JG-003, JG-004 — close data and policy bypasses.
2. JG-005, JG-006, JG-011 — establish one project-scoped human control plane.
3. JG-007, JG-008 — restore explicit and trustworthy demo/live/degraded modes.
4. JG-009, JG-010 — make supply-chain enforcement and cache behavior defensible.
5. JG-013 — encode all fixed invariants in tests and CI.
6. JG-012, JG-015, JG-016 — align claims, human oversight, and deployment.
7. JG-014, JG-017, JG-018, JG-019 — finish operational hardening.
