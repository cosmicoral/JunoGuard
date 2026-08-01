# JunoGuard — dashboard

One screen. No routes, no login, no settings. Everything Juno decides shows up
here, both lanes interleaved in a single feed, and one button closes the gate.

```bash
npm install
npm run dev          # http://localhost:5173
```

Runs with **mock data out of the box** — no backend, no Supabase, no keys.

## Mock mode vs live

Mock mode is the default and is what the demo runs on. It seeds ~55 rows of
plausible history so the feed is never empty, then emits new actions on a
timer at roughly 22–25 req/min against a 30/min policy cap.

Set both of these and the dashboard switches to Supabase Realtime instead —
`agent_actions` and `incidents` inserts, `projects` updates, no polling:

```
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
```

Optional: `VITE_API_URL` makes the kill switch also POST
`/projects/:id/suspend` (or `/resume`) to the gateway. The UI never waits on
that request — the screen flips immediately either way.

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
  App.tsx                 shell, kill-switch screen state
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
