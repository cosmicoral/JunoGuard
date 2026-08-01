/**
 * JunoGuard render layer — one visual language for every surface.
 *
 * Emits lines of styled spans rather than finished strings, so the MCP server
 * can flatten them to plain text and the CLI can paint them, without the two
 * drifting apart. Weight matches severity: an allow is one quiet line because
 * it happens constantly, a flag is a square-bordered caution, a block is a
 * rounded-border refusal with the blast radius under it.
 */

import type { BlastRadius, InstallResult, LlmResult, StatusResult, Verdict } from "./types.js";

export type Style = "" | "block" | "flag" | "allow" | "label" | "dim" | "key";
export type Span = [text: string, style: Style];
export type Line = Span[];

const BOX_W = 54; // inner width, between the border characters
const LABEL_W = 11; // "VERDICT    "
const SUB_W = 23; // "credentials in scope   "

// --------------------------------------------------------------------------
// primitives
// --------------------------------------------------------------------------

export function toPlain(lines: Line[]): string {
  return lines.map((line) => line.map(([text]) => text).join("")).join("\n");
}

const blank = (): Line => [];
const text = (value: string, style: Style = ""): Line => [[value, style]];
const pad = (value: string, width: number) => value.padEnd(width);

/**
 * The heavy header used by flag and block. Rounded corners read as more severe
 * than square ones, so block gets the rounded box and flag the square one.
 */
function banner(title: string, subject: string, style: Style, rounded: boolean): Line[] {
  const [tl, tr, bl, br] = rounded ? ["╭", "╮", "╰", "╯"] : ["┌", "┐", "└", "┘"];
  const cap = `─ ${title} `;
  const fill = "─".repeat(Math.max(0, BOX_W - cap.length));
  const trimmed = subject.slice(0, BOX_W - 4);
  return [
    [[`${tl}${cap}${fill}${tr}`, style]],
    [
      ["│", style],
      [pad(`  ${trimmed}`, BOX_W), ""],
      ["│", style],
    ],
    [[`${bl}${"─".repeat(BOX_W)}${br}`, style]],
  ];
}

const field = (label: string, value: string, style: Style = ""): Line => [
  [pad(label, LABEL_W), "label"],
  [value, style],
];

/** A continuation line under a field label. */
const cont = (value: string, style: Style = ""): Line => [
  [" ".repeat(LABEL_W), ""],
  [value, style],
];

const sub = (label: string, value: string, style: Style = ""): Line => [
  [" ".repeat(LABEL_W), ""],
  [pad(label, SUB_W), "dim"],
  [value, style],
];

/** Wrap a comma-separated list to `width`, keeping the commas trailing. */
function wrap(items: string[], width: number): string[] {
  const out: string[] = [];
  let current = "";
  items.forEach((item, index) => {
    const piece = item + (index < items.length - 1 ? "," : "");
    if (current && current.length + 1 + piece.length > width) {
      out.push(current);
      current = piece;
    } else {
      current = current ? `${current} ${piece}` : piece;
    }
  });
  if (current) out.push(current);
  return out.length ? out : [""];
}

/** Two decimals for round figures like a budget, four for fractional spend. */
function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const places = Number(value.toFixed(2)) === Number(value.toFixed(6)) ? 2 : 4;
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`;
}

const count = (value: number) => value.toLocaleString("en-US");

/** How the verdict was reached, phrased for a human. */
function sourceOf(verdict: Verdict | undefined): string {
  const source = verdict?.source ?? "unknown";
  const known: Record<string, string> = {
    ossprey: "via Ossprey",
    cache: "via Ossprey (cached)",
    mock: "via Ossprey (offline fixture)",
  };
  return known[source] ?? `via ${source}`;
}

function bar(fraction: number, width = 20): string {
  const clamped = Math.min(Math.max(fraction, 0), 1);
  const filled = Math.round(clamped * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

// --------------------------------------------------------------------------
// blast radius
// --------------------------------------------------------------------------

function blastRadius(blast: BlastRadius | null | undefined, preamble: string): Line[] {
  if (!blast) return [];
  const lines: Line[] = [
    blank(),
    [
      ["BLAST RADIUS  ", "label"],
      [preamble, "dim"],
    ],
  ];

  const creds = blast.credentials_in_scope ?? [];
  if (creds.length) {
    const wrapped = wrap(creds, BOX_W - SUB_W);
    lines.push(sub("credentials in scope", wrapped[0]!, "key"));
    for (const extra of wrapped.slice(1)) {
      lines.push([
        [" ".repeat(LABEL_W + SUB_W), ""],
        [extra, "key"],
      ]);
    }
  }

  if (blast.network_egress) lines.push(sub("network egress", String(blast.network_egress)));
  if (blast.write_access) lines.push(sub("write access", String(blast.write_access)));

  if (blast.summary) {
    lines.push(blank());
    lines.push(cont(`→ ${blast.summary}`, "block"));
  }
  return lines;
}

// --------------------------------------------------------------------------
// Lane A — package installs
// --------------------------------------------------------------------------

export function renderInstall(payload: InstallResult, pkg: string, ecosystem: string): Line[] {
  const decision = payload.decision ?? "flag";
  const verdict = payload.verdict ?? {};
  const findings = verdict.findings ?? [];
  const severity = verdict.severity ?? payload.risk_level ?? "unknown";

  if (decision === "allow") {
    // Allows happen constantly. One quiet line, nothing more.
    const detail = severity === "unknown" ? "no findings" : severity;
    return [
      [
        ["✓ juno ", "allow"],
        [`· allow — ${pkg} (${ecosystem}) · ${detail}`, "dim"],
      ],
    ];
  }

  const blocked = decision === "block";
  const style: Style = blocked ? "block" : "flag";
  // "We could not look" is a different message from "we found something": the
  // agent has to be told to retry, not to go and pick another dependency.
  const unscanned = payload.review_required === true || verdict.available === false;
  const title = blocked
    ? unscanned
      ? "JUNO · NOT SCANNED"
      : "JUNO · BLOCKED"
    : "JUNO · FLAGGED";

  const lines = banner(title, `${pkg}  (${ecosystem})`, style, blocked);
  lines.push(blank());
  lines.push(field("VERDICT", `${severity}  ·  ${sourceOf(verdict)}`, style));
  for (const finding of findings) lines.push(cont(String(finding)));
  if (!findings.length && payload.reason) lines.push(cont(String(payload.reason)));

  lines.push(
    ...blastRadius(
      payload.blast_radius,
      blocked ? "if this had installed" : "if this turns out to be hostile",
    ),
  );

  lines.push(blank());
  if (blocked && unscanned) {
    const retry = payload.retry_after_seconds;
    lines.push(text("This package was not installed, and it was never scanned.", style));
    lines.push(
      text(
        retry
          ? `The scanner is unavailable — retry in ${retry}s, or get an operator review.`
          : "The scanner is unavailable — retry later, or get an operator review.",
        style,
      ),
    );
    lines.push(text("This is not a finding against the package.", "dim"));
  } else if (blocked) {
    // The agent reads this. It has to be unambiguous enough that it picks a
    // different dependency instead of retrying the same one.
    lines.push(text("This package was not installed. Choose a different dependency.", style));
  } else {
    lines.push(text("Not blocked, but unverified. Prefer a dependency with a known", "flag"));
    lines.push(text("publisher if one exists; if you proceed, say why.", "flag"));
  }
  return lines;
}

// --------------------------------------------------------------------------
// Lane B — model calls
// --------------------------------------------------------------------------

function budgetLines(payload: LlmResult): Line[] {
  const spend = payload.spend_today_usd;
  const budget = payload.daily_budget_usd;
  if (spend === undefined || !budget) return [];
  return [
    sub("spend today", `${money(spend)} of ${money(budget)}`),
    sub("remaining", money(Math.max(0, budget - spend))),
  ];
}

export function renderLlm(payload: LlmResult, model: string): Line[] {
  const decision = payload.decision ?? "flag";
  const spend = payload.spend_today_usd;
  const budget = payload.daily_budget_usd;

  if (decision === "allow") {
    const bits = [`· allow — ${model}`];
    if (payload.tokens_in !== undefined) {
      bits.push(`${count(payload.tokens_in)} in / ${count(payload.tokens_out ?? 0)} out`);
    }
    if (payload.cost_usd !== undefined) bits.push(`$${payload.cost_usd.toFixed(6)}`);
    if (spend !== undefined && budget) bits.push(`${money(spend)} of ${money(budget)} today`);

    const lines: Line[] = [
      [
        ["✓ juno ", "allow"],
        [bits.join("  ·  "), "dim"],
      ],
    ];
    if (payload.answer) lines.push(blank(), text(String(payload.answer)));
    return lines;
  }

  const blocked = decision === "block";
  const style: Style = blocked ? "block" : "flag";
  const title = blocked ? "JUNO · BLOCKED" : "JUNO · FLAGGED";

  const lines = banner(title, `model call  ·  ${model}`, style, blocked);
  lines.push(blank());
  lines.push(field("REASON", String(payload.reason ?? "policy"), style));
  lines.push(cont(`risk: ${payload.risk_level ?? "unknown"}`, "dim"));

  const budgets = budgetLines(payload);
  if (budgets.length) {
    lines.push(blank(), [["BUDGET", "label"]], ...budgets);
  }

  lines.push(blank());
  if (blocked) {
    lines.push(text("No model call was made and nothing was charged.", style));
    lines.push(text("Do not retry this call. Ask the operator to raise the budget,", style));
    lines.push(text("reduce the request, or stop here.", style));
  } else {
    lines.push(text("Allowed, but this call is outside the normal pattern for this", "flag"));
    lines.push(text("project. Keep the next few calls small.", "flag"));
    if (payload.answer) lines.push(blank(), text(String(payload.answer)));
  }
  return lines;
}

// --------------------------------------------------------------------------
// status
// --------------------------------------------------------------------------

export function renderStatus(payload: StatusResult): Line[] {
  const project = payload.project ?? "project";
  const state = payload.status ?? "unknown";
  const suspended = state !== "active";

  const spend = payload.spend_today_usd ?? 0;
  const budget = payload.daily_budget_usd ?? 0;
  const remaining = payload.remaining_usd ?? Math.max(0, budget - spend);
  const used = budget ? spend / budget : 0;

  const style: Style = suspended ? "block" : "allow";
  const title = suspended ? "JUNO · SUSPENDED" : "JUNO · status";
  const lines = banner(title, `${project}  ·  ${state}`, style, suspended);

  lines.push(blank());
  lines.push(field("BUDGET", `${money(spend)} spent of ${money(budget)}`));
  const usedStyle: Style = used >= 0.9 ? "block" : used >= 0.7 ? "flag" : "allow";
  lines.push([
    [" ".repeat(LABEL_W), ""],
    [bar(used), usedStyle],
    [`  ${Math.round(used * 100)}%`, "dim"],
  ]);
  lines.push(cont(`${money(remaining)} remaining`, "dim"));

  const rpm = payload.requests_last_min;
  const cap = payload.max_requests_per_min;
  if (rpm !== undefined) {
    const over = cap !== undefined && rpm > cap;
    lines.push(blank());
    lines.push(
      field(
        "RATE",
        `${rpm} request${rpm === 1 ? "" : "s"} in the last minute` +
          (cap ? `  (limit ${cap}/min)` : ""),
        over ? "block" : "",
      ),
    );
    if (over) lines.push(cont("burst above policy — requests are being rejected", "block"));
  }

  const blocked = payload.blocked_today;
  const incidents = payload.open_incidents;
  if (blocked !== undefined || incidents !== undefined) {
    const parts: string[] = [];
    if (blocked !== undefined) parts.push(`${blocked} blocked`);
    if (incidents !== undefined) {
      parts.push(`${incidents} open incident${incidents === 1 ? "" : "s"}`);
    }
    lines.push(blank());
    const hot = Boolean(blocked) || Boolean(incidents);
    lines.push(field("TODAY", parts.join("  ·  "), hot ? "flag" : "dim"));
  }

  if (suspended) {
    lines.push(blank());
    lines.push(text("This project is suspended. Both lanes are dark — every install", "block"));
    lines.push(text("and model call will be blocked until an operator resumes it.", "block"));
  }
  return lines;
}

// --------------------------------------------------------------------------
// failure states
// --------------------------------------------------------------------------

/**
 * Rendered when the guard itself could not be consulted. Deliberately shaped
 * like a block: an unreachable guard means the action was not approved, and
 * nothing downstream should read it as permission.
 */
export function renderError(subject: string, detail: string, consequence: string): Line[] {
  const lines = banner("JUNO · UNAVAILABLE", subject, "block", true);
  lines.push(blank());
  lines.push(field("REASON", detail, "block"));
  lines.push(blank());
  lines.push(text(consequence, "block"));
  return lines;
}

/**
 * Shown when no project key is set. Also a refusal — nothing was checked, so
 * nothing is approved — but it fails toward teaching rather than alarm, since
 * the cause is setup rather than an attack.
 */
export function renderNotConfigured(subject: string, apiUrl: string): Line[] {
  const lines = banner("JUNO · NOT CONFIGURED", subject, "flag", false);
  lines.push(blank());
  lines.push(field("MISSING", "JUNO_PROJECT_KEY", "flag"));
  lines.push(cont("Nothing was checked, so nothing is approved.", "dim"));
  lines.push(blank());
  lines.push([["TRY IT", "label"]]);
  lines.push(sub("offline, no gateway", "JUNO_MOCK=1", "key"));
  lines.push(blank());
  lines.push([["CONNECT", "label"]]);
  lines.push(sub("your gateway", `JUNO_API_URL=${apiUrl}`, "key"));
  lines.push(sub("your project key", "JUNO_PROJECT_KEY=…", "key"));
  lines.push(blank());
  lines.push(cont("JunoGuard ships no default key on purpose — a shipped", "dim"));
  lines.push(cont("credential would point you at someone else's gateway.", "dim"));
  return lines;
}
