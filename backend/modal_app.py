"""JunoGuard gateway, deployed on Modal.

`backend/Dockerfile` is still the reference deployment and still what you should
run anywhere that gives you a container runtime. This file exists because the
detonation worker already lives in a Modal workspace, and a gateway that the
worker can reach without a second hosting account is one less thing to keep
alive. It serves the same `app.main:app` — no forked routing, no Modal-specific
endpoints.

Two properties of this deployment are load-bearing, both from docs/deploy.md:

* **One container.** The SSE event buffer is per-process, so a dashboard
  connected to replica A never sees events published by replica B.
  `max_containers=1` keeps that from happening; `@modal.concurrent` is what
  stops a single container from serialising every request.
* **`/ready`, not `/health`.** `/health` answers "the process is up". `/ready`
  answers "this deployment is fit to supervise anything", and in production it
  returns 503 until it is. Modal has no platform health check to point at it, so
  it is the smoke test's job — see docs/deploy.md §4.

Configuration comes from a Modal secret, never from a file in the image; the
image contains `app/` and nothing else from this repository.

    modal secret create junoguard-gateway JUNO_ENV=production ...   # see docs/deploy.md
    modal deploy backend/modal_app.py
"""

from pathlib import Path

import modal

HERE = Path(__file__).parent

app = modal.App("junoguard-gateway")

image = (
    modal.Image.debian_slim(python_version="3.12")
    # The same hashed lock the Dockerfile installs, with the same refusal to
    # install anything that is not in it.
    .pip_install_from_requirements(
        str(HERE / "requirements.txt"), extra_options="--require-hashes"
    )
    # Mounted rather than baked in, so a code change redeploys without a rebuild.
    .add_local_dir(str(HERE / "app"), remote_path="/root/app", ignore=["__pycache__"])
)

# Everything the gateway needs to be more than a demo. Created out of band —
# values never live in this repository.
secrets = [modal.Secret.from_name("junoguard-gateway")]


@app.function(
    image=image,
    secrets=secrets,
    # The replica constraint, enforced rather than documented.
    max_containers=1,
    # Long enough that an idle dashboard does not pay a cold start on every
    # poll, short enough that an unused gateway stops costing anything.
    scaledown_window=300,
    # A request ceiling, not an SSE ceiling: an event stream is one input that
    # stays open, and a stream cut off after five minutes looks like an outage.
    timeout=3600,
)
# Without this, one container means one request at a time, and a held-open
# event stream would block every guard call behind it.
@modal.concurrent(max_inputs=100, target_inputs=40)
@modal.asgi_app(label="junoguard-gateway")
def gateway():
    from app.main import app as fastapi_app

    return fastapi_app
