import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, test } from "node:test";

import {
  isHostSandboxEnabled,
  wrapArgvForHostSandbox,
} from "../dist/host-sandbox.js";

const temporaryDirectories = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function fakeHelper(name) {
  const directory = mkdtempSync(join(tmpdir(), "junoguard-sandbox-bin-"));
  temporaryDirectories.push(directory);
  const path = join(directory, name);
  writeFileSync(path, "#!/bin/sh\nexec \"$@\"\n");
  chmodSync(path, 0o755);
  return { directory, path };
}

test("host sandbox is opt-in via JUNO_HOST_SANDBOX", () => {
  assert.equal(isHostSandboxEnabled({}), false);
  assert.equal(isHostSandboxEnabled({ JUNO_HOST_SANDBOX: "1" }), true);
  assert.equal(isHostSandboxEnabled({ JUNO_HOST_SANDBOX: "true" }), true);
});

test("wrapArgvForHostSandbox passes through when disabled", () => {
  const argv = ["/usr/bin/npm", "install", "lodash"];
  assert.deepEqual(wrapArgvForHostSandbox(argv, { env: {} }), { argv });
});

test("wrapArgvForHostSandbox wraps on darwin when enabled", () => {
  const { directory, path } = fakeHelper("sandbox-exec");
  const argv = ["/usr/bin/npm", "install", "lodash"];
  const wrapped = wrapArgvForHostSandbox(argv, {
    env: { JUNO_HOST_SANDBOX: "1", PATH: directory },
    platform: "darwin",
    cwd: "/tmp/project",
    home: "/tmp/home",
  });
  assert.ok("argv" in wrapped);
  assert.equal(wrapped.argv[0], path);
  assert.match(wrapped.argv.join(" "), /-DPROJECT=\/tmp\/project/);
  assert.match(wrapped.argv.join(" "), /\/usr\/bin\/npm install lodash$/);
});

test("wrapArgvForHostSandbox wraps on linux when bwrap is present", () => {
  const { directory, path } = fakeHelper("bwrap");
  const wrapped = wrapArgvForHostSandbox(["npm", "install", "lodash"], {
    env: { JUNO_HOST_SANDBOX: "1", PATH: directory },
    platform: "linux",
    cwd: "/tmp/project",
    home: "/tmp/home",
  });
  assert.ok("argv" in wrapped);
  assert.equal(wrapped.argv[0], path);
  assert.match(wrapped.argv.join(" "), /npm install lodash$/);
});

test("wrapArgvForHostSandbox fails closed when helper is missing", () => {
  const wrapped = wrapArgvForHostSandbox(["npm", "install", "lodash"], {
    env: { JUNO_HOST_SANDBOX: "1", PATH: "" },
    platform: "darwin",
    cwd: "/tmp/project",
    home: "/tmp/home",
  });
  assert.ok("error" in wrapped);
  assert.match(wrapped.error, /sandbox-exec/);
});

test("wrapArgvForHostSandbox fails closed on unsupported platforms", () => {
  const wrapped = wrapArgvForHostSandbox(["npm", "install", "lodash"], {
    env: { JUNO_HOST_SANDBOX: "1" },
    platform: "win32",
    cwd: "/tmp/project",
    home: "/tmp/home",
  });
  assert.ok("error" in wrapped);
  assert.match(wrapped.error, /not supported on win32/);
});
