# JunoGuard — detonation worker

Installs a suspect package in a disposable, network-blocked Modal sandbox and
reports what it actually did.

```
gateway decides + responds                    (hot path, unchanged, ~0 ms)
        |
        v  background task
POST /detonate ──> Modal worker  (has network)
                     | fetch the registry artifact, verify its published digest
                     v
                   Sandbox(block_network=True)   (has none)
                     | write the verified bytes in, extract
                     | run each DECLARED lifecycle hook directly
                     | canary credentials seeded in the environment
                     v
                  observations
                     |
                     v
        POST /v1/detonations/<action_id>  ──> gateway  ──> incident evidence
```

**Why the fetch happens outside the sandbox.** The first version ran
`npm install <pkg>` inside the network-blocked container. npm could not reach
the registry, the package was never downloaded, no package code ran — and the
report said "attempted network egress" for *every* package, because that egress
was npm's own. Fetching and digest-verifying outside, then executing hooks on
the extracted tree inside, fixes both halves: something actually runs, and an
egress attempt now means the package reached for the network, since nothing else
in the container has any reason to.

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
| Lifecycle scripts | Read from the package's own manifest, then executed one at a time — declared *and* observed |
| Artifact integrity | The tarball is checked against the registry's published `integrity`/`shasum` before it enters the sandbox; a mismatch aborts the run |
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

## Known limitation

Hooks run on an **extracted** package, not an installed dependency tree. A script
that `require()`s the package's own dependencies will crash early — esbuild's
postinstall does exactly this in testing, and the report says so honestly
(`ran postinstall`, exit 1). Scripts using only Node builtins, which is what
exfiltration looks like, run to completion. Installing the full tree would mean
giving the sandbox registry access, which is the thing that made the first
version useless.

## Verified

Against the deployed worker:

| Package | Result |
|---|---|
| `left-pad@1.3.0` | `severity: none` — no hooks, no egress, no stray writes (4.5s) |
| `esbuild@0.21.5` | `severity: low` — `postinstall` observed running, no egress (3.4s) |

`low` for esbuild is correct and deliberate: a postinstall on its own is
ordinary, and native modules build that way.

## Cost

Only packages that were not cleanly allowed are detonated — a clean allow is the
overwhelming majority of traffic. Modal bills per second with no idle charge, so
a quiet day costs nothing.
