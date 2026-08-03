/**
 * HTTP client for the JunoGuard gateway, plus the offline fixture mode.
 *
 * Two rules shape this file:
 *
 * 1. A block is data, not an error. `decision: "block"` arrives on HTTP 200
 *    and is returned like any other envelope. Nothing here throws on it.
 * 2. When the guard cannot be reached, we fail closed. `JunoUnavailable` is
 *    thrown so callers refuse the action rather than quietly proceeding.
 */

import { randomUUID } from "node:crypto";
import { collectAgentScope } from "./scope.js";
import type { Ecosystem, Envelope, InstallResult, LlmResult, StatusResult } from "./types.js";

export const DEFAULT_API_URL = "http://localhost:8000";

// Must outlive the gateway's own scan budget (OSSPREY_SCAN_BUDGET_SECONDS, 90s).
// The gateway already bounds how long a verdict may take and refuses as
// unscanned past that; a client that gives up first turns a verdict that was
// coming into a fail-closed refusal, so a clean package is rejected on nothing
// but a stopwatch. Measured against the live pair, a cold scan of a popular
// package runs 19-35s and only the first request for a version pays it.
const DEFAULT_TIMEOUT_MS = 100_000;

const TRUTHY = new Set(["1", "true", "yes", "on"]);

export class JunoUnavailable extends Error {
  readonly detail: string;
  readonly status?: number;

  constructor(detail: string, status?: number) {
    super(detail);
    this.name = "JunoUnavailable";
    this.detail = detail;
    this.status = status;
  }
}

/**
 * No project key. Deliberately distinct from JunoUnavailable: "you have not
 * set this up" and "the gateway is down" need different advice, even though
 * both mean the action was not approved.
 *
 * There is no default key. Shipping one in a public package would point every
 * install at someone else's gateway with a credential they did not choose.
 */
export class JunoNotConfigured extends Error {
  constructor(readonly detail = "no project key configured") {
    super(detail);
    this.name = "JunoNotConfigured";
  }
}

export function mockEnabled(): boolean {
  return TRUTHY.has((process.env.JUNO_MOCK ?? "").trim().toLowerCase());
}

export interface ClientOptions {
  apiUrl?: string;
  projectKey?: string;
  mock?: boolean;
  timeoutMs?: number;
}

export class JunoClient {
  readonly apiUrl: string;
  readonly projectKey: string | undefined;
  readonly mock: boolean;
  private readonly timeoutMs: number;

  constructor(options: ClientOptions = {}) {
    this.apiUrl = (options.apiUrl ?? process.env.JUNO_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");
    this.projectKey = options.projectKey ?? process.env.JUNO_PROJECT_KEY ?? undefined;
    this.mock = options.mock ?? mockEnabled();
    const fromEnv = Number(process.env.JUNO_TIMEOUT);
    this.timeoutMs = options.timeoutMs ?? (fromEnv > 0 ? fromEnv * 1000 : DEFAULT_TIMEOUT_MS);
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    // Checked here rather than in the constructor so that commands which never
    // reach the network — `init`, `--help` — work without any configuration.
    if (!this.projectKey) throw new JunoNotConfigured();

    const url = `${this.apiUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers: {
          "X-Juno-Key": this.projectKey,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new JunoUnavailable(`gateway at ${this.apiUrl} timed out`);
      }
      throw new JunoUnavailable(`no gateway listening at ${this.apiUrl}`);
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) throw new JunoUnavailable(await errorDetail(response), response.status);

    try {
      return (await response.json()) as T;
    } catch {
      throw new JunoUnavailable("gateway returned a non-JSON response");
    }
  }

  guardInstall(pkg: string, ecosystem: Ecosystem = "npm", version?: string): Promise<InstallResult> {
    if (this.mock) return Promise.resolve(mockInstall(pkg));
    return this.request<InstallResult>("POST", "/v1/guard/install", {
      package: pkg,
      ecosystem,
      version: version ?? null,
      agent_scope: collectAgentScope(),
    });
  }

  guardLlm(prompt: string, model = "gpt-4o", maxOutputTokens = 300): Promise<LlmResult> {
    if (this.mock) return Promise.resolve(mockLlm(prompt, maxOutputTokens));
    return this.request<LlmResult>("POST", "/v1/guard/llm", {
      prompt,
      model,
      max_output_tokens: maxOutputTokens,
    });
  }

  /**
   * Record an operator's override for an install that cannot be scanned.
   *
   * Callers must treat a rejection here as a refusal to install. An override
   * nobody can find in the audit trail later is indistinguishable from having no
   * policy at all.
   */
  reportUnscanned(input: {
    sources: string[];
    ecosystem: Ecosystem;
    manager: string;
    reason: string;
    operator: string;
  }): Promise<Envelope> {
    if (this.mock) {
      return Promise.resolve({
        decision: "flag",
        reason: `[offline fixture] override by ${input.operator} was NOT recorded anywhere.`,
        risk_level: "high",
      });
    }
    return this.request<Envelope>("POST", "/v1/guard/unscanned", input);
  }

  status(): Promise<StatusResult> {
    if (this.mock) return Promise.resolve(mockStatus());
    return this.request<StatusResult>("GET", "/v1/guard/status");
  }

  health(): Promise<unknown> {
    if (this.mock) {
      return Promise.resolve({ status: "ok", service: "JunoGuard", mode: "offline-fixture" });
    }
    return this.request("GET", "/health");
  }
}

/** Turn the contract's error shape into one readable line. */
async function errorDetail(response: Response): Promise<string> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const kind = record.error;
    const detail = record.detail ?? record.message;
    if (kind && detail) return `${response.status} ${kind} — ${detail}`;
    if (kind || detail) return `${response.status} ${kind ?? detail}`;
  }
  return `HTTP ${response.status} from the gateway`;
}

// --------------------------------------------------------------------------
// Offline fixtures — JUNO_MOCK=1
//
// No network at all. The demo's insurance policy: if the gateway is down, or
// not yet running, every client still behaves exactly as it would live.
// --------------------------------------------------------------------------

export const MOCK_BLOCK_PACKAGES = new Set(["@ossprey/test-package"]);
export const MOCK_FLAG_PACKAGES = new Set(["@ossprey/suspicious-package"]);

const MOCK_SPEND_TODAY = 0.4231;
const MOCK_DAILY_BUDGET = 1.0;
export const MOCK_MAX_OUTPUT_TOKENS = 2000;
const MOCK_LARGE_PROMPT_TOKENS = 20_000;

const MOCK_BLAST_RADIUS = {
  credentials_in_scope: ["OPENAI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "AWS_PROFILE=prod"],
  network_egress: "unrestricted",
  write_access: "open repository",
  summary: "full production credential compromise",
};

export function mockInstall(pkg: string): InstallResult {
  const name = pkg.trim();

  if (MOCK_BLOCK_PACKAGES.has(name)) {
    return {
      action_id: randomUUID(),
      decision: "block",
      reason: "Ossprey verdict: malicious. The package was not installed.",
      risk_level: "critical",
      project_status: "active",
      verdict: {
        source: "mock",
        severity: "malicious",
        findings: [
          "Obfuscated postinstall script",
          "Outbound POST on install",
          "Reads process environment at install time",
        ],
      },
      blast_radius: { ...MOCK_BLAST_RADIUS },
    };
  }

  if (MOCK_FLAG_PACKAGES.has(name)) {
    return {
      action_id: randomUUID(),
      decision: "flag",
      reason: "No published provenance and a very recent first release.",
      risk_level: "medium",
      project_status: "active",
      verdict: {
        source: "mock",
        severity: "unknown",
        findings: [
          "No published provenance",
          "First release 3 days ago",
          "Name is one character from a popular package",
        ],
      },
      blast_radius: { ...MOCK_BLAST_RADIUS },
    };
  }

  return {
    action_id: randomUUID(),
    decision: "allow",
    reason: "No malicious indicators found.",
    risk_level: "low",
    project_status: "active",
    verdict: { source: "mock", severity: "clean", findings: [] },
    blast_radius: null,
  };
}

export function mockLlm(prompt: string, maxOutputTokens = 300): LlmResult {
  const tokensIn = Math.max(1, Math.floor(prompt.length / 4));
  const tokensOut = Math.min(maxOutputTokens, 120);
  const cost = Number((tokensIn * 2.5e-6 + tokensOut * 1.0e-5).toFixed(6));

  if (maxOutputTokens > MOCK_MAX_OUTPUT_TOKENS) {
    return {
      action_id: randomUUID(),
      decision: "block",
      reason: `Request exceeds the per-request token cap (${MOCK_MAX_OUTPUT_TOKENS}).`,
      risk_level: "medium",
      project_status: "active",
      answer: null,
      tokens_in: tokensIn,
      tokens_out: 0,
      cost_usd: 0,
      spend_today_usd: MOCK_SPEND_TODAY,
      daily_budget_usd: MOCK_DAILY_BUDGET,
    };
  }

  const large = tokensIn > MOCK_LARGE_PROMPT_TOKENS;
  return {
    action_id: randomUUID(),
    decision: large ? "flag" : "allow",
    reason: large
      ? "Prompt is far larger than this project's baseline."
      : "Request is within configured limits.",
    risk_level: large ? "medium" : "low",
    project_status: "active",
    answer:
      "[JunoGuard offline fixture] No model was called. Unset JUNO_MOCK and " +
      "point JUNO_API_URL at a running gateway for real completions.",
    tokens_in: tokensIn,
    tokens_out: tokensOut,
    cost_usd: cost,
    spend_today_usd: Number((MOCK_SPEND_TODAY + cost).toFixed(6)),
    daily_budget_usd: MOCK_DAILY_BUDGET,
  };
}

export function mockStatus(): StatusResult {
  return {
    project: "Demo Project",
    status: "active",
    spend_today_usd: MOCK_SPEND_TODAY,
    daily_budget_usd: MOCK_DAILY_BUDGET,
    remaining_usd: Number((MOCK_DAILY_BUDGET - MOCK_SPEND_TODAY).toFixed(4)),
    requests_last_min: 6,
    max_requests_per_min: 60,
    blocked_today: 1,
    open_incidents: 1,
  };
}
