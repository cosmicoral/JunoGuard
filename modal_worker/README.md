# JunoGuard — detonation worker

Installs a suspect package in a disposable, network-blocked Modal sandbox and
reports what it actually did.

```
gateway decides + responds          (hot path, unchanged, ~0 ms)
        |
        v  background task
POST /detonate ──> Modal ──> Sandbox(block_network=True)
                                | npm/pip install, lifecycle scripts ENABLED
                                | canary credentials seeded in the environment
                                v
                          observations
                                |
                                v
        POST /v1/detonations/<action_id>  ──> gateway  ──> incident evidence
```

## What this is and is not

It is **evidence, and sometimes retroactive response**. It cannot prevent the
install it reports on — the decision was made and returned before this ran.

* For a **blocked** package, the report is proof: blast radius stops being
  inferred from the developer's own `.env` files and becomes an observation
  about the package.
* For a package that was **flagged and proceeded**, or that went in under an
  operator's `--allow-unscanned` override, it is protective — a `critical`
  report is grounds to block and suspend after the fact.

It never gates an install, and it is entirely optional. Unset
`MODAL_DETONATE_URL` and Lane A behaves exactly as before, minus the evidence.

## What it observes

| Signal | How |
|---|---|
| Lifecycle scripts | Read from the installed package's own `package.json` — declared, not guessed |
| Network egress | Sandbox runs with `block_network=True`; an attempt fails, and the failure is the signal |
| Credential access | **Fake** credentials under realistic names are seeded in the environment, generated fresh per run; a package that prints or stages one gives itself away, and a match cannot be a coincidence |
| Stray writes | Filesystem diff before/after, minus the paths an install legitimately touches |
| Exit code, duration, output tail | Directly |

`severity` is the one judgement in the report, and it is deliberately
conservative: a postinstall script alone is `low` (native modules build that
way), egress plus a script is `high`, an exposed canary is `critical`.

## Deploy

```bash
pip install modal
modal secret create junoguard-detonation \
    MODAL_DETONATE_TOKEN=$(openssl rand -hex 24) \
    DETONATION_CALLBACK_TOKEN=$(openssl rand -hex 24)

modal deploy modal_worker/detonate.py     # prints the URL -> MODAL_DETONATE_URL
modal serve  modal_worker/detonate.py     # hot-reload, temporary URL
```

Then in `backend/.env`:

```bash
MODAL_DETONATE_URL=https://<you>--junoguard-detonation-web.modal.run
MODAL_DETONATE_TOKEN=<same as the secret>
DETONATION_CALLBACK_TOKEN=<same as the secret>
PUBLIC_BASE_URL=https://gateway.example      # where the worker posts the report
```

`PUBLIC_BASE_URL` must be reachable from Modal. On a laptop that means a tunnel;
without it the gateway logs that it skipped the detonation rather than starting
work whose result has nowhere to go.

## Security notes

**This deliberately executes untrusted code.** That is the point, and it is why
it runs in an ephemeral Modal sandbox with egress blocked rather than anywhere
near your machine or the gateway.

**The report is hostile input.** It is assembled in a container where a
package's install script has just run, so the gateway treats it accordingly:
bearer-authenticated, size-capped, stripped of control characters, and reduced
to a fixed schema with pinned enumerations before it reaches the audit trail. A
package that tries to write its own incident evidence gets a truncated string in
a known shape. See `backend/app/detonation.py` and `backend/tests/test_detonation.py`.

**The sandbox never holds a real credential.** Only the two bearer tokens live
in the Modal secret. No Supabase key, no provider key, no agent key.

## Testing without deploying

Everything above the `--- serving layer ---` line in `detonate.py` is plain
Python with no Modal imports, so the report shaping is unit-tested in
`backend/tests/test_detonation.py`:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_detonation.py -q
```

## Cost

Only packages that were not cleanly allowed are detonated — a clean allow is the
overwhelming majority of traffic. Modal bills per second with no idle charge, so
a quiet day costs nothing.
