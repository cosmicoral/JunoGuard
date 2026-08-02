export type Decision = "allow" | "flag" | "block";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ActionType = "llm_call" | "package_install" | "status_check";
export type ProjectStatus = "active" | "suspended";

export interface BlastRadius {
  credentials: string[];
  network_egress: string;
  write_access: string;
  summary: string;
  scope_source?: string;
  scope_is_attested?: boolean;
}

export interface CycloneDxSbom {
  bomFormat: "CycloneDX";
  specVersion: string;
  serialNumber?: string;
  metadata?: {
    component?: {
      name?: string;
      version?: string;
      purl?: string;
    };
  };
}

export interface SandboxEvidence {
  status: "completed" | "timed_out" | "artifact_rejected";
  engine?: "docker";
  artifact_kind?: "npm-tarball" | "pypi-sdist" | "pypi-wheel";
  scripts_executed?: Array<{
    lifecycle: string;
    exit_code?: number | null;
    timed_out?: boolean;
  }>;
  files_created?: string[];
  observations?: string[];
}

export interface ActionMetadata {
  blast_radius?: BlastRadius;
  ossprey?: { verdict: string; severity: string };
  sbom?: CycloneDxSbom | null;
  sandbox?: SandboxEvidence | null;
  [key: string]: unknown;
}

export interface AgentAction {
  id: string;
  project_id: string;
  action_type: ActionType;
  target: string;
  decision: Decision;
  reason: string;
  risk_level: RiskLevel;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  metadata: ActionMetadata;
  created_at: string;
}

export interface Incident {
  id: string;
  project_id: string;
  action_id: string | null;
  severity: RiskLevel;
  title: string;
  evidence: Record<string, unknown>;
  status: "open" | "resolved";
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
}

export interface Policy {
  project_id: string;
  daily_budget_usd: number;
  per_request_budget_usd: number;
  max_request_tokens: number;
  max_requests_per_min: number;
}
