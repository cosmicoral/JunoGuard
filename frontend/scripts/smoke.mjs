/**
 * Post-build smoke check: the production bundle still distinguishes demo,
 * degraded, and live modes on screen (JG-007 / JG-008 / JG-013).
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dist = new URL("../dist/", import.meta.url);
const html = readFileSync(new URL("index.html", dist), "utf8");
if (!html.includes('id="root"')) {
  console.error("dist/index.html is missing the React root");
  process.exit(1);
}

const assets = readdirSync(new URL("assets/", dist));
const jsName = assets.find((name) => name.endsWith(".js"));
if (!jsName) {
  console.error("no JS bundle in dist/assets");
  process.exit(1);
}

const bundle = readFileSync(join(new URL("assets/", dist).pathname, jsName), "utf8");
const needles = [
  "DEMO",
  "GATEWAY UNREACHABLE",
  "ENTER DEMO SIMULATION",
  "SIMULATION",
  "CycloneDX SBOM",
  "Sandbox detonation",
  "Scope evidence",
  "Product guide",
];

const missing = needles.filter((needle) => !bundle.includes(needle));
if (missing.length) {
  console.error("production bundle is missing mode labels:", missing.join(", "));
  process.exit(1);
}

console.log("smoke ok:", jsName);
