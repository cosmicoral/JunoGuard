import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, test } from "node:test";

import { JunoClient } from "../dist/client.js";
import { collectAgentScope } from "../dist/scope.js";

const originalCwd = process.cwd();
const originalFetch = globalThis.fetch;
const temporaryDirectories = [];

afterEach(() => {
  process.chdir(originalCwd);
  globalThis.fetch = originalFetch;
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function workspace() {
  const directory = mkdtempSync(join(tmpdir(), "junoguard-scope-"));
  temporaryDirectories.push(directory);
  mkdirSync(join(directory, ".git"));
  writeFileSync(
    join(directory, ".env"),
    [
      "OPENAI_API_KEY=super-secret-value",
      "export AWS_PROFILE=production",
      "MAX_REQUEST_TOKENS=4000",
      "NORMAL_SETTING=visible",
    ].join("\n"),
  );
  return directory;
}

test("collects credential names without values", () => {
  const directory = workspace();

  const scope = collectAgentScope(directory, {
    GITHUB_TOKEN: "another-secret-value",
    NORMAL_ENV: "not-sensitive",
  });

  assert.deepEqual(scope.credential_names, [
    "AWS_PROFILE",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
  ]);
  assert.equal(scope.repository, true);
  assert.equal(scope.workspace_access, "read_write");
  assert.doesNotMatch(JSON.stringify(scope), /super-secret-value|another-secret-value/);
});

test("guard install attaches local scope to the request", async () => {
  const directory = workspace();
  process.chdir(directory);
  let requestBody;
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(String(init.body));
    return new Response(JSON.stringify({ decision: "allow" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new JunoClient({
    apiUrl: "https://gateway.example",
    projectKey: "jg_test",
  });
  await client.guardInstall("example", "npm", "1.0.0");

  assert.equal(requestBody.agent_scope.repository, true);
  assert.ok(requestBody.agent_scope.credential_names.includes("OPENAI_API_KEY"));
  assert.doesNotMatch(JSON.stringify(requestBody), /super-secret-value/);
});
