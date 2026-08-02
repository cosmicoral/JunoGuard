/** Agent workspace scope collection without secret values. */

import {
  accessSync,
  constants,
  existsSync,
  readFileSync,
  statSync,
} from "node:fs";
import { join } from "node:path";

const ENV_FILES = [".env", ".env.local", ".env.development", ".env.production"];
const CREDENTIAL_MARKERS = ["KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE", "DSN"];
const IGNORE = [
  "SSH_AUTH_SOCK",
  "KEYBOARD",
  "KEYMAP",
  "MAX_REQUEST_TOKENS",
  "MAX_TOKENS",
  "MAX_OUTPUT_TOKENS",
  "TOKENS_PER",
  "TOKEN_LIMIT",
  "PUBLIC_KEY",
  "KEY_LENGTH",
];
const CLOUD_NAMES = new Set([
  "AWS_PROFILE",
  "AWS_ACCESS_KEY_ID",
  "GOOGLE_APPLICATION_CREDENTIALS",
  "AZURE_CLIENT_SECRET",
  "KUBECONFIG",
]);
const MAX_ENV_FILE_BYTES = 64 * 1024;
const MAX_NAMES = 200;

export interface AgentScope {
  credential_names: string[];
  workspace_access: "read_only" | "read_write" | "unknown";
  repository: boolean;
}

function isCredential(name: string): boolean {
  const upper = name.toUpperCase();
  if (!/^[A-Z_][A-Z0-9_]*$/.test(upper)) return false;
  if (IGNORE.some((ignored) => upper.includes(ignored))) return false;
  return CLOUD_NAMES.has(upper) || CREDENTIAL_MARKERS.some((marker) => upper.includes(marker));
}

function namesFromEnvFiles(cwd: string): Set<string> {
  const names = new Set<string>();
  for (const filename of ENV_FILES) {
    const path = join(cwd, filename);
    try {
      if (statSync(path).size > MAX_ENV_FILE_BYTES) continue;
      for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line || line.startsWith("#") || !line.includes("=")) continue;
        const name = line.split("=", 1)[0]!.trim().replace(/^export\s+/, "").trim();
        if (name) names.add(name);
      }
    } catch {
      // Missing or unreadable optional env files do not prevent a guard call.
    }
  }
  return names;
}

function workspaceAccess(cwd: string): AgentScope["workspace_access"] {
  try {
    accessSync(cwd, constants.R_OK);
  } catch {
    return "unknown";
  }
  try {
    accessSync(cwd, constants.W_OK);
    return "read_write";
  } catch {
    return "read_only";
  }
}

export function collectAgentScope(
  cwd = process.cwd(),
  environment: NodeJS.ProcessEnv = process.env,
): AgentScope {
  const candidates = new Set([...Object.keys(environment), ...namesFromEnvFiles(cwd)]);
  const credentialNames = [...candidates]
    .filter(isCredential)
    .sort()
    .slice(0, MAX_NAMES);

  return {
    credential_names: credentialNames,
    workspace_access: workspaceAccess(cwd),
    repository: existsSync(join(cwd, ".git")),
  };
}
