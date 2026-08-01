import type { AgentAction, Incident, Policy, Project } from "./types";

/**
 * Mock mode. Emits plausible traffic on a timer so the dashboard runs with no
 * backend at all. Rates here are tuned against the demo policy below: baseline
 * sits comfortably under the rate limit so a burst is unmistakable.
 */

export const MOCK_PROJECT: Project = {
  id: "demo-project",
  name: "Demo Project",
  status: "active",
};

export const MOCK_POLICY: Policy = {
  project_id: "demo-project",
  daily_budget_usd: 1.0,
  per_request_budget_usd: 0.05,
  max_request_tokens: 4000,
  max_requests_per_min: 30,
};

/** Actions Juno has already cleared today, before the feed window starts. */
export const ACTIONS_EARLIER_TODAY = 1247;

/** Spend Juno recorded earlier today, before the feed window starts. */
export const SPEND_EARLIER_TODAY = 0.34;

/**
 * Weighted so the average request costs a fraction of a cent. A real agent
 * loop is mostly small cheap calls; if the mix were opus-heavy the demo would
 * burn the daily cap before the three minutes were up.
 */
const MODELS = [
  ...Array<string>(9).fill("gpt-4o-mini"),
  ...Array<string>(5).fill("gpt-4o"),
  ...Array<string>(4).fill("claude-sonnet-5"),
];

const CLEAN_PACKAGES = [
  "react@18.3.1",
  "zod@3.23.8",
  "axios@1.7.2",
  "vite@5.4.10",
  "drizzle-orm@0.31.2",
  "tailwindcss@3.4.4",
  "pino@9.2.0",
  "@types/node@20.14.2",
  "express@4.19.2",
  "date-fns@3.6.0",
];

let seq = 0;
const id = () => `mock-${Date.now().toString(36)}-${(seq++).toString(36)}`;

const pick = <T,>(xs: T[]): T => xs[Math.floor(Math.random() * xs.length)];
const between = (a: number, b: number) => a + Math.random() * (b - a);

function llmCost(model: string, tokensIn: number, tokensOut: number): number {
  // Local pricing table, same shape the gateway uses. Per 1M tokens.
  const table: Record<string, [number, number]> = {
    "gpt-4o": [2.5, 10],
    "gpt-4o-mini": [0.15, 0.6],
    "claude-sonnet-5": [3, 15],
    "claude-opus-5": [15, 75],
    "text-embedding-3-small": [0.02, 0],
  };
  const [inRate, outRate] = table[model] ?? [2.5, 10];
  return (tokensIn * inRate + tokensOut * outRate) / 1_000_000;
}

function llmAction(at: number, overrides: Partial<AgentAction> = {}): AgentAction {
  const model = pick(MODELS);
  const tokensIn = Math.round(between(180, 2200));
  const tokensOut = Math.round(between(60, 520));
  return {
    id: id(),
    project_id: MOCK_PROJECT.id,
    action_type: "llm_call",
    target: model,
    decision: "allow",
    reason: "Within per-request and daily budget.",
    risk_level: "low",
    tokens_in: tokensIn,
    tokens_out: tokensOut,
    cost_usd: llmCost(model, tokensIn, tokensOut),
    metadata: {},
    created_at: new Date(at).toISOString(),
    ...overrides,
  };
}

function pkgAction(at: number, overrides: Partial<AgentAction> = {}): AgentAction {
  return {
    id: id(),
    project_id: MOCK_PROJECT.id,
    action_type: "package_install",
    target: pick(CLEAN_PACKAGES),
    decision: "allow",
    reason: "Ossprey verdict: clean. No install scripts.",
    risk_level: "low",
    tokens_in: null,
    tokens_out: null,
    cost_usd: null,
    metadata: { ossprey: { verdict: "clean", severity: "none" } },
    created_at: new Date(at).toISOString(),
    ...overrides,
  };
}

/** The Lane A set piece. Blocked, with the blast radius Juno computed. */
export function maliciousPackage(at = Date.now()): AgentAction {
  return pkgAction(at, {
    target: "@ossprey/test-package",
    decision: "block",
    reason: "Ossprey verdict: malicious. Postinstall script exfiltrates environment.",
    risk_level: "critical",
    metadata: {
      ossprey: { verdict: "malicious", severity: "critical" },
      blast_radius: {
        credentials: ["OPENAI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "AWS_PROFILE=prod"],
        network_egress: "unrestricted",
        write_access: "full repository, incl. .github/workflows",
        summary: "full production credential compromise",
      },
    },
  });
}

export function maliciousIncident(action: AgentAction): Incident {
  return {
    id: id(),
    project_id: MOCK_PROJECT.id,
    action_id: action.id,
    severity: "critical",
    title: `Malicious package blocked pre-install — ${action.target}`,
    evidence: action.metadata,
    status: "open",
    created_at: action.created_at,
  };
}

function flaggedPackage(at: number): AgentAction {
  return pkgAction(at, {
    target: "fast-json-parse@1.0.1",
    decision: "flag",
    reason: "Ossprey verdict: unknown. Publisher unverified, package 4 days old.",
    risk_level: "medium",
    metadata: { ossprey: { verdict: "unknown", severity: "low" } },
  });
}

/**
 * Seeds the feed so it never opens empty. Dense enough that the rolling
 * req/min figure is real from the first frame.
 */
export function seedActions(now = Date.now()): AgentAction[] {
  const out: AgentAction[] = [];
  // Long enough that the req/min sparkline is full from the very first frame.
  let at = now - 130_000;

  while (at < now - 1500) {
    at += between(1600, 3400);
    out.push(Math.random() < 0.22 ? pkgAction(at) : llmAction(at));
  }

  // A couple of non-allow rows in the history, so allow/flag/block are all
  // legible before anything live arrives.
  const flagIdx = Math.floor(out.length * 0.35);
  out[flagIdx] = flaggedPackage(Date.parse(out[flagIdx].created_at));

  const budgetIdx = Math.floor(out.length * 0.62);
  out[budgetIdx] = llmAction(Date.parse(out[budgetIdx].created_at), {
    target: "claude-opus-5",
    decision: "flag",
    reason: "Request cost $0.0612 exceeds per-request cap $0.0500. Downgraded.",
    risk_level: "medium",
  });

  const blockIdx = Math.floor(out.length * 0.78);
  out[blockIdx] = maliciousPackage(Date.parse(out[blockIdx].created_at));

  return out.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
}

export function seedIncidents(actions: AgentAction[]): Incident[] {
  return actions.filter((a) => a.decision === "block").map(maliciousIncident);
}

/** What Juno records once the kill switch is down: everything, refused. */
export function suspendedAction(at = Date.now()): AgentAction {
  const base = Math.random() < 0.3 ? pkgAction(at) : llmAction(at);
  return {
    ...base,
    decision: "block",
    reason: "Project suspended. All lanes closed pending manual reset.",
    risk_level: "high",
    cost_usd: null,
    metadata: {},
  };
}

/**
 * A hijacked agent hammering the model endpoint. Lane B's whole argument.
 * Spread over the last few seconds so the sparkline shows a spike with width
 * rather than a single spike-shaped artefact.
 */
export function burstActions(now = Date.now()): AgentAction[] {
  const out: AgentAction[] = [];
  const n = 16;
  for (let i = 0; i < n; i++) {
    const at = now - Math.round((n - i) * between(480, 700));
    const over = i >= 10;
    const tokensIn = Math.round(between(2400, 3600));
    const tokensOut = Math.round(between(500, 900));
    out.push(
      llmAction(at, {
        target: "gpt-4o",
        decision: over ? "block" : "flag",
        reason: over
          ? `Rate limit exceeded — ${52 + i * 4}/min against cap of ${MOCK_POLICY.max_requests_per_min}/min.`
          : "Burst detected: request rate climbing 6x above baseline.",
        risk_level: over ? "critical" : "high",
        tokens_in: tokensIn,
        tokens_out: over ? null : tokensOut,
        cost_usd: over ? null : llmCost("gpt-4o", tokensIn, tokensOut),
      }),
    );
  }
  return out;
}

export function nextAction(now = Date.now()): AgentAction {
  const roll = Math.random();
  if (roll < 0.16) return pkgAction(now);
  if (roll < 0.2) return flaggedPackage(now);
  return llmAction(now);
}

/** Interval between emitted actions — averages just under the 30/min cap. */
export function nextDelay(): number {
  return between(1600, 3200);
}
