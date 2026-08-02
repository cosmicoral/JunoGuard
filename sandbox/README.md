# JunoGuard npm sandbox

This image executes the `preinstall`, `install`, and `postinstall` scripts from
a verified npm registry tarball. It is an opt-in second signal for packages
whose Ossprey verdict is not clean; it never turns a static block into an allow.

## Build and enable

```bash
docker build -t junoguard-sandbox:latest sandbox
```

On the gateway:

```dotenv
SANDBOX_ENABLED=true
SANDBOX_IMAGE=junoguard-sandbox:latest
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
- one host mount: the digest-verified package tarball, read-only

It does **not** receive the repository, the Docker socket, gateway environment
variables, provider keys, or Supabase credentials.

## Operational limits

- npm packages are supported; PyPI detonation is not yet implemented.
- The image exercises lifecycle scripts without installing transitive
  dependencies. A script that requires them may fail, which is evidence rather
  than a clean result.
- Container isolation is still a kernel boundary. Run the gateway against a
  dedicated rootless Docker daemon; do not expose a general-purpose production
  Docker socket to the gateway process. Higher-risk deployments should use an
  additional VM boundary such as Firecracker or gVisor.
- Docker must terminate timed-out containers. JunoGuard names every container
  and force-removes it after a client timeout.

The canary under `fixtures/` writes a file, references a credential name, and
attempts network access. Its file remains in ephemeral storage and the network
attempt cannot leave the container.
