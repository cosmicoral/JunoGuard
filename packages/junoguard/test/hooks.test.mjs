import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  decideBeforeShell,
  hookShellResponse,
  isAlreadyJunoGated,
  isUngatedInstallCommand,
  writeCursorHooks,
} from "../dist/hooks.js";

const temporaryDirectories = [];
const fixturesRoot = fileURLToPath(new URL("./.tmp-hooks", import.meta.url));

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("denies bare package-manager installs including absolute paths", () => {
  for (const command of [
    "npm install lodash",
    "pnpm add react",
    "yarn add zod",
    "yarn install",
    "pip install requests",
    "python -m pip install flask",
    "/usr/bin/npm install left-pad",
    "cd packages/app && npm i lodash",
    "npm ci",
  ]) {
    assert.equal(isUngatedInstallCommand(command), true, command);
    assert.equal(decideBeforeShell(command).permission, "deny", command);
  }
});

test("allows non-install shells and juno-gated installs", () => {
  for (const command of [
    "npm test",
    "npm run build",
    "npm run install",
    "pnpm run lint",
    "git status",
    "juno npm install lodash",
    "npx -y @heysalad/junoguard npm install lodash",
    "node ./node_modules/@heysalad/junoguard/dist/bin.js pnpm add react",
  ]) {
    assert.equal(isUngatedInstallCommand(command), false, command);
    assert.equal(decideBeforeShell(command).permission, "allow", command);
  }
  assert.equal(isAlreadyJunoGated("juno yarn add zod"), true);
});

test("hook shell fails closed on invalid stdin", () => {
  const body = JSON.parse(hookShellResponse("not-json"));
  assert.equal(body.permission, "deny");
  assert.match(body.agent_message, /refused/i);
});

test("hook shell strips UTF-8 BOM from Cursor payloads", () => {
  const payload = `\uFEFF${JSON.stringify({ command: "npm install evil" })}`;
  const body = JSON.parse(hookShellResponse(payload));
  assert.equal(body.permission, "deny");
});

test("hooks.json merge preserves neighbors and is replaceable with --force", () => {
  mkdirSync(fixturesRoot, { recursive: true });
  const cwd = mkdtempSync(join(fixturesRoot, "case-"));
  temporaryDirectories.push(cwd);
  // Avoid writing under `.cursor/` in tests — some environments block that path.
  const hooksPath = join(cwd, "hooks.json");
  writeFileSync(
    hooksPath,
    `${JSON.stringify(
      {
        version: 1,
        hooks: {
          beforeShellExecution: [{ command: "./hooks/audit.sh" }],
        },
      },
      null,
      2,
    )}\n`,
  );

  const first = writeCursorHooks("project", cwd, "npx -y @heysalad/junoguard hook shell", {
    hooksPath,
  });
  assert.equal(first.kind, "written");
  const second = writeCursorHooks("project", cwd, "npx -y @heysalad/junoguard hook shell", {
    hooksPath,
  });
  assert.equal(second.kind, "exists");
  const forced = writeCursorHooks("project", cwd, "npx -y @heysalad/junoguard hook shell", {
    force: true,
    hooksPath,
  });
  assert.equal(forced.kind, "written");

  const config = JSON.parse(readFileSync(hooksPath, "utf8"));
  assert.equal(config.version, 1);
  assert.equal(config.hooks.beforeShellExecution.length, 2);
  assert.equal(config.hooks.beforeShellExecution[0].command, "./hooks/audit.sh");
  assert.equal(config.hooks.beforeShellExecution[1].failClosed, true);
  assert.match(config.hooks.beforeShellExecution[1].command, /hook shell/);
});
