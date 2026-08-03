# Keep the agent productive without risking credentials, runaway spend, or an unrecoverable afternoon.

**Series:** JunoGuard field notes  
**Citation style:** Chicago Manual of Style, 17th ed. (notes and bibliography)  
**Primary keyword:** AI coding agent productivity

---

![Figure 1. Blast radius of an unguarded coding agent](./assets/jg-blast-radius.png)

**Figure 1.** The job is not to stop the agent. It is to keep shipping while the blast radius stays bounded. Illustration by JunoGuard.

The job is not to stop the agent. The job is to keep shipping.

That sentence sounds obvious until you watch what most “AI security” products optimize for. They optimize for alerts, dashboards, and quarterly compliance language. A founder or staff engineer optimizing for throughput needs something else: continuity. The model should finish the refactor. The dependency install should not become a credential exfiltration event. The afternoon should not disappear into incident response because nobody measured what the agent could reach.

This post is about that job — stated as a job to be done, not as a threat model lecture.

## The job, in one sentence

Keep the agent productive without risking credentials, runaway spend, or an unrecoverable afternoon.

Notice what is missing. There is no mention of CVE counts, SOC2 checkboxes, or “AI governance.” Those may matter elsewhere. Here the unit of value is a shipped feature, a contained bill, and secrets that stay secret. Security is the means. Throughput with bounded downside is the end.

## What “productive” actually means

Productive does not mean “unrestricted.” It means the agent can attempt the work, receive a legible answer when something is wrong, and choose a different path without thrashing.

Cursor, Claude Code, and Codex are useful because they loop: read context, call tools, install packages, edit files, retry until the diff looks plausible. That loop is the product. Interrupt it badly — opaque errors, silent allows, or alerts that arrive after the damage — and you have not improved security. You have reduced throughput.

The useful interrupt sits between “the model decided to install” and “code executed with your ambient authority.” Public reporting on npm supply-chain campaigns and on malware that targets assistant configuration paths treats that moment as part of the software supply chain now, not a future concern.[^1] Your agent’s trust surface is already in scope.

## Blast radius is the variable you manage

![Figure 2. Dual-lane control plane](./assets/jg-dual-lane.png)

**Figure 2.** Two lanes, one question: should this proceed? Lane A gates installs; Lane B gates spend. Illustration by JunoGuard.

Blast radius is the set of things that become reachable if a bad action succeeds: credential names in scope, network egress, write access to the open repository, and the model budget that funds the next hundred retries. Most setups never compute that set until after something goes wrong.

JunoGuard exists to answer one question on every action: should this proceed?

**Lane A — supply chain.** Before a package reaches disk, Juno asks for a malware verdict via Ossprey.[^2] No verdict means no install. Flagged packages do not proceed on unattended paths without an audited override. Registry-backed CycloneDX metadata captures the exact coordinate. Optional sandbox detonation can add behavioral evidence on a cold path after the response — enrichment for the record, not a time machine for an install that already happened.[^3]

**Lane B — LLM spend.** Budgets, per-request caps, rate limits, and burst detection run on local pricing and accounting. There is no model call on the hot path for the decision itself. Hijacked agents often reveal themselves as abnormal token burn; treating that as telemetry is more honest than calling it a billing nicety. Products such as LiteLLM expose virtual keys and spend caps for model gateways; JunoGuard applies that class of control beside install policy for coding agents, not instead of it.[^4]

Both lanes share policy, incidents, and a kill switch operated by an accountable operator. Allows stay quiet. Flags require a named override when the install is unattended. Scanner outages refuse; they do not silently become allows.

## Why alerts alone fail the job

If you only buy CVE scanning, you miss novel malware with no advisory yet. If you only buy an LLM gateway with virtual keys, you still let the agent `npm install` whatever a poisoned instruction requested. If you only buy an MCP traffic gateway, you may redact tool arguments while the shell still runs an ungated package manager.[^5]

Those products are real and often necessary. The gap is the coding-agent interrupt — the moment the model’s plan becomes shell execution with your credentials.

Research on MCP tool poisoning and configuration swap advisories show the agent’s trust surface is now part of the supply chain — not a future concern.[^6][^7] Alerts that arrive after the package is on disk do not preserve the afternoon. They document its loss.

## What good looks like for the agent

Blocking is table stakes. The useful part is making the refusal legible to the agent so it self-corrects instead of retrying.

In mock mode you can see the shape without a gateway:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

A live block is not a thrown tool error. Errors invite retries. A structured refusal with verdict, reason, and blast radius invites a different dependency. The model reads “Ossprey verdict: malicious” and “credentials in scope: OPENAI_API_KEY, SUPABASE_SERVICE_ROLE_KEY” — names, not values — and can pivot without burning another hour on the same coordinate.

That is productivity with guardrails, not productivity despite them.

## Honest limits (because trust requires them)

MCP tool exposure is **advisory**: it works when the agent calls the tool. It is not a kernel boundary. Closing more of the gap means using the CLI forwarders (`juno npm|pnpm|yarn|pip …`), optional PATH wrap (`juno wrap on`), and the Cursor / Claude Code shell hooks that `init` can write. Absolute paths to the real package manager still bypass the wrap. JunoGuard does not claim poetry or uv gating. It does not claim anomaly-detection machine learning. Modal cold-path detonation is evidence infrastructure, not a time machine.

If a vendor cannot say those sentences out loud, they are selling comfort, not control.

## Start here

Read the product and console at [junoguard.com](https://junoguard.com).[^8]

Wire the client into the agents on your machine:

```bash
npx @heysalad/junoguard init
```

Use `JUNO_MOCK=1` when you want the refusal UX without credentials. For live policy you will need a gateway and a project key you chose — not one we embedded for you.[^9]

The blast radius was always there. The new part is measuring it before the afternoon is gone — and keeping the agent shipping while you do.

---

## Notes

[^1]: Cybersecurity and Infrastructure Security Agency, “Widespread Supply Chain Compromise Impacting npm Ecosystem,” CISA Alert, September 23, 2025, https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem; Cloud Security Alliance, “Miasma and IronWorm: AI Coding Supply Chain,” CSA Labs Research Note, June 2026, https://labs.cloudsecurityalliance.org/research/csa-research-note-miasma-ironworm-ai-coding-supply-chain-202/.

[^2]: Ossprey Security, “Malicious Code Detection for Open Source,” Ossprey, accessed August 3, 2026, https://www.ossprey.com/.

[^3]: Modal Labs, “Sandboxes,” Modal Docs, accessed August 3, 2026, https://modal.com/docs/guide/sandboxes.

[^4]: BerriAI, “Virtual Keys,” LiteLLM Docs, accessed August 3, 2026, https://docs.litellm.ai/docs/proxy/virtual_keys.

[^5]: MCP Manager, “Runtime Protections,” MCP Manager Docs, accessed August 3, 2026, https://docs.mcpmanager.ai/security/runtime-protections; Socket, “Socket vs Snyk,” Socket.dev, accessed August 3, 2026, https://socket.dev/compare/socket-vs-snyk.

[^6]: Luca Beurer-Kellner and Marc Fischer, “MCP Security Notification: Tool Poisoning Attacks,” Invariant Labs, April 2025, https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

[^7]: National Institute of Standards and Technology, “CVE-2025-54136 Detail,” National Vulnerability Database, August 1, 2025, https://nvd.nist.gov/vuln/detail/CVE-2025-54136; Cursor, “MCPoison: Persistent Code Execution via Trusted MCP Configuration Modification,” GitHub Security Advisory GHSA-24mc-g4xr-4395, 2025, https://github.com/cursor/cursor/security/advisories/GHSA-24mc-g4xr-4395.

[^8]: HeySalad, “JunoGuard,” accessed August 3, 2026, https://junoguard.com.

[^9]: HeySalad, “@heysalad/junoguard,” npm, August 1, 2026, https://www.npmjs.com/package/@heysalad/junoguard.

---

## Bibliography

Beurer-Kellner, Luca, and Marc Fischer. “MCP Security Notification: Tool Poisoning Attacks.” Invariant Labs, April 2025. https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

BerriAI. “Virtual Keys.” LiteLLM Docs. Accessed August 3, 2026. https://docs.litellm.ai/docs/proxy/virtual_keys.

Cloud Security Alliance. “Miasma and IronWorm: AI Coding Supply Chain.” CSA Labs Research Note, June 2026. https://labs.cloudsecurityalliance.org/research/csa-research-note-miasma-ironworm-ai-coding-supply-chain-202/.

Cursor. “MCPoison: Persistent Code Execution via Trusted MCP Configuration Modification.” GitHub Security Advisory GHSA-24mc-g4xr-4395, 2025. https://github.com/cursor/cursor/security/advisories/GHSA-24mc-g4xr-4395.

Cybersecurity and Infrastructure Security Agency. “Widespread Supply Chain Compromise Impacting npm Ecosystem.” CISA Alert, September 23, 2025. https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem.

HeySalad. “@heysalad/junoguard.” npm, August 1, 2026. https://www.npmjs.com/package/@heysalad/junoguard.

———. “JunoGuard.” Accessed August 3, 2026. https://junoguard.com.

MCP Manager. “Runtime Protections.” MCP Manager Docs. Accessed August 3, 2026. https://docs.mcpmanager.ai/security/runtime-protections.

Modal Labs. “Sandboxes.” Modal Docs. Accessed August 3, 2026. https://modal.com/docs/guide/sandboxes.

National Institute of Standards and Technology. “CVE-2025-54136 Detail.” National Vulnerability Database, August 1, 2025. https://nvd.nist.gov/vuln/detail/CVE-2025-54136.

Ossprey Security. “Malicious Code Detection for Open Source.” Ossprey. Accessed August 3, 2026. https://www.ossprey.com/.

Socket. “Socket vs Snyk.” Socket.dev. Accessed August 3, 2026. https://socket.dev/compare/socket-vs-snyk.
