/** Shapes from docs/api-contract.md. The contract is authoritative. */

export type Decision = "allow" | "flag" | "block";
export type Ecosystem = "npm" | "pypi";

export interface Envelope {
  action_id?: string;
  decision: Decision;
  reason?: string;
  risk_level?: string;
  project_status?: string;
}

export interface Verdict {
  source?: string; // ossprey | cache | mock
  severity?: string; // malicious | suspicious | unknown | clean | unavailable
  /** False when no scan happened — a scanner outage, not a finding. */
  available?: boolean;
  findings?: string[];
}

export interface BlastRadius {
  credentials_in_scope?: string[];
  network_egress?: string;
  write_access?: string;
  summary?: string;
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
  package?: string;
  version?: string;
  scripts_executed?: Array<{
    lifecycle: string;
    exit_code?: number | null;
    signal?: string | null;
    timed_out?: boolean;
    stdout?: string;
    stderr?: string;
  }>;
  files_created?: string[];
  observations?: string[];
  isolation?: {
    network?: string;
    root_filesystem?: string;
    capabilities?: string;
    host_mounts?: string[];
    memory_mb?: number;
    cpus?: number;
    pids?: number;
  };
}

export interface InstallResult extends Envelope {
  verdict?: Verdict;
  /** Registry-backed package identity. Null in offline fixture mode. */
  sbom?: CycloneDxSbom | null;
  /** Isolated npm lifecycle evidence when sandbox detonation is enabled. */
  sandbox?: SandboxEvidence | null;
  /** Null when the decision is allow. */
  blast_radius?: BlastRadius | null;
  /** Set when the refusal is "we could not look", not "we found something". */
  review_required?: boolean;
  retry_after_seconds?: number;
}

export interface LlmResult extends Envelope {
  /** Null when blocked. */
  answer?: string | null;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  spend_today_usd?: number;
  daily_budget_usd?: number;
}

export interface StatusResult {
  project?: string;
  status?: string;
  spend_today_usd?: number;
  daily_budget_usd?: number;
  remaining_usd?: number;
  requests_last_min?: number;
  max_requests_per_min?: number;
  blocked_today?: number;
  open_incidents?: number;
}
