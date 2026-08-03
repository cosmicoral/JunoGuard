import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  accessSync,
  chmodSync,
  constants,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";
import { afterEach, test } from "node:test";

import { main } from "../dist/cli.js";
import {
  disableWrap,
  enableWrap,
  resolveRealBinary,
  shimPath,
  wrapDir,
  wrapStatus,
} from "../dist/wrap.js";

const temporaryDirectories = [];
const originalCwd = process.cwd();
const originalPath = process.env.PATH;
const originalMock = process.env.JUNO_MOCK;
const originalWrapDir = process.env.JUNO_WRAP_DIR;
const originalLog = console.log;
const originalError = console.error;

afterEach(() => {
  process.chdir(originalCwd);
  process.env.PATH = originalPath;
  if (originalMock === undefined) delete process.env.JUNO_MOCK;
  else process.env.JUNO_MOCK = originalMock;
  if (originalWrapDir === undefined) delete process.env.JUNO_WRAP_DIR;
  else process.env.JUNO_WRAP_DIR = originalWrapDir;
  console.log = originalLog;
  console.error = originalError;
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function workspace() {
  const directory = mkdtempSync(join(tmpdir(), "junoguard-wrap-"));
  temporaryDirectories.push(directory);
  return directory;
}

function silence() {
  console.log = () => {};
  console.error = () => {};
}

test("wrap on writes executable shims and status reports them", () => {
  const cwd = workspace();
  const { dir, created } = enableWrap({ cwd });
  assert.equal(dir, wrapDir(cwd));
  assert.equal(created.length, 6);
  for (const manager of ["npm", "pnpm", "yarn", "pip", "poetry", "uv"]) {
    accessSync(shimPath(manager, cwd), constants.X_OK);
  }
  const status = wrapStatus(cwd);
  assert.deepEqual(status.active, ["npm", "pnpm", "yarn", "pip", "poetry", "uv"]);
  assert.equal(status.missing.length, 0);
});

test("resolveRealBinary skips the wrap directory", () => {
  const cwd = workspace();
  const { dir } = enableWrap({ cwd });
  const realDir = join(cwd, "real-bin");
  mkdirSync(realDir);
  const realNpm = join(realDir, "npm");
  writeFileSync(realNpm, "#!/bin/sh\necho real\n");
  chmodSync(realNpm, 0o755);

  const resolved = resolveRealBinary("npm", {
    PATH: `${dir}${delimiter}${realDir}`,
    JUNO_WRAP_DIR: dir,
  });
  assert.equal(resolved, realNpm);
});

test("wrap off removes shims", () => {
  const cwd = workspace();
  enableWrap({ cwd });
  const { removed } = disableWrap(cwd);
  assert.equal(removed.length, 6);
  assert.deepEqual(wrapStatus(cwd).active, []);
});

test("PATH shim blocks a mock-malicious npm install without recursion", () => {
  const cwd = workspace();
  process.chdir(cwd);
  process.env.JUNO_MOCK = "1";
  const { dir } = enableWrap({ cwd });
  silence();

  const result = spawnSync(join(dir, "npm"), ["install", "@ossprey/test-package"], {
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${dir}${delimiter}${process.env.PATH ?? ""}`,
      JUNO_MOCK: "1",
      JUNO_WRAP_DIR: dir,
    },
  });

  assert.equal(result.status, 2);
  assert.match(`${result.stdout}\n${result.stderr}`, /not installed|was not run|BLOCK/i);
});

test("juno wrap status reports inactive wrap", async () => {
  const cwd = workspace();
  process.chdir(cwd);
  silence();
  const code = await main(["wrap", "status"], {
    name: "@heysalad/junoguard",
    version: "0.0.0-test",
  });
  assert.equal(code, 0);
});
