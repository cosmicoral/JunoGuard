/**
 * Opt-in OS sandbox for approved package-manager exec() calls.
 *
 * This is the host boundary increment: installs that reach `juno …` can run
 * inside a credential-scoped sandbox. It does not intercept bare package-manager
 * invocations, absolute paths, or agents that ignore Juno entirely.
 */

import { accessSync, constants, mkdtempSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";

const TRUTHY = new Set(["1", "true", "yes"]);

export function isHostSandboxEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return TRUTHY.has((env.JUNO_HOST_SANDBOX ?? "").trim().toLowerCase());
}

function executableOnPath(name: string, env: NodeJS.ProcessEnv): string | null {
  for (const dir of (env.PATH ?? "").split(":")) {
    if (!dir) continue;
    const candidate = join(dir, name);
    try {
      accessSync(candidate, constants.X_OK);
      return candidate;
    } catch {
      // Keep scanning PATH.
    }
  }
  return null;
}

function macProfile(project: string, home: string): string {
  return `(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow signal)
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix*)
(allow iokit-open)
(allow network*)
(allow file-read*
  (subpath "/usr")
  (subpath "/bin")
  (subpath "/sbin")
  (subpath "/opt")
  (subpath "/Library")
  (subpath "/System")
  (subpath "/private/tmp")
  (subpath "/var/folders")
  (subpath "/dev")
  (subpath "/etc")
  (subpath (param "PROJECT"))
  (subpath (param "HOME") "/.npm")
  (subpath (param "HOME") "/.cache")
  (subpath (param "HOME") "/.local")
  (subpath (param "HOME") "/Library/Caches")
)
(allow file-write* file-write-data
  (subpath (param "PROJECT"))
  (subpath (param "HOME") "/.npm")
  (subpath (param "HOME") "/.cache")
  (subpath (param "HOME") "/.local")
  (subpath (param "HOME") "/Library/Caches")
  (subpath "/private/tmp")
  (subpath "/var/folders")
)
(deny file-read* file-write* file-write-data
  (subpath (param "HOME") "/.ssh")
  (subpath (param "HOME") "/.aws")
  (subpath (param "HOME") "/.config/gcloud")
  (subpath (param "HOME") "/.kube")
  (subpath (param "HOME") "/.docker")
)
`;
}

function wrapDarwin(
  argv: string[],
  options: { cwd: string; home: string; env: NodeJS.ProcessEnv },
): { argv: string[] } | { error: string } {
  const sandboxExec = executableOnPath("sandbox-exec", options.env);
  if (!sandboxExec) {
    return {
      error:
        "JUNO_HOST_SANDBOX=1 but sandbox-exec was not found on PATH. Refusing the install.",
    };
  }

  const profileDir = mkdtempSync(join(tmpdir(), "junoguard-sandbox-"));
  const profilePath = join(profileDir, "install.sb");
  writeFileSync(profilePath, macProfile(options.cwd, options.home), "utf8");

  return {
    argv: [
      sandboxExec,
      "-f",
      profilePath,
      `-DPROJECT=${options.cwd}`,
      `-DHOME=${options.home}`,
      ...argv,
    ],
  };
}

function wrapLinux(
  argv: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv },
): { argv: string[] } | { error: string } {
  const bwrap = executableOnPath("bwrap", options.env);
  if (!bwrap) {
    return {
      error: "JUNO_HOST_SANDBOX=1 but bwrap was not found on PATH. Refusing the install.",
    };
  }

  const binds = ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt"].filter((root) => {
    try {
      accessSync(root, constants.R_OK);
      return true;
    } catch {
      return false;
    }
  });

  const wrapped = [
    bwrap,
    ...binds.flatMap((root) => ["--ro-bind", root, root]),
    "--bind",
    options.cwd,
    options.cwd,
    "--bind",
    "/tmp",
    "/tmp",
    "--proc",
    "/proc",
    "--dev",
    "/dev",
    "--die-with-parent",
    "--",
    ...argv,
  ];
  return { argv: wrapped };
}

/** Wrap an approved argv when host sandboxing is requested. */
export function wrapArgvForHostSandbox(
  argv: string[],
  options: {
    cwd?: string;
    home?: string;
    env?: NodeJS.ProcessEnv;
    platform?: NodeJS.Platform;
  } = {},
): { argv: string[] } | { error: string } {
  const env = options.env ?? process.env;
  if (!isHostSandboxEnabled(env)) return { argv };

  const cwd = resolve(options.cwd ?? env.PWD ?? process.cwd());
  const home = options.home ?? env.HOME ?? homedir();
  const platform = options.platform ?? process.platform;

  if (platform === "darwin") return wrapDarwin(argv, { cwd, home, env });
  if (platform === "linux") return wrapLinux(argv, { cwd, env });
  return {
    error: `JUNO_HOST_SANDBOX=1 is not supported on ${platform}. Refusing the install.`,
  };
}
