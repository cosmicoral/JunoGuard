# `npx @heysalad/junoguard init`: wire Cursor, Claude Code, and Codex without a default project key.

**Series:** JunoGuard field notes  
**Citation style:** Chicago Manual of Style, 17th ed. (notes and bibliography)  
**Primary keyword:** JunoGuard init

---

![Figure 1. Install path without a default project key](./assets/jg-install-path.png)

**Figure 1.** `init` wires agents fail-closed: no embedded key, mock mode for proof, live mode requires `JUNO_PROJECT_KEY`. Illustration by JunoGuard.

The fastest way to fail at agent security is to ship a default credential. It looks configured. It silently 401s against a gateway nobody deployed. Or worse — it works once, gets committed, and publishes a live project key to a public remote.

JunoGuard does not embed a project key. `init` writes agent config that **fails closed** until you supply one — or until you explicitly opt into offline mock mode to prove the UX first.

## One command, three agents

```bash
npx @heysalad/junoguard init
```

With no arguments, `init` detects agent configuration in the current directory and writes JunoGuard MCP entries for Cursor, Claude Code, and Codex when their config files are present. You can also name agents explicitly:

```bash
npx @heysalad/junoguard init cursor claude-code codex
```

For each agent, `init` adds an MCP server entry pointing at `npx -y @heysalad/junoguard mcp` (or a local checkout with `--local` for pre-publish testing). Cursor and Claude Code also get shell hooks that route package-manager invocations through Juno’s forwarder when the agent runs shell commands.[^1]

Restart the agent — or refresh its MCP panel — after `init` completes.

## Fail closed without a key

If you run `init` without `JUNO_PROJECT_KEY` in your environment and without `--mock`, the written config is **incomplete on purpose**. Every guarded action will refuse until you add a key to the env block or export it in your shell.

You will see a explicit warning:

> no JUNO_PROJECT_KEY in your environment — the config is incomplete.

That is preferable to discovering mid-demo that the agent has been proceeding unguarded because a fake key looked valid.

Clients require `JUNO_PROJECT_KEY` for live use and send it as `X-Juno-Key`. There is no default key in the box.[^1]

## Mock first: proof without credentials

For demos, docs, and CI, use mock mode:

```bash
npx @heysalad/junoguard init --mock
```

`--mock` writes `JUNO_MOCK=1` into the agent env block. No gateway. No network. No key. The clients return the same decision vocabulary as live — including the `@ossprey/test-package` block fixture:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

Mock mode is the insurance policy: if the gateway is down, behavior stays deterministic. Allows, flags, and blocks still render; scanner semantics still refuse on outage in live mode.

When you are ready for live policy, export a real project key from your gateway, re-run `init` without `--mock`, and restart the agent.

## Global vs project scope

By default, `init` writes **project-scoped** config — `.cursor/mcp.json`, `.mcp.json`, and hook files beside your repo. That is appropriate when the whole team shares one setup.

Use `--global` to write user-level config outside the repository. Prefer `--global` when the env block would carry `JUNO_PROJECT_KEY`: `init` warns loudly if a key is written inside a git working tree, because committing it publishes the credential. Rotating afterwards is the only fix.[^1]

Dry-run with `--dry-run` to preview paths without writing.

## What `init` does not do

`init` does not turn on PATH wrap automatically. After MCP and hooks are wired, opt in separately:

```bash
juno wrap on
```

That writes `.junoguard/bin` shims for npm, pnpm, yarn, and pip so bare invocations hit the forwarder when the directory is on PATH. Absolute paths to the real binary still bypass the wrap. JunoGuard does not claim poetry or uv gating.[^1]

`init` also does not deploy a gateway. Live policy needs `JUNO_API_URL` pointing at a running JunoGuard backend and a project key you created in the console — not one we invented for you.

## The dual lane you are wiring

![Figure 2. Dual-lane control plane](./assets/jg-dual-lane.png)

**Figure 2.** MCP exposes Lane A (`guard_install`) and Lane B (`guard_llm`); hooks and forwarders cover shell paths MCP does not see. Illustration by JunoGuard.

MCP tools:

- **`guard_install`** — Lane A. Scan a dependency before it reaches disk.
- **`guard_llm`** — Lane B. Proxied model call under budget and burst policy.
- **`guard_status`** — project state, spend, kill switch visibility.

MCP exposure is **advisory**: it works when the agent calls the tool. Shell hooks and forwarders close more of the gap for package managers the agent invokes directly. Research on MCP tool poisoning shows why tool metadata integrity matters on the tools you *do* expose — Juno hashes its own MCP definitions in `tools.lock.json` and refuses to start on mismatch.[^2] That protects Juno’s surface, not the entire ecosystem.

## Live checklist

1. Deploy or run the JunoGuard gateway (see [junoguard.com](https://junoguard.com)).[^3]
2. Create a project key in the console.
3. `export JUNO_PROJECT_KEY=…` (and `JUNO_API_URL` if not default).
4. `npx @heysalad/junoguard init` — prefer `--global` if the key would land in a tracked file.
5. Optional: `juno wrap on` for PATH shims.
6. Restart Cursor / Claude Code / Codex.
7. Prove refusal UX with mock first if stakeholders need to see a block before keys are issued.

## Start here

Product and console: [junoguard.com](https://junoguard.com).[^3]

Install path:

```bash
npx @heysalad/junoguard init
```

Fail closed by default. Mock when you need proof. Live when you have a key you chose.

---

## Notes

[^1]: HeySalad, “@heysalad/junoguard,” npm, August 1, 2026, https://www.npmjs.com/package/@heysalad/junoguard.

[^2]: Beurer-Kellner and Fischer, “MCP Security Notification.”

[^3]: HeySalad, “JunoGuard,” accessed August 3, 2026, https://junoguard.com.

---

## Bibliography

Beurer-Kellner, Luca, and Marc Fischer. “MCP Security Notification: Tool Poisoning Attacks.” Invariant Labs, April 2025. https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

HeySalad. “@heysalad/junoguard.” npm, August 1, 2026. https://www.npmjs.com/package/@heysalad/junoguard.

———. “JunoGuard.” Accessed August 3, 2026. https://junoguard.com.
