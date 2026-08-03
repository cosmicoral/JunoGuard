# No LLM on the hot path: why JunoGuard won’t spend tokens to protect tokens.

**Series:** JunoGuard field notes  
**Citation style:** Chicago Manual of Style, 17th ed. (notes and bibliography)  
**Primary keyword:** deterministic agent policy

---

![Figure 1. Dual-lane control plane with zero LLM on decision node](./assets/jg-dual-lane.png)

**Figure 1.** The decision node is deterministic. No model judges the model on the hot path. Illustration by JunoGuard.

A product that uses an LLM to decide whether an LLM call is safe has a punchline problem: who guards the guard? Latency compounds. Cost compounds. And the same class of prompt injection that poisoned the original request can poison the safety check — especially when that check is itself an LLM reading untrusted content.

JunoGuard’s core principle is literal, not sloganeering: **no LLM on the hot path.** Every allow, flag, and block is computed by deterministic rules. Lane A uses the Ossprey verdict already in hand. Lane B uses local pricing, budgets, caps, rate limits, and burst thresholds. The decision engine does not call a model to judge the model.[^1]

## What “hot path” means here

Hot path is the synchronous decision between “the agent requested an action” and “the action proceeds or refuses.” For installs, that is before the package reaches disk. For model calls, that is before the upstream API key is used.

Cold path is everything that can happen **after** the client receives a response: Modal sandbox detonation, feed enrichment, operator review queues. Cold-path work adds evidence; it does not substitute for a deterministic gate.[^2]

If your safety architecture needs a model to interpret every install manifest, you have traded one probabilistic layer for another — and billed for both.

## Lane A: verdict in, decision out

Before a package reaches disk, Juno asks Ossprey for a malware verdict. Severity maps to policy: malicious blocks, unknown or suspicious may flag, clean allows — with unattended installs refusing flags unless an operator override exists. No verdict means no install; scanner outage refuses.[^3]

Registry-backed CycloneDX metadata captures the coordinate. Optional sandbox adds behavioral evidence on the cold path. None of that requires an LLM to read the tarball description and “use judgment.”

The mock fixture makes this visible offline:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

Same vocabulary live or mock — because the engine is rule tables and verdict fields, not a summarization call.

## Lane B: local math, not model arbitration

Lane B gates LLM spend: daily budgets, per-request output caps, rate limits, burst detection. Pricing comes from local tables aligned to provider rates — the same class of control virtual-key gateways expose, applied beside install policy for coding agents.[^4]

When a request exceeds a cap, the block reason cites the cap. When spend spikes relative to baseline, burst logic flags or blocks — threshold telemetry, not “anomaly ML” we do not ship. Hijacked agents often reveal themselves as abnormal token burn; treating that as a deterministic signal is more honest than pretending a second model will intuit intent.

Lane B’s **`guard_llm`** MCP tool proxies the call when allowed — the model still runs for the user’s task. The **policy check** that precedes it does not.

## Why we reject “AI security agent” framing

An “AI security agent” that reads every tool call and renders a natural-language risk score sounds sophisticated in a demo. In production it adds:

- **Latency** on every install and completion
- **Cost** — spending tokens to protect tokens
- **Attack surface** — another model reading attacker-controlled strings

Deterministic policy is the product. The refusal panel is structured data — verdict, reason, blast radius — so the **user’s** agent can self-correct without Juno running a second opinion model on the critical path.

Research on MCP tool poisoning shows models overweight tool metadata relative to what users see.[^5] Adding another LLM that also reads tool output does not remove that bias; it stacks it. Integrity controls on the tools you ship — hash-pinned definitions in `tools.lock.json`, server refuses to start on mismatch — address a different layer: whether *your* MCP surface changed since approval.[^5]

## Fail closed without fantasy intelligence

Clients require `JUNO_PROJECT_KEY` and fail closed without it. No default key. Mock mode (`JUNO_MOCK=1`) exercises the same decision paths without network.[^6]

Scanner down? Refuse — do not ask a model to guess whether the package is probably fine. Flagged on an unattended install? Refuse until override — do not ask a model to infer developer intent.

That is less narratively exciting than “our AI copilot for AI copilots.” It is more auditable. You can read the rule tables. You can replay a decision from logged inputs. You can explain to an auditor why `@ossprey/test-package` blocked without citing model vibes.

## Honest limits still apply

Deterministic policy does not mean total coverage. MCP is advisory. PATH wrap is bypassable via absolute paths. Forwarders cover npm, pnpm, yarn, and pip — not poetry or uv. Modal cold-path sandbox enriches evidence; it does not rewrite history.[^2]

No LLM on the hot path is a design choice within those boundaries — not a claim that every possible agent action is gated.

## The principle, restated

JunoGuard will not spend tokens to protect tokens. Deterministic policy is the product. Lane A consumes Ossprey verdicts. Lane B consumes counters and price tables. The agent you already pay for does the reasoning; Juno does the interrupt.

Read more at [junoguard.com](https://junoguard.com).[^6]

Wire it:

```bash
npx @heysalad/junoguard init
```

Prove refusal UX with mock first. Go live when you have a key you chose.

---

## Notes

[^1]: HeySalad, “JunoGuard,” accessed August 3, 2026, https://junoguard.com.

[^2]: Modal Labs, “Sandboxes,” Modal Docs, accessed August 3, 2026, https://modal.com/docs/guide/sandboxes.

[^3]: Ossprey Security, “Malicious Code Detection for Open Source,” Ossprey, accessed August 3, 2026, https://www.ossprey.com/.

[^4]: BerriAI, “Virtual Keys,” LiteLLM Docs, accessed August 3, 2026, https://docs.litellm.ai/docs/proxy/virtual_keys.

[^5]: Luca Beurer-Kellner and Marc Fischer, “MCP Security Notification: Tool Poisoning Attacks,” Invariant Labs, April 2025, https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

[^6]: HeySalad, “@heysalad/junoguard,” npm, August 1, 2026, https://www.npmjs.com/package/@heysalad/junoguard.

---

## Bibliography

Beurer-Kellner, Luca, and Marc Fischer. “MCP Security Notification: Tool Poisoning Attacks.” Invariant Labs, April 2025. https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

BerriAI. “Virtual Keys.” LiteLLM Docs. Accessed August 3, 2026. https://docs.litellm.ai/docs/proxy/virtual_keys.

HeySalad. “@heysalad/junoguard.” npm, August 1, 2026. https://www.npmjs.com/package/@heysalad/junoguard.

———. “JunoGuard.” Accessed August 3, 2026. https://junoguard.com.

Modal Labs. “Sandboxes.” Modal Docs. Accessed August 3, 2026. https://modal.com/docs/guide/sandboxes.

Ossprey Security. “Malicious Code Detection for Open Source.” Ossprey. Accessed August 3, 2026. https://www.ossprey.com/.
