import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, test } from "node:test";

import { main } from "../dist/cli.js";

const originalCwd = process.cwd();
const originalKey = process.env.JUNO_PROJECT_KEY;
const originalLog = console.log;
const originalError = console.error;
const temporaryDirectories = [];

afterEach(() => {
  process.chdir(originalCwd);
  if (originalKey === undefined) delete process.env.JUNO_PROJECT_KEY;
  else process.env.JUNO_PROJECT_KEY = originalKey;
  console.log = originalLog;
  console.error = originalError;
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

/** A working directory that is, or is not, a git repository. */
function workspace({ git }) {
  const directory = mkdtempSync(join(tmpdir(), "junoguard-init-"));
  temporaryDirectories.push(directory);
  if (git) mkdirSync(join(directory, ".git"));
  mkdirSync(join(directory, ".cursor"));
  process.chdir(directory);
  return directory;
}

/** Run init, returning everything it printed. */
async function runInit(argv) {
  const lines = [];
  console.log = (...args) => lines.push(args.join(" "));
  console.error = (...args) => lines.push(args.join(" "));
  await main(["init", ...argv], { name: "@heysalad/junoguard", version: "0.0.0-test" });
  return lines.join("\n");
}

const pkg = "@heysalad/junoguard";

test("init warns when a project key lands inside a git repository", async () => {
  workspace({ git: true });
  process.env.JUNO_PROJECT_KEY = "jg_live_example";
  const output = await runInit(["cursor"]);
  assert.match(output, /written inside a git repository/);
  assert.match(output, /--global/);
});

test("init stays quiet when the target is not in a repository", async () => {
  workspace({ git: false });
  process.env.JUNO_PROJECT_KEY = "jg_live_example";
  const output = await runInit(["cursor"]);
  assert.doesNotMatch(output, /written inside a git repository/);
});

test("init does not warn when there is no key to leak", async () => {
  workspace({ git: true });
  delete process.env.JUNO_PROJECT_KEY;
  const output = await runInit(["cursor"]);
  assert.doesNotMatch(output, /written inside a git repository/);
});

test("mock mode writes no key, so there is nothing to warn about", async () => {
  workspace({ git: true });
  process.env.JUNO_PROJECT_KEY = "jg_live_example";
  const output = await runInit(["cursor", "--mock"]);
  assert.doesNotMatch(output, /written inside a git repository/);
});

test("a dry run warns about nothing because it wrote nothing", async () => {
  workspace({ git: true });
  process.env.JUNO_PROJECT_KEY = "jg_live_example";
  const output = await runInit(["cursor", "--dry-run"]);
  assert.doesNotMatch(output, /written inside a git repository/);
  assert.ok(pkg);
});
