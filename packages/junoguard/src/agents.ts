/**
 * Where each AI coding agent keeps its MCP config, and how to write into it.
 *
 * Every path and key here was verified against a real installation rather than
 * recalled — the formats differ in ways that are easy to get subtly wrong:
 * VS Code uses `servers`, not `mcpServers`; Codex is TOML, not JSON; Claude
 * Code's user-level config is a large state file we refuse to rewrite.
 *
 * Rules this module holds to:
 *   - never clobber an existing junoguard entry without --force
 *   - never destroy a config we cannot parse; print the snippet instead
 *   - never write a partial file
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";

export type Scope = "project" | "global";
export type Format = "json" | "toml";

export interface ServerEntry {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface AgentTarget {
  id: string;
  label: string;
  /** Config file for this scope, or null when the agent has no such scope. */
  path(scope: Scope, cwd: string): string | null;
  format: Format;
  /** Top-level key holding the server map. */
  rootKey: string;
  /** Extra fields this agent expects on each server entry. */
  extra?: Record<string, string>;
  /** Shown when a scope is unsupported, e.g. use the agent's own CLI. */
  note?: (scope: Scope, packageName: string) => string | null;
}

const home = homedir();

function vsCodeUserDir(): string {
  if (platform() === "darwin") return join(home, "Library", "Application Support", "Code", "User");
  if (platform() === "win32") return join(process.env.APPDATA ?? home, "Code", "User");
  return join(process.env.XDG_CONFIG_HOME ?? join(home, ".config"), "Code", "User");
}

export const AGENTS: AgentTarget[] = [
  {
    id: "cursor",
    label: "Cursor",
    format: "json",
    rootKey: "mcpServers",
    path: (scope, cwd) =>
      scope === "project" ? join(cwd, ".cursor", "mcp.json") : join(home, ".cursor", "mcp.json"),
  },
  {
    id: "claude-code",
    label: "Claude Code",
    format: "json",
    rootKey: "mcpServers",
    // ~/.claude.json is a large application state file. Writing it risks the
    // user's whole configuration, so user scope defers to Claude Code's CLI.
    path: (scope, cwd) => (scope === "project" ? join(cwd, ".mcp.json") : null),
    note: (scope, packageName) =>
      scope === "global"
        ? `user scope: run  claude mcp add -s user junoguard -- npx -y ${packageName} mcp`
        : null,
  },
  {
    id: "codex",
    label: "Codex",
    format: "toml",
    rootKey: "mcp_servers",
    path: (scope) => (scope === "global" ? join(home, ".codex", "config.toml") : null),
    note: (scope) => (scope === "project" ? "Codex reads user-level config only; use --global" : null),
  },
  {
    id: "vscode",
    label: "VS Code",
    format: "json",
    rootKey: "servers",
    extra: { type: "stdio" },
    path: (scope, cwd) =>
      scope === "project" ? join(cwd, ".vscode", "mcp.json") : join(vsCodeUserDir(), "mcp.json"),
  },
  {
    id: "windsurf",
    label: "Windsurf",
    format: "json",
    rootKey: "mcpServers",
    path: (scope) =>
      scope === "global" ? join(home, ".codeium", "windsurf", "mcp_config.json") : null,
    note: (scope) => (scope === "project" ? "Windsurf reads user-level config only; use --global" : null),
  },
];

export function findAgent(id: string): AgentTarget | undefined {
  return AGENTS.find((agent) => agent.id === id.toLowerCase());
}

/** Agents with an existing config file — a decent proxy for "installed". */
export function detectAgents(cwd: string): AgentTarget[] {
  return AGENTS.filter((agent) =>
    (["project", "global"] as Scope[]).some((scope) => {
      const path = agent.path(scope, cwd);
      return path !== null && existsSync(path);
    }),
  );
}

export type WriteOutcome =
  | { kind: "written"; path: string; created: boolean }
  | { kind: "exists"; path: string }
  | { kind: "unsupported"; note: string }
  | { kind: "unparseable"; path: string; snippet: string };

export function writeConfig(
  agent: AgentTarget,
  scope: Scope,
  cwd: string,
  name: string,
  entry: ServerEntry,
  options: { force?: boolean; dryRun?: boolean; packageName?: string } = {},
): WriteOutcome {
  const path = agent.path(scope, cwd);
  if (path === null) {
    const note =
      agent.note?.(scope, options.packageName ?? "@heysalad/junoguard") ??
      `${agent.label} has no ${scope} scope`;
    return { kind: "unsupported", note };
  }

  const payload = { ...entry, ...(agent.extra ?? {}) };
  const existed = existsSync(path);
  const original = existed ? readFileSync(path, "utf8") : "";

  if (agent.format === "toml") {
    if (original.includes(`[${agent.rootKey}.${name}]`) && !options.force) {
      return { kind: "exists", path };
    }
    const block = tomlBlock(agent.rootKey, name, payload);
    if (!options.dryRun) {
      mkdirSync(dirname(path), { recursive: true });
      // Appending a table at end-of-file is always valid TOML, and leaves the
      // rest of the user's config byte-for-byte untouched.
      const separator = original.length && !original.endsWith("\n") ? "\n" : "";
      writeFileSync(path, `${original}${separator}\n${block}`, "utf8");
    }
    return { kind: "written", path, created: !existed };
  }

  let config: Record<string, unknown> = {};
  if (existed && original.trim()) {
    try {
      config = JSON.parse(original) as Record<string, unknown>;
    } catch {
      // Could be JSONC, or simply broken. Either way, refuse to overwrite it.
      return { kind: "unparseable", path, snippet: jsonSnippet(agent.rootKey, name, payload) };
    }
  }

  const servers = (config[agent.rootKey] ?? {}) as Record<string, unknown>;
  if (servers[name] && !options.force) return { kind: "exists", path };

  servers[name] = payload;
  config[agent.rootKey] = servers;

  if (!options.dryRun) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  }
  return { kind: "written", path, created: !existed };
}

function tomlString(value: string): string {
  return JSON.stringify(value); // TOML basic strings match JSON string escaping
}

function tomlBlock(rootKey: string, name: string, entry: Record<string, unknown>): string {
  const lines = [`[${rootKey}.${name}]`];
  lines.push(`command = ${tomlString(String(entry.command))}`);
  const args = (entry.args as string[]) ?? [];
  lines.push(`args = [${args.map(tomlString).join(", ")}]`);
  const env = (entry.env as Record<string, string>) ?? {};
  const pairs = Object.entries(env).map(([key, value]) => `${key} = ${tomlString(value)}`);
  if (pairs.length) lines.push(`env = { ${pairs.join(", ")} }`);
  return `${lines.join("\n")}\n`;
}

function jsonSnippet(rootKey: string, name: string, entry: Record<string, unknown>): string {
  return JSON.stringify({ [rootKey]: { [name]: entry } }, null, 2);
}
