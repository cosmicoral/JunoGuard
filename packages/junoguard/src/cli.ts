/**
 * `juno` — JunoGuard on the command line.
 *
 * The forwarders (`juno npm|pnpm|yarn install`, `juno pip install`) are the
 * point: scan first, and only spawn the real package manager if every package
 * came back clean. A block prints the refusal, exits non-zero, and never
 * reaches the package manager. So does an unreachable gateway — a guard that
 * cannot be consulted is not permission to proceed.
 *
 * Argument parsing is hand-rolled rather than delegated to a parser, because
 * the forwarder must hand npm its flags in the user's original order and every
 * parser wants to interpret them first.
 */

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import pc from "picocolors";

import {
  AGENTS,
  detectAgents,
  findAgent,
  writeConfig,
  type Scope,
  type ServerEntry,
} from "./agents.js";
import { DEFAULT_API_URL, JunoClient, JunoNotConfigured, JunoUnavailable } from "./client.js";
import { SCRIPT, clockNow, diffStatus, renderEvent, type Event } from "./feed.js";
import {
  hookShellResponse,
  writeCursorHooks,
} from "./hooks.js";
import {
  renderError,
  renderInstall,
  renderNotConfigured,
  renderStatus,
  type Line,
  type Style,
} from "./render.js";
import type { Ecosystem, StatusResult } from "./types.js";
import {
  disableWrap,
  enableWrap,
  resolveRealBinary,
  wrapStatus,
} from "./wrap.js";

// 0 clean · 2 blocked by policy · 3 guard unreachable. Distinct so CI can tell
// "Juno said no" from "Juno was down", which are different problems.
const EXIT_OK = 0;
const EXIT_BLOCKED = 2;
const EXIT_UNAVAILABLE = 3;
const EXIT_NOT_CONFIGURED = 4;
// Distinct from a policy block: nothing was evaluated, so there is no verdict —
// only an absence of one, which is still a refusal.
const EXIT_UNSCANNABLE = 5;

const PAINT: Record<Style, (value: string) => string> = {
  "": (value) => value,
  block: (value) => pc.bold(pc.red(value)),
  flag: (value) => pc.bold(pc.yellow(value)),
  allow: (value) => pc.green(value),
  label: (value) => pc.bold(value),
  dim: (value) => pc.dim(value),
  key: (value) => pc.cyan(value),
};

function paint(lines: Line[]): string {
  return lines.map((line) => line.map(([text, style]) => PAINT[style](text)).join("")).join("\n");
}

const out = (lines: Line[]) => console.log(paint(lines));
const err = (lines: Line[]) => console.error(paint(lines));
const say = (text: string, style: Style = "") => console.log(PAINT[style](text));

function printEvent(event: Event): void {
  console.log(paint([renderEvent(event, clockNow())]));
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// --------------------------------------------------------------------------
// shared helpers
// --------------------------------------------------------------------------

function unreachable(subject: string, error: unknown, consequence: string): never {
  if (error instanceof JunoNotConfigured) {
    err(renderNotConfigured(subject, new JunoClient().apiUrl));
    process.exit(EXIT_NOT_CONFIGURED);
  }
  const detail = error instanceof JunoUnavailable ? error.detail : String(error);
  err(renderError(subject, detail, consequence));
  process.exit(EXIT_UNAVAILABLE);
}

async function scanOne(
  client: JunoClient,
  pkg: string,
  ecosystem: Ecosystem,
  version?: string,
): Promise<string> {
  let payload;
  try {
    payload = await client.guardInstall(pkg, ecosystem, version);
  } catch (error) {
    unreachable(
      `${pkg}  (${ecosystem})`,
      error,
      "The guard could not be consulted, so nothing was installed.\n" +
        "Start the JunoGuard gateway, or re-run with JUNO_MOCK=1.",
    );
  }
  out(renderInstall(payload, pkg, ecosystem));
  if (payload.decision !== "allow") console.log();
  return payload.decision;
}

// --------------------------------------------------------------------------
// commands
// --------------------------------------------------------------------------

async function cmdStatus(): Promise<number> {
  const client = new JunoClient();
  try {
    out(renderStatus(await client.status()));
  } catch (error) {
    unreachable(
      "project status",
      error,
      "No budget or incident data is available.\n" +
        "Start the JunoGuard gateway, or re-run with JUNO_MOCK=1.",
    );
  }
  if (client.mock) say("\noffline fixtures (JUNO_MOCK=1) — not live gateway data", "dim");
  return EXIT_OK;
}

async function cmdScan(argv: string[]): Promise<number> {
  const flags = parseFlags(argv);
  const pkg = flags.positional[0];
  if (!pkg) {
    say("usage: juno scan <package> [--ecosystem npm|pypi] [--package-version X]", "flag");
    return 1;
  }
  const ecosystem = (flags.values.ecosystem ?? flags.values.e ?? "npm") as Ecosystem;
  const decision = await scanOne(
    new JunoClient(),
    pkg,
    ecosystem,
    flags.values["package-version"],
  );
  return decision === "block" ? EXIT_BLOCKED : EXIT_OK;
}

// Tokens we cannot scan by name: flags, their values, local paths, and direct
// git/http installs. Scoped npm names like @scope/pkg must survive this.
const UNSCANNABLE = /^(-|\.|\/|~|file:|git\+|git:|https?:)/;

/** Our own flags, stripped before anything is handed to npm or pip. */
const OWN_FLAGS = new Set([
  "--allow-unscanned",
  "--allow-flagged",
  "--reason",
  "--operator",
]);

interface Override {
  allowed: boolean;
  allowFlagged: boolean;
  reason?: string;
  operator?: string;
}

function extractOverride(tokens: string[]): { rest: string[]; override: Override } {
  const rest: string[] = [];
  const override: Override = { allowed: false, allowFlagged: false };
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i]!;
    if (!OWN_FLAGS.has(token)) {
      rest.push(token);
      continue;
    }
    if (token === "--allow-unscanned") override.allowed = true;
    if (token === "--allow-flagged") override.allowFlagged = true;
    if (token === "--reason") override.reason = tokens[++i];
    if (token === "--operator") override.operator = tokens[++i];
  }
  return { rest, override };
}

/**
 * Refuse an install nobody can scan, and say exactly what would authorize it.
 *
 * A lockfile-only install, a local archive, a Git or URL source: Juno cannot
 * evaluate any of them by name. Running the package manager anyway with a
 * warning printed above it was the gap that made "an agent cannot route around
 * the gate" untrue — an agent that reads the warning still gets its package.
 */
function refuseUnscannable(
  sources: string[],
  manager: string,
  kind: "lockfile" | "sources",
): number {
  err([
    [["", ""]],
    [[`JUNO · REFUSED — NOTHING TO SCAN`, "block"]],
    [[``, ""]],
    kind === "lockfile"
      ? [[`No package was named, so ${manager} would resolve from a lockfile.`, ""]]
      : [[`These sources cannot be scanned by name: ${sources.join(", ")}`, ""]],
    [[`${manager} was not run.`, "block"]],
    [[``, ""]],
    [[`An unscannable source needs a named human to take responsibility:`, "dim"]],
    [
      [
        `  juno ${manager} install … --allow-unscanned --reason "<why>" --operator "<you>"`,
        "key",
      ],
    ],
    [[`The override is recorded against the project as an audited gap in`, "dim"]],
    [[`coverage. If it cannot be recorded, the install still does not happen.`, "dim"]],
  ]);
  return EXIT_UNSCANNABLE;
}

function refuseFlagged(packages: string[], manager: string): number {
  err([
    [["", ""]],
    [[`JUNO · REFUSED — FLAGGED PACKAGE`, "block"]],
    [[``, ""]],
    [[`Flagged packages are not clean enough to install unattended:`, ""]],
    [[`  ${packages.join(", ")}`, "key"]],
    [[`${manager} was not run.`, "block"]],
    [[``, ""]],
    [[`A named human can accept the risk with an audited override:`, "dim"]],
    [
      [
        `  juno ${manager} install … --allow-flagged --reason "<why>" --operator "<you>"`,
        "key",
      ],
    ],
  ]);
  return EXIT_BLOCKED;
}

async function recordOverride(
  sources: string[],
  ecosystem: Ecosystem,
  manager: string,
  override: Override,
  kind: "unscanned" | "flagged" = "unscanned",
): Promise<boolean> {
  const operator = override.operator ?? process.env.JUNO_OPERATOR;
  const flag = kind === "flagged" ? "--allow-flagged" : "--allow-unscanned";
  if (!override.reason || !operator) {
    err([
      [[`${flag} needs both --reason and --operator.`, "block"]],
      [[`  (--operator may come from the JUNO_OPERATOR environment variable.)`, "dim"]],
    ]);
    return false;
  }

  const client = new JunoClient();
  try {
    const payload = await client.reportUnscanned({
      sources,
      ecosystem,
      manager,
      reason: override.reason,
      operator,
    });
    say(`override recorded — ${payload.reason ?? "logged"}`, "flag");
    if (client.mock) {
      say("JUNO_MOCK=1: nothing was actually recorded anywhere.", "block");
      return false;
    }
    return true;
  } catch (error) {
    // Unrecordable overrides are exactly what an attacker would want, so this
    // fails closed rather than proceeding on trust.
    const detail = error instanceof JunoUnavailable ? error.detail : String(error);
    err([
      [[`The override could not be recorded: ${detail}`, "block"]],
      [[`${manager} was not run. An unlogged override is not an override.`, "block"]],
    ]);
    return false;
  }
}

async function cmdForward(
  tokens: string[],
  ecosystem: Ecosystem,
  argv0: string[],
  manager: string,
): Promise<number> {
  const { rest, override } = extractOverride(tokens);
  const packages = rest.filter((token) => !UNSCANNABLE.test(token));
  const passthrough = rest.filter((token) => UNSCANNABLE.test(token));
  const unscanned = passthrough.filter((token) => !token.startsWith("-"));

  // No package named at all: a lockfile install, which resolves whatever the
  // lockfile says and is therefore entirely unscanned.
  if (!packages.length && !unscanned.length) {
    if (!override.allowed) return refuseUnscannable([], manager, "lockfile");
    if (!(await recordOverride([`${manager} lockfile`], ecosystem, manager, override))) {
      return EXIT_UNSCANNABLE;
    }
    return exec([...argv0, ...rest], manager);
  }

  if (unscanned.length && !override.allowed) {
    return refuseUnscannable(unscanned, manager, "sources");
  }
  if (unscanned.length && !(await recordOverride(unscanned, ecosystem, manager, override))) {
    return EXIT_UNSCANNABLE;
  }

  const client = new JunoClient();
  const blocked: string[] = [];
  const flagged: string[] = [];
  for (const pkg of packages) {
    const decision = await scanOne(client, pkg, ecosystem);
    if (decision === "block") blocked.push(pkg);
    else if (decision === "flag") flagged.push(pkg);
  }

  if (blocked.length) {
    say(
      `${manager} was not run. ${blocked.length} of ${packages.length} ` +
        `package${packages.length === 1 ? "" : "s"} blocked: ${blocked.join(", ")}`,
      "block",
    );
    return EXIT_BLOCKED;
  }

  // A flag is a proceedable gateway decision for operators watching the feed,
  // not permission for an unattended CLI install to reach disk.
  if (flagged.length) {
    if (!override.allowFlagged) return refuseFlagged(flagged, manager);
    if (
      !(await recordOverride(
        flagged.map((pkg) => `flagged:${pkg}`),
        ecosystem,
        manager,
        override,
        "flagged",
      ))
    ) {
      return EXIT_BLOCKED;
    }
  }

  return exec([...argv0, ...rest], manager);
}

/** Lifecycle scripts run with full host credentials — keep them off by default. */
export function withIgnoredScripts(cmd: string[], manager: string): string[] {
  if (manager === "pip" || manager === "yarn") return cmd;
  if (manager !== "npm" && manager !== "pnpm") return cmd;
  if (cmd.includes("--ignore-scripts") || cmd.includes("--no-ignore-scripts")) return cmd;
  // Insert after the verb (`install` / `add`) so npm/pnpm still see it as a flag.
  if (cmd.length < 2) return [...cmd, "--ignore-scripts"];
  return [cmd[0]!, cmd[1]!, "--ignore-scripts", ...cmd.slice(2)];
}

function exec(cmd: string[], manager: string): Promise<number> {
  const gated = withIgnoredScripts(cmd, manager);
  const real = resolveRealBinary(gated[0] ?? manager);
  const argv = [real, ...gated.slice(1)];
  say(`$ ${argv.join(" ")}`, "dim");
  return new Promise((resolve) => {
    const child = spawn(argv[0]!, argv.slice(1), { stdio: "inherit", shell: false });
    child.on("error", () => {
      say(`${manager} is not on PATH`, "block");
      resolve(EXIT_UNAVAILABLE);
    });
    child.on("close", (code) => resolve(code ?? 0));
  });
}

function cmdWrap(argv: string[]): number {
  const [sub] = argv;
  if (!sub || sub === "status" || sub === "-h" || sub === "--help") {
    if (sub === "-h" || sub === "--help") {
      say("usage: juno wrap on|off|status", "flag");
      return sub ? EXIT_OK : 1;
    }
    const status = wrapStatus();
    if (!status.active.length) {
      say("PATH wrap is off. Run: juno wrap on", "flag");
      return EXIT_OK;
    }
    say(`PATH wrap active in ${status.dir}`, "allow");
    say(`shims: ${status.active.join(", ")}`, "dim");
    if (status.pathPrefixed) {
      say("this directory is already first on PATH", "dim");
    } else {
      say("put the wrap directory first on PATH:", "flag");
      say(`  export PATH="${status.dir}:$PATH"`, "key");
    }
    say(
      "residual: absolute paths to the real package manager still bypass the wrap",
      "dim",
    );
    return EXIT_OK;
  }

  if (sub === "on") {
    const { dir, created } = enableWrap();
    say(`wrote ${created.length} shims in ${dir}`, "allow");
    say("put the wrap directory first on PATH for this shell:", "flag");
    say(`  export PATH="${dir}:$PATH"`, "key");
    say(
      "bare npm/pnpm/yarn/pip install now routes through JunoGuard. Absolute paths still bypass.",
      "dim",
    );
    return EXIT_OK;
  }

  if (sub === "off") {
    const { dir, removed } = disableWrap();
    if (!removed.length) {
      say(`PATH wrap already off (${dir})`, "dim");
      return EXIT_OK;
    }
    say(`removed ${removed.length} shims from ${dir}`, "allow");
    return EXIT_OK;
  }

  say(`unknown wrap command "${sub}" — use on, off, or status`, "block");
  return 1;
}

async function cmdWatch(argv: string[]): Promise<number> {
  const flags = parseFlags(argv);
  const interval = Number(flags.values.interval ?? flags.values.i ?? 2) * 1000;
  const client = new JunoClient();

  say(
    `watching ${client.mock ? "offline fixtures" : client.apiUrl}  ·  ctrl-c to stop`,
    "dim",
  );
  console.log();

  if (client.mock) {
    for (;;) {
      for (const event of SCRIPT) {
        printEvent(event);
        await sleep(Math.max(200, interval * 0.6));
      }
    }
  }

  let previous: StatusResult | null = null;
  for (;;) {
    try {
      const current = await client.status();
      if (previous === null) {
        out(renderStatus(current));
        console.log();
      } else {
        for (const event of diffStatus(previous, current)) printEvent(event);
      }
      previous = current;
    } catch (error) {
      // A missing key will never fix itself by polling harder.
      if (error instanceof JunoNotConfigured) {
        console.log();
        err(renderNotConfigured("live decision feed", client.apiUrl));
        return EXIT_NOT_CONFIGURED;
      }
      const detail = error instanceof JunoUnavailable ? error.detail : String(error);
      printEvent({ decision: "block", lane: "guard", detail: `gateway unreachable — ${detail}` });
    }
    await sleep(interval);
  }
}

function cmdInit(argv: string[], packageName: string): number {
  const flags = parseFlags(argv);
  const scope: Scope = flags.bools.global ? "global" : "project";
  const cwd = process.cwd();
  const dryRun = Boolean(flags.bools["dry-run"]);
  const force = Boolean(flags.bools.force);

  // In mock mode no gateway or key is involved at all. Otherwise carry through
  // whatever is in the environment — and never invent a key, since a config
  // containing a made-up credential looks configured but silently 401s.
  const projectKey = process.env.JUNO_PROJECT_KEY;
  const env: Record<string, string> = flags.bools.mock
    ? { JUNO_MOCK: "1" }
    : {
        JUNO_API_URL: process.env.JUNO_API_URL ?? DEFAULT_API_URL,
        ...(projectKey ? { JUNO_PROJECT_KEY: projectKey } : {}),
      };

  const entry: ServerEntry = {
    command: flags.bools.local ? process.execPath : "npx",
    args: flags.bools.local
      ? [new URL("./bin.js", import.meta.url).pathname, "mcp"]
      : ["-y", packageName, "mcp"],
    env,
  };

  const requested = flags.positional.length
    ? flags.positional.map((id) => {
        const agent = findAgent(id);
        if (!agent) {
          say(`unknown agent "${id}" — known: ${AGENTS.map((a) => a.id).join(", ")}`, "block");
          process.exit(1);
        }
        return agent;
      })
    : detectAgents(cwd);

  if (!requested.length) {
    say("no agent config found to update.", "flag");
    say(`name one explicitly: juno init ${AGENTS.map((a) => a.id).join("|")}`, "dim");
    return 1;
  }

  say(dryRun ? `would write (${scope} scope):` : `wiring junoguard in (${scope} scope):`, "label");
  console.log();

  let failures = 0;
  const hookCommand = flags.bools.local
    ? `${process.execPath} ${new URL("./bin.js", import.meta.url).pathname} hook shell`
    : `npx -y ${packageName} hook shell`;

  for (const agent of requested) {
    const result = writeConfig(agent, scope, cwd, "junoguard", entry, {
      force,
      dryRun,
      packageName,
    });
    const name = agent.label.padEnd(13);
    switch (result.kind) {
      case "written":
        say(`  ✓ ${name}${result.path}${result.created ? "  (created)" : ""}`, "allow");
        break;
      case "exists":
        say(`  · ${name}already configured — use --force to replace`, "dim");
        break;
      case "unsupported":
        say(`  · ${name}${result.note}`, "dim");
        break;
      case "unparseable":
        failures += 1;
        say(`  ✗ ${name}${result.path} is not valid JSON — not touching it`, "block");
        say(`    add this by hand:`, "dim");
        console.log(
          result.snippet
            .split("\n")
            .map((line) => `    ${pc.dim(line)}`)
            .join("\n"),
        );
        break;
    }

    if (agent.id === "cursor") {
      const hooks = writeCursorHooks(scope, cwd, hookCommand, { force, dryRun });
      switch (hooks.kind) {
        case "written":
          say(
            `  ✓ ${"Cursor hooks".padEnd(13)}${hooks.path}${hooks.created ? "  (created)" : ""}`,
            "allow",
          );
          break;
        case "exists":
          say(`  · ${"Cursor hooks".padEnd(13)}already configured — use --force to replace`, "dim");
          break;
        case "unparseable":
          failures += 1;
          say(`  ✗ ${"Cursor hooks".padEnd(13)}${hooks.path} is not valid JSON`, "block");
          if (hooks.snippet) {
            console.log(
              hooks.snippet
                .split("\n")
                .map((line) => `    ${pc.dim(line)}`)
                .join("\n"),
            );
          }
          break;
      }
    }
  }

  console.log();
  if (!flags.bools.mock && !projectKey) {
    // Written, but it will refuse every action until this is set. Say so now
    // rather than letting them discover it mid-demo.
    say("no JUNO_PROJECT_KEY in your environment — the config is incomplete.", "flag");
    say("  add one to the env block above, or re-run with --mock to try it offline.", "dim");
    console.log();
  }
  if (flags.bools.local) {
    say("--local wrote an absolute path to this checkout, for pre-publish testing.", "flag");
  } else {
    say("restart the agent (or refresh its MCP panel) to pick this up.", "dim");
  }
  return failures ? 1 : EXIT_OK;
}

// --------------------------------------------------------------------------
// argv handling
// --------------------------------------------------------------------------

interface Flags {
  positional: string[];
  values: Record<string, string | undefined>;
  bools: Record<string, boolean>;
}

/** Minimal parser for the non-forwarding commands. */
function parseFlags(argv: string[]): Flags {
  const flags: Flags = { positional: [], values: {}, bools: {} };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i]!;
    if (!token.startsWith("-")) {
      flags.positional.push(token);
      continue;
    }
    const name = token.replace(/^--?/, "");
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("-")) {
      flags.values[name] = next;
      flags.bools[name] = true;
      i += 1;
    } else {
      flags.bools[name] = true;
    }
  }
  return flags;
}

const HELP = `
${pc.bold("juno")} — JunoGuard: supervision for what your agent installs and spends.

${pc.bold("USAGE")}
  juno <command> [options]

${pc.bold("COMMANDS")}
  status                    budget, spend, rate limit, open incidents
  scan <package>            scan a package without installing it
  npm install <pkg>...      scan, then run the real npm if all are clean
  pnpm install <pkg>...     scan, then run the real pnpm if all are clean
  yarn add <pkg>...         scan, then run the real yarn if all are clean
  pip install <pkg>...      scan, then run the real pip if all are clean
  wrap on|off|status        project PATH shims so bare installs hit the gate
  hook shell                Cursor beforeShellExecution gate (stdin JSON)
  watch                     tail the live decision feed
  init [agent]...           wire junoguard into an AI coding agent
  mcp                       run the MCP server over stdio

${pc.bold("WRAP")}
  juno wrap on              write .junoguard/bin shims for npm, pnpm, yarn, pip
  juno wrap off             remove those shims
  juno wrap status          show whether PATH includes the wrap directory
  Absolute paths to the real package manager still bypass the wrap.

${pc.bold("INIT")}
  juno init                 detect installed agents, configure each
  juno init cursor codex    configure named agents
  agents: ${AGENTS.map((a) => a.id).join(", ")}
  --global                  user-level config instead of project-level
  --dry-run                 show what would change, write nothing
  --force                   replace an existing junoguard entry
  --mock                    write JUNO_MOCK=1 into the agent's env
  --local                   point at this checkout (pre-publish testing)

${pc.bold("SCAN")}
  --ecosystem, -e <npm|pypi>
  --package-version <version>

${pc.bold("UNSCANNABLE / FLAGGED INSTALLS")}
  Lockfile installs and path, URL or Git sources cannot be scanned by name, so
  they are refused. Flagged packages are also refused for unattended installs.
  To take responsibility:
  --allow-unscanned         proceed for unscannable sources
  --allow-flagged           proceed for packages the gateway flagged
  --reason "<why>"          required with either override
  --operator "<you>"        required; or set JUNO_OPERATOR
  The override is recorded against the project. If it cannot be recorded, the
  install does not happen.

${pc.bold("ENVIRONMENT")}
  JUNO_PROJECT_KEY          ${pc.bold("required")} for live use — sent as X-Juno-Key
  JUNO_API_URL              gateway base URL (default ${DEFAULT_API_URL})
  JUNO_MOCK=1               offline fixtures, no network, no key needed
  JUNO_TIMEOUT              seconds before a gateway call gives up

${pc.bold("TRY IT WITHOUT A GATEWAY")}
  JUNO_MOCK=1 juno scan @ossprey/test-package

${pc.bold("EXIT CODES")}
  0 allowed · 2 blocked by policy · 3 guard unreachable · 4 not configured
  5 refused: nothing to scan
`.trim();

export async function main(
  argv: string[],
  pkg: { name: string; version: string },
): Promise<number> {
  const { name: packageName, version } = pkg;
  const [command, ...rest] = argv;

  switch (command) {
    case undefined:
    case "-h":
    case "--help":
    case "help":
      console.log(HELP);
      return command === undefined ? 1 : EXIT_OK;

    case "-v":
    case "--version":
      console.log(version);
      return EXIT_OK;

    case "status":
      return cmdStatus();

    case "scan":
      return cmdScan(rest);

    case "watch":
      return cmdWatch(rest);

    case "init":
      return cmdInit(rest, packageName);

    case "wrap":
      return cmdWrap(rest);

    case "hook": {
      const [sub] = rest;
      if (sub !== "shell") {
        say("usage: juno hook shell   (reads Cursor hook stdin JSON)", "flag");
        return 1;
      }
      const raw = readFileSync(0, "utf8");
      process.stdout.write(hookShellResponse(raw));
      return EXIT_OK;
    }

    case "mcp": {
      // Imported lazily so the CLI path never pays for the MCP SDK.
      const mcp = await import("./mcp.js");
      if (rest.includes("--verify")) return mcp.cmdVerify(version);
      if (rest.includes("--update-lock")) return mcp.cmdUpdateLock(version);
      await mcp.runStdioServer(version);
      return new Promise<number>(() => {}); // stdio server owns the process
    }

    case "npm":
    case "pnpm":
    case "yarn":
    case "pip": {
      const [sub, ...tokens] = rest;
      const forwarders: Record<
        string,
        { ecosystem: Ecosystem; verbs: string[]; argv: (verb: string) => string[] }
      > = {
        npm: {
          ecosystem: "npm",
          verbs: ["install", "i", "add"],
          argv: () => ["npm", "install"],
        },
        pnpm: {
          ecosystem: "npm",
          verbs: ["install", "i", "add"],
          argv: (verb) => ["pnpm", verb === "i" ? "install" : verb],
        },
        yarn: {
          ecosystem: "npm",
          verbs: ["add", "install"],
          argv: (verb) => ["yarn", verb],
        },
        pip: {
          ecosystem: "pypi",
          verbs: ["install"],
          argv: () => ["pip", "install"],
        },
      };
      const forwarder = forwarders[command]!;
      if (!sub || !forwarder.verbs.includes(sub)) {
        const preferred = command === "yarn" ? "add" : "install";
        say(`usage: juno ${command} ${preferred} <package>...`, "flag");
        return 1;
      }
      return cmdForward(tokens, forwarder.ecosystem, forwarder.argv(sub), command);
    }

    default:
      say(`unknown command "${command}"`, "block");
      console.log(HELP);
      return 1;
  }
}
