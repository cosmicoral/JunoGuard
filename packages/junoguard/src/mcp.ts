/**
 * JunoGuard MCP server.
 *
 * Three tools over stdio. Whatever these return is rendered straight into the
 * agent's chat, so the return value is the product surface, not a debug dump.
 *
 * Design notes that matter:
 *
 * - A block is a successful call. It returns HTTP 200 from the gateway and a
 *   rendered refusal from here. It never throws — an exception surfaces as a
 *   tool failure, and a failed tool is something an agent retries.
 * - If the gateway is unreachable we still return a string, but one shaped
 *   like a refusal. An unconsultable guard is not permission to proceed.
 * - The refusal text is written for the agent, not just the human: it states
 *   plainly that nothing was installed and that it should pick an alternative.
 *
 * Nothing here may write to stdout — that channel carries JSON-RPC framing.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { JunoClient, JunoNotConfigured, JunoUnavailable } from "./client.js";
import {
  renderError,
  renderInstall,
  renderLlm,
  renderNotConfigured,
  renderStatus,
  toPlain,
} from "./render.js";
import type { Ecosystem } from "./types.js";

const asText = (value: string) => ({ content: [{ type: "text" as const, text: value }] });

function unavailable(subject: string, error: unknown, consequence: string) {
  if (error instanceof JunoNotConfigured) {
    return asText(toPlain(renderNotConfigured(subject, new JunoClient().apiUrl)));
  }
  const detail = error instanceof JunoUnavailable ? error.detail : String(error);
  return asText(toPlain(renderError(subject, detail, consequence)));
}

export function createServer(version: string): McpServer {
  const server = new McpServer({ name: "junoguard", version });

  server.registerTool(
    "guard_install",
    {
      title: "Guard a package install",
      description: [
        "Check a package with JunoGuard BEFORE installing it. Required for every install.",
        "",
        "Call this first, every time, for any dependency you are about to add — npm,",
        "pnpm, yarn, pip, poetry, uv, or a manifest edit. Only run the real package",
        "manager if this returns an allow.",
        "",
        "Returns a decision. If it is a block, the package was NOT installed: do not",
        "retry it and do not try another package manager — choose a different",
        "dependency, or tell the user no safe option exists.",
      ].join("\n"),
      inputSchema: {
        package: z.string().describe('Package name, e.g. "express" or "@ossprey/test-package".'),
        ecosystem: z.enum(["npm", "pypi"]).default("npm").describe('"npm" or "pypi".'),
        version: z.string().optional().describe("Optional exact version. Omit for latest."),
      },
    },
    async ({ package: pkg, ecosystem, version }) => {
      const eco = (ecosystem ?? "npm") as Ecosystem;
      try {
        const payload = await new JunoClient().guardInstall(pkg, eco, version);
        return asText(toPlain(renderInstall(payload, pkg, eco)));
      } catch (error) {
        return unavailable(
          `${pkg}  (${eco})`,
          error,
          "The guard could not be consulted, so this install is not approved.\n" +
            "Do not install this package. Start the JunoGuard gateway, or set\n" +
            "JUNO_MOCK=1 for offline mode, then try again.",
        );
      }
    },
  );

  server.registerTool(
    "guard_llm",
    {
      title: "Guard a model call",
      description: [
        "Make a model call through JunoGuard, with budget and burst policy applied.",
        "",
        "The provider key stays server-side and never reaches this client. Token",
        "counts, cost, and the running daily spend come back with the answer.",
        "",
        "If the result is a block, no model call was made and nothing was charged.",
        "Do not retry the same call — reduce it, or stop and ask the operator.",
      ].join("\n"),
      inputSchema: {
        prompt: z.string().describe("The prompt to send."),
        model: z.string().default("gpt-4o").describe("Model id."),
        max_output_tokens: z.number().int().positive().default(300).describe("Output cap."),
      },
    },
    async ({ prompt, model, max_output_tokens }) => {
      const chosen = model ?? "gpt-4o";
      try {
        const payload = await new JunoClient().guardLlm(prompt, chosen, max_output_tokens ?? 300);
        return asText(toPlain(renderLlm(payload, chosen)));
      } catch (error) {
        return unavailable(
          `model call  ·  ${chosen}`,
          error,
          "The guard could not be consulted, so this call was not made.\n" +
            "Start the JunoGuard gateway, or set JUNO_MOCK=1 for offline mode.",
        );
      }
    },
  );

  server.registerTool(
    "guard_status",
    {
      title: "Check budget and incidents",
      description: [
        "Check this project's JunoGuard budget, spend, rate limit, and incidents.",
        "",
        "Cheap and safe to poll. Call it before a run of expensive work so you know",
        "the remaining budget instead of discovering the limit by hitting it. If the",
        "project is suspended, stop: every install and model call will be blocked.",
      ].join("\n"),
      inputSchema: {},
    },
    async () => {
      try {
        return asText(toPlain(renderStatus(await new JunoClient().status())));
      } catch (error) {
        return unavailable(
          "project status",
          error,
          "The guard could not be consulted. Assume no budget is available\n" +
            "and do not proceed with guarded work.",
        );
      }
    },
  );

  return server;
}

export async function runStdioServer(version: string): Promise<void> {
  const server = createServer(version);
  await server.connect(new StdioServerTransport());
}
