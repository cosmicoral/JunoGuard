/**
 * The live decision feed behind `juno watch`.
 *
 * Live mode derives events from `GET /v1/guard/status`, which is the only
 * polling surface the frozen contract gives us: a rise in `blocked_today` is a
 * block, a rise in `open_incidents` is an incident, a rise in
 * `spend_today_usd` is billable traffic. Offline mode replays a scripted run
 * so the feed still moves with no gateway.
 */

import type { Line, Style } from "./render.js";
import type { StatusResult } from "./types.js";

const LANE_W = 10;
const DECISION_W = 7;

export interface Event {
  decision: "allow" | "flag" | "block" | "incident";
  lane: string;
  detail: string;
}

const STYLES: Record<Event["decision"], [Style, string]> = {
  allow: ["allow", "allow"],
  flag: ["flag", "FLAG"],
  block: ["block", "BLOCK"],
  incident: ["block", "!"],
};

export function renderEvent(event: Event, clock: string): Line {
  const [style, label] = STYLES[event.decision] ?? (["dim", event.decision] as [Style, string]);
  const detailStyle: Style = event.decision === "allow" ? "dim" : style;
  return [
    [`${clock}  `, "dim"],
    [label.padEnd(DECISION_W), style],
    [event.lane.padEnd(LANE_W), "key"],
    [event.detail, detailStyle],
  ];
}

export function clockNow(): string {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

// --------------------------------------------------------------------------
// live mode — status deltas
// --------------------------------------------------------------------------

export function diffStatus(previous: StatusResult, current: StatusResult): Event[] {
  const events: Event[] = [];

  if (previous.status !== current.status) {
    events.push({
      decision: current.status === "active" ? "allow" : "incident",
      lane: "project",
      detail: `project is now ${current.status}`,
    });
  }

  const blockedDelta = (current.blocked_today ?? 0) - (previous.blocked_today ?? 0);
  for (let i = 0; i < blockedDelta; i += 1) {
    events.push({ decision: "block", lane: "guard", detail: "an action was blocked by policy" });
  }

  const incidentDelta = (current.open_incidents ?? 0) - (previous.open_incidents ?? 0);
  for (let i = 0; i < incidentDelta; i += 1) {
    events.push({ decision: "incident", lane: "incident", detail: "new incident opened" });
  }

  const spendDelta = (current.spend_today_usd ?? 0) - (previous.spend_today_usd ?? 0);
  if (spendDelta > 0) {
    const budget = current.daily_budget_usd ?? 0;
    const remaining = current.remaining_usd ?? Math.max(0, budget - (current.spend_today_usd ?? 0));
    events.push({
      decision: "allow",
      lane: "llm",
      detail: `+$${spendDelta.toFixed(6)}  ·  $${remaining.toFixed(4)} left today`,
    });
  }

  const rpm = current.requests_last_min;
  const cap = current.max_requests_per_min;
  const wasOver =
    previous.requests_last_min !== undefined &&
    previous.max_requests_per_min !== undefined &&
    previous.requests_last_min > previous.max_requests_per_min;
  if (rpm !== undefined && cap && rpm > cap && !wasOver) {
    events.push({
      decision: "flag",
      lane: "burst",
      detail: `${rpm} req/min against a ${cap}/min limit`,
    });
  }

  return events;
}

// --------------------------------------------------------------------------
// offline mode — scripted run
// --------------------------------------------------------------------------

export const SCRIPT: Event[] = [
  { decision: "allow", lane: "install", detail: "express (npm) · clean" },
  { decision: "allow", lane: "llm", detail: "gpt-4o · 1,204 in / 287 out · $0.000431" },
  { decision: "allow", lane: "install", detail: "zod (npm) · clean" },
  {
    decision: "flag",
    lane: "install",
    detail: "@ossprey/suspicious-package (npm) · no published provenance",
  },
  { decision: "allow", lane: "llm", detail: "gpt-4o · 842 in / 190 out · $0.000312" },
  {
    decision: "block",
    lane: "install",
    detail: "@ossprey/test-package (npm) · malicious: obfuscated postinstall",
  },
  {
    decision: "incident",
    lane: "incident",
    detail: "critical · attempted credential exfiltration on install",
  },
  { decision: "allow", lane: "llm", detail: "gpt-4o · 611 in / 140 out · $0.000253" },
  { decision: "flag", lane: "burst", detail: "63 req/min against a 60/min limit" },
];
