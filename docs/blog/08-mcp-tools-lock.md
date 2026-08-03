# MCP tool poisoning, rug pulls, and why we hash our own tools into `tools.lock.json`.

**Series:** JunoGuard field notes  
**Citation style:** Chicago Manual of Style, 17th ed. (notes and bibliography)  
**Primary keyword:** MCP tool poisoning

---

![Figure 1. Tool metadata flows to model trust](./assets/jg-refusal-panel.png)

**Figure 1.** Tool descriptions are an instruction channel. Integrity checks start on the tools you ship. Illustration by JunoGuard.

In April 2025, Invariant Labs published research on Model Context Protocol (MCP) **tool poisoning**: malicious instructions embedded in tool metadata that models follow more readily than users ever see.[^1] The attack is not exotic. Change a tool description — or swap a server definition after approval — and you change agent behavior silently. Rug pulls on MCP configs are the operational sibling: “approved yesterday” is not “safe today.”[^2]

JunoGuard does not claim to sanitize the entire MCP ecosystem. Third-party servers you install remain your trust boundary. What we do claim is narrower and enforceable: **our** MCP surface — `guard_install`, `guard_llm`, `guard_status` — is hash-pinned in a committed `tools.lock.json`, and the server refuses to start if names, descriptions, or schemas drift from that lockfile.

That is integrity for the gate itself, not a universal antidote to poisoned tools elsewhere.

## How tool poisoning works

MCP tools carry machine-readable definitions: name, description, input schema. The model reads those fields when deciding how to invoke a tool. Invariant’s notification describes attacks where benign-looking descriptions hide instructions — exfiltrate data, ignore prior constraints, prefer a malicious package — that never appear in the user-visible UI.[^1]

Follow-on work such as MCPTox benchmarks the problem against real servers.[^3] The pattern matches what supply-chain defenders already know from README injection and `postinstall` scripts: **the instruction channel is the vulnerability**, not necessarily the compiled binary.

For coding agents, that channel is doubly sensitive. A poisoned `guard_install` description might steer the model away from calling the real guard. A poisoned *package manager* MCP shim might never touch Juno at all. MCP Manager-style runtime protections can redact or inspect traffic on some paths; they do not replace install gating on the shell the agent still has.[^4]

## Rug pulls on trusted configuration

Separate from description poisoning, configuration swap attacks target the MCP client. Cursor’s MCPoison advisory (CVE-2025-54136) describes persistent code execution via trusted MCP configuration modification — a reminder that the config file on disk is part of the attack surface.[^2]

JunoGuard’s response on **our** surface is deterministic: ship a lockfile, verify at startup, exit non-zero on mismatch (`juno mcp --verify`, exit code 78). CI checks both TypeScript and Python MCP servers against the same lock. If someone edits a tool description in `mcp.ts` or `server.py` without updating the lock, the server does not serve.

That does not stop an attacker from adding a *second* MCP server the user approved once. It stops Juno’s own tools from changing underneath a team that thought they reviewed the definitions.

## What `tools.lock.json` contains

The lockfile records SHA-256 hashes of each tool’s canonical definition — name, description, schema — plus a surface hash for the combined MCP catalog. Example structure:

```json
{
  "lock_version": 1,
  "algorithm": "sha256",
  "tools": {
    "guard_install": "c1e4d7b6…",
    "guard_llm": "2ed438b4…",
    "guard_status": "60ddfe0f…"
  },
  "surface": "b45aad9d…"
}
```

At startup, the MCP server recomputes hashes from the live definitions and compares. Mismatch → refuse to start, log clearly, no “best effort” serve with stale semantics.

This follows the same integrity instinct Invariant recommends when tool descriptions become an instruction channel: treat definitions like code, not copy.[^1] Version them. Review them. Detect drift automatically.

## What the lockfile does not do

Be explicit about the boundary:

- **Does not** scan third-party MCP servers you also run
- **Does not** prevent an agent from bypassing MCP and using `/usr/bin/npm` directly
- **Does not** replace Lane A Ossprey verdicts or Lane B spend caps
- **Does not** sanitize npm, PyPI, or registry content

MCP exposure remains **advisory** for Juno’s tools too — advisory with integrity guarantees on *our* definitions, not kernel enforcement on every process. Closing more of the gap still means forwarders (`juno npm|pnpm|yarn|pip …`), optional PATH wrap, and shell hooks from `init`. Absolute paths bypass PATH wrap. Poetry and uv are out of scope for forwarders today.

Hash-pinning is about **not becoming the poisoned guard** — not about pretending one lockfile cleans the ecosystem.

## Lane A and Lane B still do the work

Tool integrity sits beside the dual lane, not instead of it.

**Lane A** — before disk, Ossprey verdict, SBOM coordinate, flagged refuses on unattended installs. Demo block:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

**Lane B** — budgets, caps, rate limits, burst thresholds on local pricing; no LLM on the hot path for the policy decision.

When `guard_install` returns `JUNO · BLOCKED`, the model reads structured verdict and blast radius — credential names in scope, not values — and can pivot. When the tool definition itself were tampered, the server would not have started; the team discovers drift at deploy or CI time, not mid-incident.

## Operational checklist

1. Commit `tools.lock.json` beside the MCP server.
2. Run `juno mcp --verify` in CI when MCP definitions change.
3. Treat lock updates as code review — same as changing policy rules.
4. Wire agents with `npx @heysalad/junoguard init`; use `--mock` before live keys.
5. Layer forwarders and hooks for shell paths MCP never sees.
6. Do not assume third-party MCP tools inherit Juno’s lock — review them separately.

## Start here

Read Invariant’s notification for the threat model.[^1] Read JunoGuard’s product docs for the gate.[^5]

Console: [junoguard.com](https://junoguard.com).[^5]

Install:

```bash
npx @heysalad/junoguard init
```

We hash our tools because tool metadata is an instruction channel. We refuse to start on mismatch because a silent rug pull on the guard is worse than no guard at all. We will not tell you that fixes MCP everywhere — only that it fixes **our** surface honestly.

---

## Notes

[^1]: Luca Beurer-Kellner and Marc Fischer, “MCP Security Notification: Tool Poisoning Attacks,” Invariant Labs, April 2025, https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

[^2]: National Institute of Standards and Technology, “CVE-2025-54136 Detail,” National Vulnerability Database, August 1, 2025, https://nvd.nist.gov/vuln/detail/CVE-2025-54136; Cursor, “MCPoison: Persistent Code Execution via Trusted MCP Configuration Modification,” GitHub Security Advisory GHSA-24mc-g4xr-4395, 2025, https://github.com/cursor/cursor/security/advisories/GHSA-24mc-g4xr-4395.

[^3]: Zhihao Jia et al., “MCPTox: A Benchmark for Tool Poisoning Attack on Real-World MCP Servers,” arXiv, August 2025, https://arxiv.org/abs/2508.14925.

[^4]: MCP Manager, “Runtime Protections,” MCP Manager Docs, accessed August 3, 2026, https://docs.mcpmanager.ai/security/runtime-protections.

[^5]: HeySalad, “JunoGuard,” accessed August 3, 2026, https://junoguard.com; HeySalad, “@heysalad/junoguard,” npm, August 1, 2026, https://www.npmjs.com/package/@heysalad/junoguard.

---

## Bibliography

Beurer-Kellner, Luca, and Marc Fischer. “MCP Security Notification: Tool Poisoning Attacks.” Invariant Labs, April 2025. https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

Cursor. “MCPoison: Persistent Code Execution via Trusted MCP Configuration Modification.” GitHub Security Advisory GHSA-24mc-g4xr-4395, 2025. https://github.com/cursor/cursor/security/advisories/GHSA-24mc-g4xr-4395.

HeySalad. “@heysalad/junoguard.” npm, August 1, 2026. https://www.npmjs.com/package/@heysalad/junoguard.

———. “JunoGuard.” Accessed August 3, 2026. https://junoguard.com.

Jia, Zhihao, et al. “MCPTox: A Benchmark for Tool Poisoning Attack on Real-World MCP Servers.” arXiv, August 2025. https://arxiv.org/abs/2508.14925.

MCP Manager. “Runtime Protections.” MCP Manager Docs. Accessed August 3, 2026. https://docs.mcpmanager.ai/security/runtime-protections.

National Institute of Standards and Technology. “CVE-2025-54136 Detail.” National Vulnerability Database, August 1, 2025. https://nvd.nist.gov/vuln/detail/CVE-2025-54136.
