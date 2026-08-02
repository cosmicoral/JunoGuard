import { lstatSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { join, posix, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { gunzipSync } from "node:zlib";

const ARTIFACT = "/input/package.tgz";
const WORK = "/work";
const PACKAGE = join(WORK, "package");
const LIFECYCLES = ["preinstall", "install", "postinstall"];
const OUTPUT_LIMIT = 4_000;
const FILE_LIMIT = 200;
const SCRIPT_TIMEOUT_MS = 3_000;
const ARCHIVE_FILE_LIMIT = 2_000;
const ARCHIVE_SIZE_LIMIT = 64 * 1024 * 1024;
const ARCHIVE_OUTPUT_LIMIT = ARCHIVE_SIZE_LIMIT + ARCHIVE_FILE_LIMIT * 1024;

export class ArtifactRejected extends Error {}

function tarString(header, start, length) {
  return header.subarray(start, start + length).toString("utf8").split("\0", 1)[0].trim();
}

function tarOctal(header, start, length) {
  if (header[start] & 0x80) throw new ArtifactRejected("archive uses an unsupported numeric format");
  const value = tarString(header, start, length);
  if (!/^[0-7]+$/.test(value)) throw new ArtifactRejected("archive contains malformed metadata");
  return Number.parseInt(value, 8);
}

function validateChecksum(header) {
  const expected = tarOctal(header, 148, 8);
  let actual = 0;
  for (let index = 0; index < header.length; index += 1) {
    actual += index >= 148 && index < 156 ? 32 : header[index];
  }
  if (actual !== expected) throw new ArtifactRejected("archive header checksum is invalid");
}

function validatePath(name) {
  if (!name || name.includes("\\") || name.startsWith("/")) {
    throw new ArtifactRejected("archive contains an unsafe path");
  }
  const parts = name.split("/");
  const normalized = posix.normalize(name);
  if (parts.includes("..") || normalized === ".." || normalized.startsWith("../")) {
    throw new ArtifactRejected("archive contains a path outside its extraction root");
  }
}

function parsePax(body) {
  const attributes = {};
  let offset = 0;
  while (offset < body.length) {
    const separator = body.indexOf(32, offset);
    if (separator < 0) throw new ArtifactRejected("archive contains malformed PAX metadata");
    const length = Number.parseInt(body.subarray(offset, separator).toString("ascii"), 10);
    if (!Number.isSafeInteger(length) || length <= 0 || offset + length > body.length) {
      throw new ArtifactRejected("archive contains malformed PAX metadata");
    }
    const record = body.subarray(separator + 1, offset + length);
    if (record.at(-1) !== 10) throw new ArtifactRejected("archive contains malformed PAX metadata");
    const assignment = record.subarray(0, -1).toString("utf8");
    const equals = assignment.indexOf("=");
    if (equals <= 0) throw new ArtifactRejected("archive contains malformed PAX metadata");
    attributes[assignment.slice(0, equals)] = assignment.slice(equals + 1);
    offset += length;
  }
  return attributes;
}

export function validateTarballBuffer(compressed) {
  let archive;
  try {
    archive = gunzipSync(compressed, { maxOutputLength: ARCHIVE_OUTPUT_LIMIT });
  } catch (error) {
    throw new ArtifactRejected(`archive could not be decompressed within limits: ${error}`);
  }

  let offset = 0;
  let entries = 0;
  let expandedSize = 0;
  let terminated = false;
  let pendingPath = null;
  let pendingSize = null;
  while (offset + 512 <= archive.length) {
    const header = archive.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) {
      terminated = true;
      break;
    }
    validateChecksum(header);
    const name = tarString(header, 0, 100);
    const prefix = tarString(header, 345, 155);
    const headerPath = prefix ? `${prefix}/${name}` : name;
    validatePath(headerPath);
    const type = String.fromCharCode(header[156] || 48);
    const size = tarOctal(header, 124, 12);
    entries += 1;
    expandedSize += size;
    if (entries > ARCHIVE_FILE_LIMIT) throw new ArtifactRejected("archive contains too many entries");
    if (expandedSize > ARCHIVE_SIZE_LIMIT) {
      throw new ArtifactRejected("archive expands beyond the size limit");
    }

    const bodyStart = offset + 512;
    const nextOffset = bodyStart + Math.ceil(size / 512) * 512;
    if (nextOffset > archive.length) throw new ArtifactRejected("archive is truncated");
    const body = archive.subarray(bodyStart, bodyStart + size);

    if (type === "x") {
      const attributes = parsePax(body);
      if (attributes.linkpath) throw new ArtifactRejected("archive contains a link entry");
      if (attributes.path) {
        validatePath(attributes.path);
        pendingPath = attributes.path;
      }
      if (attributes.size !== undefined) {
        const value = Number(attributes.size);
        if (!Number.isSafeInteger(value) || value < 0) {
          throw new ArtifactRejected("archive contains malformed PAX size metadata");
        }
        pendingSize = value;
      }
    } else if (type === "L") {
      const longPath = body.toString("utf8").split("\0", 1)[0];
      validatePath(longPath);
      pendingPath = longPath;
    } else if (type === "0" || type === "5") {
      validatePath(pendingPath || headerPath);
      if (pendingSize !== null && pendingSize !== size) {
        throw new ArtifactRejected("archive PAX size does not match its file header");
      }
      if (type === "5" && size !== 0) {
        throw new ArtifactRejected("archive directory contains unexpected data");
      }
      pendingPath = null;
      pendingSize = null;
    } else {
      throw new ArtifactRejected("archive contains a link or special entry");
    }

    offset = nextOffset;
  }
  if (!terminated || entries === 0 || pendingPath !== null || pendingSize !== null) {
    throw new ArtifactRejected("archive is empty, unterminated, or has dangling metadata");
  }
}

export function validateTarball(path) {
  validateTarballBuffer(readFileSync(path));
}

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

export function main() {
  mkdirSync(WORK, { recursive: true });
  try {
    validateTarball(ARTIFACT);
  } catch (error) {
    emit({
      status: "artifact_rejected",
      scripts_executed: [],
      observations: [error instanceof Error ? error.message : "package archive is unsafe"],
      stderr: clipped(error),
    });
    return;
  }

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
    return;
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
    return;
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
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main();
}
