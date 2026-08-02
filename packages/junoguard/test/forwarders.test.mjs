import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { main, withIgnoredScripts } from "../dist/cli.js";

const originalMock = process.env.JUNO_MOCK;
const originalLog = console.log;
const originalError = console.error;

afterEach(() => {
  if (originalMock === undefined) delete process.env.JUNO_MOCK;
  else process.env.JUNO_MOCK = originalMock;
  console.log = originalLog;
  console.error = originalError;
});

function silence() {
  console.log = () => {};
  console.error = () => {};
}

test("pnpm forwarder refuses a mock-blocked package before spawning", async () => {
  process.env.JUNO_MOCK = "1";
  silence();
  const code = await main(["pnpm", "install", "@ossprey/test-package"], {
    name: "@heysalad/junoguard",
    version: "0.0.0-test",
  });
  assert.equal(code, 2);
});

test("yarn lockfile install is refused without an override", async () => {
  process.env.JUNO_MOCK = "1";
  silence();
  const code = await main(["yarn", "install"], {
    name: "@heysalad/junoguard",
    version: "0.0.0-test",
  });
  assert.equal(code, 5);
});

test("npm and pnpm installs get --ignore-scripts by default", () => {
  assert.deepEqual(withIgnoredScripts(["npm", "install", "lodash"], "npm"), [
    "npm",
    "install",
    "--ignore-scripts",
    "lodash",
  ]);
  assert.deepEqual(withIgnoredScripts(["pnpm", "add", "react"], "pnpm"), [
    "pnpm",
    "add",
    "--ignore-scripts",
    "react",
  ]);
  assert.deepEqual(
    withIgnoredScripts(["npm", "install", "--no-ignore-scripts", "lodash"], "npm"),
    ["npm", "install", "--no-ignore-scripts", "lodash"],
  );
});

test("help lists pnpm and yarn forwarders", async () => {
  let printed = "";
  console.log = (value) => {
    printed += String(value);
  };
  const code = await main(["--help"], {
    name: "@heysalad/junoguard",
    version: "0.0.0-test",
  });
  assert.equal(code, 0);
  assert.match(printed, /pnpm install/);
  assert.match(printed, /yarn add/);
});
