/**
 * Tool-definition integrity for the published MCP surface.
 *
 * A tool description is not documentation. The model reads it as instruction,
 * so whoever controls it steers the agent. Two attacks follow, both named in
 * docs/threat-landscape.md §2.4:
 *
 * - **Tool poisoning** — instructions hidden in a description no human reads.
 * - **Rug pull** — a server approved while benign later redefines its tools and
 *   keeps the approval. Most clients never alert on the change.
 *
 * This is the package an agent actually runs, so both apply to us directly.
 * Every tool's name, description and schema is hashed into `tools.lock.json`,
 * which is committed and published; the server verifies itself against that
 * lock before it serves anything.
 *
 * What that buys, stated honestly:
 *
 * - A tampered install, a compromised dependency, or an edit that lands after
 *   review cannot silently change what the agent is told. The server refuses to
 *   start and names the tool that moved.
 * - The lock is a git-tracked artefact, so re-pinning is a diff somebody has to
 *   approve. That is the trust root: not this file, the review.
 *
 * What it does not buy: an attacker who edits the source *and* the lock in one
 * reviewed commit is not stopped by a hash. The lock is what makes that visible
 * in a diff.
 */

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Resolves to the package root from both `src/` (tsx) and `dist/` (published). */
export const LOCK_PATH = fileURLToPath(new URL("../tools.lock.json", import.meta.url));

export const LOCK_VERSION = 1;
export const ALGORITHM = "sha256";

/** Serving an unverified surface should take a conscious act at the command line. */
export const UNPINNED_ENV = "JUNO_MCP_ALLOW_UNPINNED";

/**
 * EX_CONFIG. Refusing to start is the alert — the client shows the server red,
 * which is louder than a log line nobody reads.
 */
export const REFUSE_EXIT_CODE = 78;

/**
 * Everything the model or the client can be steered by. Presentation and
 * transport detail the SDK may set differently between versions is excluded on
 * purpose: pinning it produces noisy failures, and noisy failures teach people
 * to re-pin without reading.
 */
const SIGNIFICANT_FIELDS = [
  "name",
  "title",
  "description",
  "inputSchema",
  "outputSchema",
  "annotations",
] as const;

export interface ToolLike {
  name: string;
  [key: string]: unknown;
}

export interface Manifest {
  lock_version: number;
  algorithm: string;
  tools: Record<string, string>;
  surface: string;
}

export interface Report {
  ok: boolean;
  reason: string;
  added: string[];
  removed: string[];
  changed: string[];
}

export interface Decision {
  serve: boolean;
  message: string;
}

/** Stable JSON: sorted keys at every depth, so digests do not depend on key order. */
function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const entries = Object.keys(value as Record<string, unknown>)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`);
  return `{${entries.join(",")}}`;
}

export function canonical(tool: ToolLike): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of SIGNIFICANT_FIELDS) {
    out[field] = tool[field] ?? null;
  }
  return out;
}

export function digest(tool: ToolLike): string {
  return createHash("sha256").update(stableStringify(canonical(tool)), "utf8").digest("hex");
}

export function buildManifest(tools: ToolLike[]): Manifest {
  const perTool: Record<string, string> = {};
  for (const tool of tools) {
    if (tool.name in perTool) throw new Error(`duplicate tool name: ${tool.name}`);
    perTool[tool.name] = digest(tool);
  }

  const sorted = Object.fromEntries(Object.entries(perTool).sort(([a], [b]) => (a < b ? -1 : 1)));
  // One digest over the whole surface, so adding or removing a tool is a change
  // even though every surviving tool still matches.
  const surface = createHash("sha256").update(stableStringify(sorted), "utf8").digest("hex");

  return { lock_version: LOCK_VERSION, algorithm: ALGORITHM, tools: sorted, surface };
}

export function summarise(report: Report): string {
  if (report.ok) return "tool definitions match tools.lock.json";
  const parts: string[] = [];
  if (report.added.length) parts.push(`added: ${[...report.added].sort().join(", ")}`);
  if (report.removed.length) parts.push(`removed: ${[...report.removed].sort().join(", ")}`);
  if (report.changed.length) parts.push(`redefined: ${[...report.changed].sort().join(", ")}`);
  const detail = parts.join("; ");
  return report.reason && detail ? `${report.reason} — ${detail}` : report.reason || detail;
}

function fail(reason: string, extra: Partial<Report> = {}): Report {
  return { ok: false, reason, added: [], removed: [], changed: [], ...extra };
}

export function loadLock(path: string = LOCK_PATH): Manifest | null | undefined {
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    return null; // missing
  }
  try {
    return JSON.parse(raw) as Manifest;
  } catch {
    return undefined; // present but unreadable
  }
}

/**
 * Compare the live surface against the pinned one. A missing or unreadable lock
 * is a failure, not a pass: "we could not check" is the same answer as "it does
 * not match" everywhere else in this product.
 */
export function verify(tools: ToolLike[], lock: Manifest | null | undefined): Report {
  if (lock === null) return fail("tools.lock.json is missing");
  if (!lock || typeof lock !== "object" || !lock.tools) return fail("tools.lock.json is unreadable");
  if (lock.lock_version !== LOCK_VERSION) {
    return fail(`tools.lock.json is version ${lock.lock_version}, expected ${LOCK_VERSION}`);
  }
  if (lock.algorithm !== ALGORITHM) return fail(`unsupported digest algorithm ${lock.algorithm}`);

  const current = buildManifest(tools);
  const live = current.tools;
  const pinned = lock.tools;

  const added = Object.keys(live).filter((n) => !(n in pinned)).sort();
  const removed = Object.keys(pinned).filter((n) => !(n in live)).sort();
  const changed = Object.keys(live)
    .filter((n) => n in pinned && live[n] !== pinned[n])
    .sort();

  if (added.length || removed.length || changed.length) {
    return fail("the tool surface does not match the reviewed definitions", {
      added,
      removed,
      changed,
    });
  }

  // Belt and braces: matching tool by tool, this can only disagree if the lock's
  // own combined digest was edited by hand.
  if (lock.surface !== current.surface) {
    return fail("tools.lock.json surface digest does not match its own entries");
  }

  return { ok: true, reason: "", added: [], removed: [], changed: [] };
}

/**
 * Turn a verification result into a serve-or-refuse decision. Kept separate
 * from the SDK so the policy is testable without an MCP runtime.
 */
export function gate(report: Report, allowUnpinned = false): Decision {
  if (report.ok) return { serve: true, message: "" };

  if (allowUnpinned) {
    return {
      serve: true,
      message:
        `junoguard: WARNING — ${summarise(report)}. ` +
        `Serving anyway because ${UNPINNED_ENV} is set.`,
    };
  }

  return {
    serve: false,
    message:
      `junoguard: refusing to start — ${summarise(report)}.\n` +
      `  The tool descriptions an agent reads are instructions, so a change here ` +
      `is a change to agent behaviour.\n` +
      `  Review the diff. If it is intended, re-pin with: juno mcp --update-lock\n` +
      `  To serve unverified anyway (development only): ${UNPINNED_ENV}=1`,
  };
}

export function allowUnpinnedFromEnv(env: NodeJS.ProcessEnv = process.env): boolean {
  return ["1", "true", "yes"].includes((env[UNPINNED_ENV] ?? "").trim().toLowerCase());
}

export function writeLock(tools: ToolLike[], path: string = LOCK_PATH): Manifest {
  const manifest = buildManifest(tools);
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return manifest;
}
