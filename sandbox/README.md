# JunoGuard package sandboxes

The npm image executes `preinstall`, `install`, and `postinstall` from a verified
registry tarball. The Python image accepts a verified sdist or pure
`py3-none-any` wheel and performs offline build, install, and top-level import
steps. These workers are opt-in second signals for non-clean Ossprey verdicts;
they never turn a static block into an allow.

## Build and enable

```bash
docker build -t junoguard-sandbox:latest sandbox
docker build -f sandbox/Dockerfile.python \
  -t junoguard-python-sandbox:latest sandbox
bash sandbox/run-canaries.sh
```

On the gateway:

```dotenv
SANDBOX_ENABLED=true
SANDBOX_IMAGE=junoguard-sandbox:latest
SANDBOX_PYPI_IMAGE=junoguard-python-sandbox:latest
```

The base image is pinned by multi-platform digest. The gateway uses
`--pull=never`, so a decision cannot silently fetch a different worker image.

## Boundary

Each detonation gets:

- no network namespace access
- no Linux capabilities and `no-new-privileges`
- a read-only root filesystem
- an unprivileged `65534:65534` user
- 0.5 CPU, 256 MB memory, 64 PIDs, and a wall-clock timeout
- ephemeral `noexec` tmpfs for `/work` and `/tmp`
- one host mount: the digest-verified package artifact, read-only

It does **not** receive the repository, the Docker socket, gateway environment
variables, provider keys, or Supabase credentials.

## Operational limits

- npm packages run lifecycle scripts without transitive dependencies. A script
  that requires them may fail, which is evidence rather than a clean result.
- PyPI prefers a source distribution and otherwise accepts only a pure
  `py3-none-any` wheel. Native wheels are not executed.
- Python builds use the worker's pinned setuptools and wheel with `--no-index`,
  `--no-deps`, and no build isolation. Packages requiring other build backends
  fail closed because the networkless worker cannot fetch them.
- Archive validation rejects absolute and parent paths, links, special files,
  encrypted ZIP entries, duplicate paths, and expansion beyond fixed file and
  byte limits before package code runs.
- Container isolation is still a kernel boundary. Run the gateway against a
  dedicated rootless Docker daemon; do not expose a general-purpose production
  Docker socket to the gateway process. Higher-risk deployments should use an
  additional VM boundary such as Firecracker or gVisor.
- Docker must terminate timed-out containers. JunoGuard names every container
  and force-removes it after a client timeout.

The npm and PyPI canaries under `fixtures/` write files and exercise their
execution paths. The npm canary also references a credential name and attempts
network access. Canary files remain in ephemeral storage, and network attempts
cannot leave the container.
