/**
 * Cursor beforeShellExecution gating for package installs.
 *
 * MCP and PATH wraps still depend on cooperation. This hook denies bare
 * npm/pnpm/yarn/pip install shells inside Cursor so the agent must use
 * `juno <manager> …` or the MCP `guard_install` tool first.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

export type ShellPermission = "allow" | "deny";

export interface ShellDecision {
  permission: ShellPermission;
  user_message?: string;
  agent_message?: string;
}

const INSTALL_VERBS = new Set(["install", "i", "add", "ci"]);

/** True when the shell already routes through the juno CLI / package entrypoint. */
export function isAlreadyJunoGated(command: string): boolean {
  const normalized = command.replace(/\uFEFF/g, "").trim();
  if (/\bjuno\b/.test(normalized) && /\b(npm|pnpm|yarn|pip)\b/.test(normalized)) {
    return true;
  }
  if (/@heysalad\/junoguard\b/.test(normalized) && /\b(npm|pnpm|yarn|pip)\b/.test(normalized)) {
    return true;
  }
  if (/junoguard(?:\.js|\.mjs)?\b/.test(normalized) && /\b(npm|pnpm|yarn|pip)\b/.test(normalized)) {
    return true;
  }
  return false;
}

/**
 * Detect package-manager install verbs, including absolute paths and simple
 * compound shells (`cd x && npm install y`).
 */
export function isUngatedInstallCommand(command: string): boolean {
  if (isAlreadyJunoGated(command)) return false;

  const normalized = command.replace(/\uFEFF/g, "");
  // Split on common shell separators without a full shell parser.
  const segments = normalized.split(/(?:&&|\|\||;|\n)/);
  for (const segment of segments) {
    const tokens = tokenize(segment);
    if (tokensLookLikeInstall(tokens)) return true;
  }
  return false;
}

function tokenize(segment: string): string[] {
  return segment
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => token.replace(/^['"]|['"]$/g, ""));
}

function basenameCommand(token: string): string {
  const cleaned = token.replace(/^\.?\//, "");
  const parts = cleaned.split(/[\\/]/);
  return (parts[parts.length - 1] ?? cleaned).toLowerCase();
}

function tokensLookLikeInstall(tokens: string[]): boolean {
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]!;
    const base = basenameCommand(token);

    if (base === "npm" || base === "pnpm" || base === "yarn") {
      const verb = tokens[index + 1]?.toLowerCase();
      // `npm run <script>` is never a registry install, even when the script is
      // named "install". Only the direct install/add/ci verbs are gated.
      if (verb && INSTALL_VERBS.has(verb)) return true;
    }

    if (base === "pip" || base === "pip3") {
      const verb = tokens[index + 1]?.toLowerCase();
      if (verb === "install") return true;
    }

    if ((base === "python" || base === "python3") && tokens[index + 1] === "-m") {
      const module = tokens[index + 2]?.toLowerCase();
      const verb = tokens[index + 3]?.toLowerCase();
      if ((module === "pip" || module === "pip3") && verb === "install") return true;
    }
  }
  return false;
}

export function decideBeforeShell(command: string): ShellDecision {
  if (!isUngatedInstallCommand(command)) {
    return { permission: "allow" };
  }

  const agent_message = [
    "Package install blocked by JunoGuard.",
    "Use the MCP tool guard_install, or run through the CLI:",
    "  juno npm|pnpm|yarn|pip install <package>...",
    "Bare package-manager installs are refused so a postinstall cannot run before a verdict.",
  ].join("\n");

  return {
    permission: "deny",
    user_message: "JunoGuard blocked an ungated package install.",
    agent_message,
  };
}

export function parseHookStdin(raw: string): { command: string } {
  const text = raw.replace(/^\uFEFF/, "").trim() || "{}";
  const payload = JSON.parse(text) as { command?: unknown };
  return { command: typeof payload.command === "string" ? payload.command : "" };
}

export function hookShellResponse(rawStdin: string): string {
  try {
    const { command } = parseHookStdin(rawStdin);
    return `${JSON.stringify(decideBeforeShell(command))}\n`;
  } catch (error) {
    // failClosed hooks treat invalid JSON / crashes as deny. Emit an explicit
    // deny body as well so operators see why when the host surfaces it.
    const detail = error instanceof Error ? error.message : String(error);
    return `${JSON.stringify({
      permission: "deny",
      user_message: "JunoGuard install hook failed closed.",
      agent_message: `JunoGuard could not inspect the shell command (${detail}). The install was refused.`,
    })}\n`;
  }
}

export interface CursorHookWriteResult {
  kind: "written" | "exists" | "unparseable";
  path: string;
  created?: boolean;
  snippet?: string;
}

export function cursorHooksPath(scope: "project" | "global", cwd: string): string {
  return scope === "project"
    ? join(cwd, ".cursor", "hooks.json")
    : join(homedir(), ".cursor", "hooks.json");
}

export function buildCursorHookEntry(command: string): Record<string, unknown> {
  return {
    command,
    failClosed: true,
    matcher: String.raw`\b(npm|pnpm|yarn|pip3?|python3?)\b`,
  };
}

/**
 * Merge the JunoGuard beforeShellExecution entry into Cursor hooks.json.
 * Never removes unrelated hooks.
 */
export function writeCursorHooks(
  scope: "project" | "global",
  cwd: string,
  hookCommand: string,
  options: { force?: boolean; dryRun?: boolean; hooksPath?: string } = {},
): CursorHookWriteResult {
  const path = options.hooksPath ?? cursorHooksPath(scope, cwd);
  const existed = existsSync(path);
  const original = existed ? readFileSync(path, "utf8") : "";
  const entry = buildCursorHookEntry(hookCommand);

  let config: Record<string, unknown> = { version: 1, hooks: {} };
  if (existed && original.trim()) {
    try {
      config = JSON.parse(original) as Record<string, unknown>;
    } catch {
      return {
        kind: "unparseable",
        path,
        snippet: JSON.stringify({ version: 1, hooks: { beforeShellExecution: [entry] } }, null, 2),
      };
    }
  }

  if (typeof config.version !== "number") config.version = 1;
  const hooks = (config.hooks ?? {}) as Record<string, unknown>;
  const before = Array.isArray(hooks.beforeShellExecution)
    ? ([...hooks.beforeShellExecution] as Record<string, unknown>[])
    : [];

  const marker = "junoguard";
  const existingIndex = before.findIndex((item) => {
    const command = typeof item?.command === "string" ? item.command : "";
    return command.includes(marker) || command.includes("hook shell");
  });

  if (existingIndex >= 0 && !options.force) {
    return { kind: "exists", path };
  }

  if (existingIndex >= 0) before[existingIndex] = entry;
  else before.push(entry);

  hooks.beforeShellExecution = before;
  config.hooks = hooks;

  if (!options.dryRun) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  }

  return { kind: "written", path, created: !existed };
}
