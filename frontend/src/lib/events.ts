import type { ActionMetadata, AgentAction, BlastRadius, Incident, ProjectStatus } from "./types";

/** Backend blast_radius uses credentials_in_scope; the UI uses credentials. */
export function normalizeBlast(raw: unknown): BlastRadius | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const r = raw as Record<string, unknown>;
  const raw_creds = (r.credentials_in_scope ?? r.credentials) as string[] | undefined;
  const credentials = Array.isArray(raw_creds) ? raw_creds : [];
  const network_egress = String(r.network_egress ?? "");
  const write_access = String(r.write_access ?? "");
  const summary = String(r.summary ?? "");
  const scope_source = typeof r.scope_source === "string" ? r.scope_source : undefined;
  const scope_is_attested =
    typeof r.scope_is_attested === "boolean" ? r.scope_is_attested : undefined;

  // An empty credential list is a real answer, not a missing payload — the
  // scanned environment simply had no keys. Egress and write access still
  // matter, so keep the panel as long as anything is populated. Dropping it
  // here is how a blocked install renders with no explanation at all.
  if (!credentials.length && !network_egress && !write_access && !summary) return undefined;

  return {
    credentials,
    network_egress,
    write_access,
    summary,
    scope_source,
    scope_is_attested,
  };
}

function normalizeMetadata(raw: unknown): ActionMetadata {
  if (!raw || typeof raw !== "object") return {};
  const meta = { ...(raw as ActionMetadata) };
  if (meta.blast_radius) {
    const blast = normalizeBlast(meta.blast_radius);
    if (blast) meta.blast_radius = blast;
    else delete meta.blast_radius;
  }
  // Gateway nests Ossprey under `verdict`; the feed reads `ossprey`.
  const verdict = (meta as { verdict?: { severity?: string; source?: string } }).verdict;
  if (verdict && !meta.ossprey) {
    meta.ossprey = {
      verdict: String(verdict.severity ?? "unknown"),
      severity: String(verdict.severity ?? "unknown"),
    };
  }
  return meta;
}

/** Map a gateway action event payload onto the dashboard's AgentAction shape. */
export function actionFromEvent(data: Record<string, unknown>, projectId: string): AgentAction {
  return {
    id: String(data.id ?? crypto.randomUUID()),
    project_id: String(data.project_id ?? projectId),
    action_type: (data.action_type as AgentAction["action_type"]) ?? "llm_call",
    target: String(data.target ?? ""),
    decision: (data.decision as AgentAction["decision"]) ?? "allow",
    reason: String(data.reason ?? ""),
    risk_level: (data.risk_level as AgentAction["risk_level"]) ?? "low",
    tokens_in: (data.tokens_in as number | null) ?? null,
    tokens_out: (data.tokens_out as number | null) ?? null,
    cost_usd: (data.cost_usd as number | null) ?? null,
    metadata: normalizeMetadata(data.metadata),
    created_at: String(data.created_at ?? new Date().toISOString()),
  };
}

/** Map a gateway incident event onto Incident, filling fields the stream omits. */
export function incidentFromEvent(
  data: Record<string, unknown>,
  projectId: string,
): Incident {
  const actionId = data.action_id != null ? String(data.action_id) : null;
  return {
    id: String(data.id ?? `inc-${actionId ?? crypto.randomUUID()}`),
    project_id: String(data.project_id ?? projectId),
    action_id: actionId,
    severity: (data.severity as Incident["severity"]) ?? "high",
    title: String(data.title ?? "Incident"),
    evidence: (data.evidence as Record<string, unknown>) ?? {},
    status: (data.status as Incident["status"]) ?? "open",
    created_at: String(data.created_at ?? new Date().toISOString()),
  };
}

export interface ProjectEvent {
  status: ProjectStatus;
  reason: string | null;
}

export function projectFromEvent(data: Record<string, unknown>): ProjectEvent {
  return {
    status: data.status === "suspended" ? "suspended" : "active",
    reason: data.reason != null ? String(data.reason) : null,
  };
}
