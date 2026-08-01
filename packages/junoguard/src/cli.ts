/**
 * `juno` — JunoGuard on the command line.
 *
 * The forwarders (`juno npm install`, `juno pip install`) are the point: scan
 * first, and only spawn the real package manager if every package came back
 * clean. A block prints the refusal, exits non-zero, and never reaches npm or
 * pip. So does an unreachable gateway — a guard that cannot be consulted is
 * not permission to proceed.
 *
 * Argument parsing is hand-rolled rather than delegated to a parser, because
 * the forwarder must hand npm its flags in the user's original order and every
 * parser wants to interpret them first.
 */

import { spawn } from "node:child_process";
import pc from "picocolors";

import {
  AGENTS,
  detectAgents,
  findAgent,
  writeConfig,
  type Scope,
  type ServerEntry,
} from "./agents.js";
import { DEFAULT_API_URL, DEFAULT_PROJECT_KEY, JunoClient, JunoUnavailable } from "./client.js";
import { SCRIPT, clockNow, diffStatus, renderEvent, type Event } from "./feed.js";
import {
  renderError,
  renderInstall,
  renderStatus,
  type Line,
  type Style,
} from "./render.js";
import type { Ecosystem, StatusResult } from "./types.js";

// 0 clean · 2 blocked by policy · 3 guard unreachable. Distinct so CI can tell
// "Juno said no" from "Juno was down", which are different problems.
const EXIT_OK = 0;
const EXIT_BLOCKED = 2;
const EXIT_UNAVAILABLE = 3;

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

async function cmdForward(
  tokens: string[],
  ecosystem: Ecosystem,
  argv0: string[],
  manager: string,
): Promise<number> {
  const packages = tokens.filter((token) => !UNSCANNABLE.test(token));
  const passthrough = tokens.filter((token) => UNSCANNABLE.test(token));

  if (!packages.length) {
    // A lockfile install, or a path/URL install. Say the run was unguarded
    // rather than implying Juno approved it.
    say(`no scannable package named — running ${manager} unguarded`, "flag");
    return exec([...argv0, ...tokens], manager);
  }

  const unscanned = passthrough.filter((token) => !token.startsWith("-"));
  if (unscanned.length) {
    say(`not scanned (path or URL install): ${unscanned.join(", ")}`, "flag");
  }

  const client = new JunoClient();
  const blocked: string[] = [];
  for (const pkg of packages) {
    if ((await scanOne(client, pkg, ecosystem)) === "block") blocked.push(pkg);
  }

  if (blocked.length) {
    say(
      `${manager} was not run. ${blocked.length} of ${packages.length} ` +
        `package${packages.length === 1 ? "" : "s"} blocked: ${blocked.join(", ")}`,
      "block",
    );
    return EXIT_BLOCKED;
  }

  return exec([...argv0, ...tokens], manager);
}

function exec(cmd: string[], manager: string): Promise<number> {
  say(`$ ${cmd.join(" ")}`, "dim");
  return new Promise((resolve) => {
    const child = spawn(cmd[0]!, cmd.slice(1), { stdio: "inherit", shell: false });
    child.on("error", () => {
      say(`${manager} is not on PATH`, "block");
      resolve(EXIT_UNAVAILABLE);
    });
    child.on("close", (code) => resolve(code ?? 0));
  });
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
      const detail = error instanceof JunoUnavailable ? error.detail : String(error);
      printEvent({ decision: "block", lane: "guard", detail: `gateway unreachable — ${detail}` });
    }
    await sleep(interval);
  }
}

function cmdInit(argv: string[]): number {
  const flags = parseFlags(argv);
  const scope: Scope = flags.bools.global ? "global" : "project";
  const cwd = process.cwd();
  const dryRun = Boolean(flags.bools["dry-run"]);
  const force = Boolean(flags.bools.force);

  const entry: ServerEntry = {
    command: flags.bools.local ? process.execPath : "npx",
    args: flags.bools.local
      ? [new URL("./bin.js", import.meta.url).pathname, "mcp"]
      : ["-y", "junoguard", "mcp"],
    env: {
      JUNO_API_URL: process.env.JUNO_API_URL ?? DEFAULT_API_URL,
      JUNO_PROJECT_KEY: process.env.JUNO_PROJECT_KEY ?? DEFAULT_PROJECT_KEY,
      ...(flags.bools.mock ? { JUNO_MOCK: "1" } : {}),
    },
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
  for (const agent of requested) {
    const result = writeConfig(agent, scope, cwd, "junoguard", entry, { force, dryRun });
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
  }

  console.log();
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
  pip install <pkg>...      scan, then run the real pip if all are clean
  watch                     tail the live decision feed
  init [agent]...           wire junoguard into an AI coding agent
  mcp                       run the MCP server over stdio

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

${pc.bold("ENVIRONMENT")}
  JUNO_API_URL              gateway base URL (default ${DEFAULT_API_URL})
  JUNO_PROJECT_KEY          sent as X-Juno-Key
  JUNO_MOCK=1               offline fixtures, no network at all
  JUNO_TIMEOUT              seconds before a gateway call gives up

${pc.bold("EXIT CODES")}
  0 allowed · 2 blocked by policy · 3 guard unreachable
`.trim();

export async function main(argv: string[], version: string): Promise<number> {
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
      return cmdInit(rest);

    case "mcp": {
      // Imported lazily so the CLI path never pays for the MCP SDK.
      const { runStdioServer } = await import("./mcp.js");
      await runStdioServer(version);
      return new Promise<number>(() => {}); // stdio server owns the process
    }

    case "npm":
    case "pip": {
      const [sub, ...tokens] = rest;
      const isNpm = command === "npm";
      const verbs = isNpm ? ["install", "i", "add"] : ["install"];
      if (!sub || !verbs.includes(sub)) {
        say(`usage: juno ${command} install <package>...`, "flag");
        return 1;
      }
      return cmdForward(
        tokens,
        isNpm ? "npm" : "pypi",
        isNpm ? ["npm", "install"] : ["pip", "install"],
        command,
      );
    }

    default:
      say(`unknown command "${command}"`, "block");
      console.log(HELP);
      return 1;
  }
}
