import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isHostSandboxEnabled,
  wrapArgvForHostSandbox,
} from "../dist/host-sandbox.js";

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
  const argv = ["/usr/bin/npm", "install", "lodash"];
  const wrapped = wrapArgvForHostSandbox(argv, {
    env: { JUNO_HOST_SANDBOX: "1", PATH: "/usr/bin" },
    platform: "darwin",
    cwd: "/tmp/project",
    home: "/tmp/home",
  });
  assert.ok("argv" in wrapped);
  assert.equal(wrapped.argv[0], "/usr/bin/sandbox-exec");
  assert.match(wrapped.argv.join(" "), /-DPROJECT=\/tmp\/project/);
  assert.match(wrapped.argv.join(" "), /\/usr\/bin\/npm install lodash$/);
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
