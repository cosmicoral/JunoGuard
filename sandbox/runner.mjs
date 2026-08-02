import { lstatSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { spawnSync } from "node:child_process";

const ARTIFACT = "/input/package.tgz";
const WORK = "/work";
const PACKAGE = join(WORK, "package");
const LIFECYCLES = ["preinstall", "install", "postinstall"];
const OUTPUT_LIMIT = 4_000;
const FILE_LIMIT = 200;
const SCRIPT_TIMEOUT_MS = 3_000;

function clipped(value) {
  return String(value ?? "").slice(-OUTPUT_LIMIT);
}

function filesUnder(root) {
  const found = [];
  const visit = (directory) => {
    for (const name of readdirSync(directory)) {
      if (found.length >= FILE_LIMIT) return;
      const path = join(directory, name);
      const stat = lstatSync(path);
      found.push(relative(root, path));
      if (stat.isDirectory() && !stat.isSymbolicLink()) visit(path);
    }
  };
  visit(root);
  return found.sort();
}

function emit(result) {
  process.stdout.write(`JUNO_SANDBOX_RESULT=${JSON.stringify(result)}\n`);
}

mkdirSync(WORK, { recursive: true });
const extraction = spawnSync(
  "tar",
  ["-xzf", ARTIFACT, "-C", WORK, "--no-same-owner", "--no-same-permissions"],
  { encoding: "utf8", timeout: SCRIPT_TIMEOUT_MS },
);
if (extraction.status !== 0) {
  emit({
    status: "artifact_rejected",
    scripts_executed: [],
    observations: ["package archive could not be extracted"],
    stderr: clipped(extraction.stderr),
  });
  process.exit(0);
}

let manifest;
try {
  manifest = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
} catch (error) {
  emit({
    status: "artifact_rejected",
    scripts_executed: [],
    observations: ["package.json is missing or invalid"],
    stderr: clipped(error),
  });
  process.exit(0);
}

const before = new Set(filesUnder(PACKAGE));
const scripts = manifest.scripts && typeof manifest.scripts === "object" ? manifest.scripts : {};
const executions = [];

for (const lifecycle of LIFECYCLES) {
  const command = scripts[lifecycle];
  if (typeof command !== "string" || !command.trim()) continue;

  const run = spawnSync(command, {
    cwd: PACKAGE,
    shell: true,
    encoding: "utf8",
    timeout: SCRIPT_TIMEOUT_MS,
    env: {
      HOME: "/tmp",
      PATH: "/usr/local/bin:/usr/bin:/bin",
      npm_lifecycle_event: lifecycle,
      npm_package_name: String(manifest.name ?? ""),
      npm_package_version: String(manifest.version ?? ""),
    },
  });
  executions.push({
    lifecycle,
    exit_code: run.status,
    signal: run.signal,
    timed_out: run.error?.code === "ETIMEDOUT",
    stdout: clipped(run.stdout),
    stderr: clipped(run.stderr),
  });
}

const after = filesUnder(PACKAGE);
const createdFiles = after.filter((path) => !before.has(path));
const combinedOutput = executions.map((item) => `${item.stdout}\n${item.stderr}`).join("\n");
const observations = [];
if (executions.some((item) => item.timed_out)) observations.push("lifecycle script exceeded time limit");
if (executions.some((item) => item.exit_code !== 0)) observations.push("lifecycle script exited non-zero");
if (/ENETUNREACH|EAI_AGAIN|ECONNREFUSED|network is unreachable/i.test(combinedOutput)) {
  observations.push("lifecycle script attempted network access; sandbox network was disabled");
}
if (/\/etc\/(passwd|shadow)|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|SUPABASE_SERVICE_ROLE_KEY/i.test(
  combinedOutput,
)) {
  observations.push("lifecycle output referenced credential or host-sensitive material");
}
if (createdFiles.length) observations.push(`lifecycle scripts created ${createdFiles.length} file(s)`);

emit({
  status: "completed",
  package: String(manifest.name ?? ""),
  version: String(manifest.version ?? ""),
  scripts_executed: executions,
  files_created: createdFiles.slice(0, FILE_LIMIT),
  observations,
});
