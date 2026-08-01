#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { main } from "./cli.js";

// Name and version both come from package.json so that `init` always writes
// the npx name this build was actually published under — scoped or not.
const pkg = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
) as { name: string; version: string };

main(process.argv.slice(2), pkg).then(
  (code) => {
    process.exitCode = code;
  },
  (error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  },
);
