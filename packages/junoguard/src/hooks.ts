/**
 * Agent shell gating for package installs.
 *
 * MCP and PATH wraps still depend on cooperation. These hooks deny bare
 * npm/pnpm/yarn/pip install shells so the agent must use `juno <manager> …`
 * or the MCP `guard_install` tool first.
 *
 * Supported hosts:
 *   - Cursor `beforeShellExecution` (permission / user_message / agent_message)
 *   - Claude Code `PreToolUse` Bash (hookSpecificOutput.permissionDecision)
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

export type ShellPermission = "allow" | "deny";
export type HookHost = "cursor" | "claude";

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

export function detectHookHost(payload: Record<string, unknown>): HookHost {
  if (typeof payload.tool_name === "string" || typeof payload.tool_input === "object") {
    return "claude";
  }
  const event = payload.hook_event_name ?? payload.hookEventName;
  if (typeof event === "string" && /pretooluse/i.test(event)) return "claude";
  return "cursor";
}

export function extractShellCommand(payload: Record<string, unknown>): string {
  if (typeof payload.command === "string") return payload.command;

  const toolInput = payload.tool_input;
  if (toolInput && typeof toolInput === "object") {
    const command = (toolInput as { command?: unknown }).command;
    if (typeof command === "string") return command;
  }

  return "";
}

export function parseHookStdin(raw: string): { command: string; host: HookHost } {
  const text = raw.replace(/^\uFEFF/, "").trim() || "{}";
  const payload = JSON.parse(text) as Record<string, unknown>;
  return {
    command: extractShellCommand(payload),
    host: detectHookHost(payload),
  };
}

function cursorHookBody(decision: ShellDecision): Record<string, unknown> {
  const body: Record<string, unknown> = { permission: decision.permission };
  if (decision.user_message) body.user_message = decision.user_message;
  if (decision.agent_message) body.agent_message = decision.agent_message;
  return body;
}

function claudeHookBody(decision: ShellDecision): Record<string, unknown> {
  if (decision.permission === "allow") {
    return {
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "allow",
      },
    };
  }

  const reason =
    decision.agent_message ??
    decision.user_message ??
    "JunoGuard blocked an ungated package install.";

  return {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: reason,
    },
    systemMessage: reason,
  };
}

export function formatHookResponse(host: HookHost, decision: ShellDecision): string {
  const body = host === "claude" ? claudeHookBody(decision) : cursorHookBody(decision);
  return `${JSON.stringify(body)}\n`;
}

export function hookShellResponse(rawStdin: string): string {
  try {
    const { command, host } = parseHookStdin(rawStdin);
    return formatHookResponse(host, decideBeforeShell(command));
  } catch (error) {
    // failClosed hooks treat invalid JSON / crashes as deny. Emit an explicit
    // deny body as well so operators see why when the host surfaces it.
    const detail = error instanceof Error ? error.message : String(error);
    const decision: ShellDecision = {
      permission: "deny",
      user_message: "JunoGuard install hook failed closed.",
      agent_message: `JunoGuard could not inspect the shell command (${detail}). The install was refused.`,
    };
    // Prefer Cursor shape on parse failure — Claude still understands deny via
    // fail-closed host behaviour when JSON is unusable; Cursor needs the body.
    try {
      const text = rawStdin.replace(/^\uFEFF/, "").trim();
      if (text) {
        const payload = JSON.parse(text) as Record<string, unknown>;
        return formatHookResponse(detectHookHost(payload), decision);
      }
    } catch {
      // fall through
    }
    return formatHookResponse("cursor", decision);
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

export interface ClaudeHookWriteResult {
  kind: "written" | "exists" | "unparseable";
  path: string;
  created?: boolean;
  snippet?: string;
}

export function claudeSettingsPath(scope: "project" | "global", cwd: string): string {
  return scope === "project"
    ? join(cwd, ".claude", "settings.json")
    : join(homedir(), ".claude", "settings.json");
}

export function buildClaudePreToolUseEntry(command: string): Record<string, unknown> {
  return {
    matcher: "Bash",
    hooks: [
      {
        type: "command",
        command,
      },
    ],
  };
}

function isJunoHookCommand(command: unknown): boolean {
  if (typeof command !== "string") return false;
  return command.includes("junoguard") || command.includes("hook shell");
}

function claudeEntryIsOurs(entry: Record<string, unknown>): boolean {
  const hooks = Array.isArray(entry.hooks) ? entry.hooks : [];
  return hooks.some((item) => {
    if (!item || typeof item !== "object") return false;
    return isJunoHookCommand((item as { command?: unknown }).command);
  });
}

/**
 * Merge the JunoGuard PreToolUse Bash entry into Claude Code settings.json.
 * Never removes unrelated hooks.
 */
export function writeClaudeHooks(
  scope: "project" | "global",
  cwd: string,
  hookCommand: string,
  options: { force?: boolean; dryRun?: boolean; settingsPath?: string } = {},
): ClaudeHookWriteResult {
  const path = options.settingsPath ?? claudeSettingsPath(scope, cwd);
  const existed = existsSync(path);
  const original = existed ? readFileSync(path, "utf8") : "";
  const entry = buildClaudePreToolUseEntry(hookCommand);
  const snippet = JSON.stringify({ hooks: { PreToolUse: [entry] } }, null, 2);

  let config: Record<string, unknown> = {};
  if (existed && original.trim()) {
    try {
      config = JSON.parse(original) as Record<string, unknown>;
    } catch {
      return { kind: "unparseable", path, snippet };
    }
  }

  const hooks = (config.hooks ?? {}) as Record<string, unknown>;
  const preToolUse = Array.isArray(hooks.PreToolUse)
    ? ([...hooks.PreToolUse] as Record<string, unknown>[])
    : [];

  const existingIndex = preToolUse.findIndex((item) => claudeEntryIsOurs(item ?? {}));
  if (existingIndex >= 0 && !options.force) {
    return { kind: "exists", path };
  }

  if (existingIndex >= 0) preToolUse[existingIndex] = entry;
  else preToolUse.push(entry);

  hooks.PreToolUse = preToolUse;
  config.hooks = hooks;

  if (!options.dryRun) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  }

  return { kind: "written", path, created: !existed };
}
