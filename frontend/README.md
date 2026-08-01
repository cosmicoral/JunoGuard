# JunoGuard — site and live dashboard

The root route is JunoGuard's product landing page. The authenticated
operational console lives at `/dashboard`: everything Juno decides appears
there, both lanes interleaved in a single feed, and one button closes the gate.

```bash
npm install
npm run dev          # http://localhost:5173
```

The landing and sign-in screens run without a backend. Dashboard access uses
Google or GitHub OAuth through Supabase and therefore requires the two Supabase
frontend variables below. The FastAPI gateway remains optional for the
dashboard; with Supabase configured, the feed comes from Supabase Realtime.

## OAuth providers

Both providers reuse the same Supabase client, PKCE callback, persisted session,
route guard, and sign-out flow.

First, in Supabase Authentication → URL Configuration, set the Site URL and add
`http://localhost:5173/auth/callback` plus the production callback URL to the
redirect allow list. Then copy `.env.example` to `.env.local` and set
`VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.

### Google

1. In Supabase Authentication → Providers, enable Google and add the client ID
   and secret from Google Cloud.
2. In Google Cloud, add Supabase's callback URL as an authorized redirect URI:
   `https://<project-ref>.supabase.co/auth/v1/callback`.

### GitHub

1. In GitHub Settings → Developer settings → OAuth Apps, create an OAuth app.
   Use the JunoGuard deployment as the Homepage URL and set the Authorization
   callback URL to `https://<project-ref>.supabase.co/auth/v1/callback`.
2. In Supabase Authentication → Providers, enable GitHub and add the OAuth
   app's client ID and client secret.

Finally, apply `supabase/schema.sql` for a fresh database, or apply
`supabase/migrations/202608010001_require_authenticated_dashboard_reads.sql`
to an existing database so anonymous clients cannot read dashboard data.

The browser uses the PKCE OAuth flow. Supabase persists and refreshes the
session, `/auth/callback` exchanges the authorization code, and unauthenticated
dashboard visits return to `/auth/sign-in`.

## Mock mode vs live

Mock mode is the default. It seeds ~55 rows of plausible history so the feed
is never empty, then emits new actions on a timer at roughly 22–25 req/min
against a 30/min policy cap.

Data source precedence (see `docs/api-contract.md`):

1. **Supabase** — set `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`
2. **SSE** — set `VITE_API_URL=http://localhost:8000` (backfill
   `/v1/events/recent`, then a short-lived token from `/v1/events/token` and
   `EventSource` on `/v1/events/stream`; the feed is authenticated and returns
   only this project's events)
3. **Mock** — neither configured

The kill switch POSTs `/v1/projects/suspend` or `/v1/projects/resume` with
`X-Juno-Key`. Failures surface in the header — the UI does not flip until the
gateway confirms.

## Demo controls

Invisible, keyboard only, mock mode only. Nothing on screen to mis-click.

| Key | What lands |
| --- | --- |
| `B` | A malicious package block, expanded, with full blast radius and a new incident |
| `R` | A token burst — 16 backdated calls escalating flag → block, spiking the sparkline past the cap |

The **SUSPEND** button is the closing beat: the rail goes red, the header
flips, and every action after it lands as `BLOCKED · project suspended`. Press
it again to reset.

## Layout notes

Built for a projector at roughly half screen width (~960px), not a wide ops
console. Stat numbers are 38px with tabular figures so they do not jitter as
values settle. Mid-greys are avoided anywhere meaning is carried — decisions
are green/amber/red at full saturation.

There is exactly one chart: the sparkline in REQ/MIN, hand-rolled inline SVG
with a dashed line at the policy cap. A burst crosses it visibly. That is the
entire Lane B argument in one glyph.

## Structure

```
src/
  App.tsx                 landing/dashboard route selection
  auth/                   session context, sign-in, callback, route guard
  Landing.tsx             product landing page
  Dashboard.tsx           dashboard shell and kill-switch screen state
  lib/useJuno.ts          state, mock timer, Realtime subscriptions, rollups
  lib/mock.ts             seed data, emitters, the two demo set pieces
  lib/supabase.ts         client; decides mock vs live from env
  components/Header.tsx   wordmark, status, kill switch
  components/Stats.tsx    four tiles, budget meter, sparkline
  components/Feed.tsx     unified feed, inline blast radius
```

## Motion

Springs, `bounce: 0`, ~300ms — no overshoot anywhere. New rows enter with a
small y-offset; blocked rows get exactly one red flash on arrival and then sit
still. Numbers interpolate rather than snap. The inline expand uses Motion's
`layout` so surrounding rows slide rather than jump.

`prefers-reduced-motion` drops the movement and the looping status pulse but
keeps colour and opacity, which is where the meaning is.
