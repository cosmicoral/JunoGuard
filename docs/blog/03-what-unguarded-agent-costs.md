# Credentials, token bills, and lost afternoons — what an unguarded agent actually costs.

**Series:** JunoGuard field notes  
**Citation style:** Chicago Manual of Style, 17th ed. (notes and bibliography)  
**Primary keyword:** AI coding agent cost

---

![Figure 1. Blast radius of an unguarded coding agent](./assets/jg-blast-radius.png)

**Figure 1.** Three currencies an unguarded agent spends: secrets, dollars, and hours. Illustration by JunoGuard.

Security vendors love invented ROI percentages. This post will not give you one. What an unguarded coding agent costs is simpler and more painful: credentials that leave with a package, token bills that spike before anyone opens the dashboard, and afternoons that disappear into incident response instead of shipping.

Those are three separate losses. They compound. And they do not require a sophisticated exploit — only an install, a loop, and a machine that trusts registries by default.

## Currency one: secrets

An AI coding agent runs with ambient authority. Environment variables for API keys, cloud profiles, database URLs — the names are often visible to the process even when values are not printed in chat. A malicious `postinstall` script does not need to trick you. It needs to trick the model into installing it, then read what the shell already has.

Public reporting on npm supply-chain worms and on malware that plants persistence into assistant configuration paths treats the coding assistant as both target and carrier.[^1] Research on Model Context Protocol (MCP) tool poisoning shows how malicious instructions hide in tool metadata that models trust more readily than users see.[^2] The 2018 `event-stream` compromise demonstrated install-time trust abuse without a conventional CVE.[^3]

The cost of a leaked `OPENAI_API_KEY` or `SUPABASE_SERVICE_ROLE_KEY` is not abstract. It is rotation, audit, customer notification if data was reachable, and the quiet knowledge that the agent you trusted to speed up development became the exfiltration path. JunoGuard’s blast-radius reporting declares credential *names* in scope — never secret values — so a refusal tells the agent what would have been exposed, not what was already sent.

## Currency two: runaway spend

Hijacked agents do not always steal keys first. Sometimes they burn budget. A model loop that retries a failing install, a poisoned prompt that requests enormous completions, or a compromised workflow that hammers an endpoint can produce a bill before a human checks the provider dashboard.

Products such as LiteLLM expose virtual keys and spend caps for model gateways.[^4] That class of control matters. JunoGuard’s Lane B applies budgets, per-request caps, rate limits, and burst detection beside install policy — using local pricing and accounting, with no LLM call on the hot path for the decision itself. The point is not to optimize pennies. The point is to keep a bad afternoon from becoming a bad invoice.

![Figure 2. Dual-lane control plane with spend lane callout](./assets/jg-dual-lane.png)

**Figure 2.** Lane B gates LLM spend with the same allow / flag / block vocabulary as Lane A. Illustration by JunoGuard.

When spend crosses a threshold, the response should be deterministic: block, flag for review, or allow — not “we’ll email you next week.”

## Currency three: lost afternoons

The third cost is time — and it is the one founders feel first.

You did not adopt Cursor or Claude Code to open a Jira ticket about a dependency. You adopted them to merge a PR. When a bad install succeeds, the afternoon’s job changes: clone forensics, grep logs, revoke keys, explain to the team why CI secrets need rotating, write the postmortem nobody wanted to write.

Software composition analysis and CVE scanners often report after the package is on disk. Provider dashboards show spend after the requests. The agent, meanwhile, has already moved on to the next step. The cost is not only the direct damage. It is the opportunity cost of the feature that did not ship.

JunoGuard’s job is to interrupt *before* that pivot — with a refusal the agent can read and act on, not a thrown error that invites another retry.

## What prevention looks like (without fantasy math)

Every action answers one question: should this proceed?

**Lane A — supply chain.** Before a package reaches disk, Juno asks for a malware verdict via Ossprey.[^5] No verdict means no install. Flagged packages do not proceed on unattended paths without an audited override. Registry-backed CycloneDX metadata captures the exact coordinate.

**Lane B — tokens and cost.** Budgets, caps, rate limits, burst detection — deterministic, local, no model judging the model on the hot path.

Both lanes share policy, incidents, and a kill switch. Allows stay quiet. Flags require a named override when the install is unattended. Scanner outages refuse; they do not silently become allows.

You can see the refusal shape without live credentials:

```bash
JUNO_MOCK=1 npx @heysalad/junoguard scan @ossprey/test-package
```

The mock fixture returns a block with Ossprey verdict, findings, and blast radius — the same UX the agent would see live. That is how you evaluate whether the interrupt saves an afternoon before you wire production keys.

## What we will not claim

We will not quote a “97% reduction in incidents” we cannot reproduce. We will not promise poetry or uv gating — JunoGuard forwarders cover npm, pnpm, yarn, and pip only. We will not claim MCP exposure is a kernel boundary; it is advisory. PATH wrap helps until someone invokes an absolute path to the real binary. Modal cold-path detonation enriches evidence after the response; it does not rewrite an install that already happened.[^6]

Honest limits do not reduce value. They tell you where to add compensating controls — hooks, forwarders, operator review — instead of buying comfort.

## The invoice, restated

An unguarded agent can cost you secrets, spend, and time. JunoGuard exists to put a deterministic gate between the agent and that blast radius — not another chatty “AI security agent,” but a control plane that refuses clearly, logs why, and lets the model choose a different path.

Read the product and console at [junoguard.com](https://junoguard.com).[^7]

Wire the client:

```bash
npx @heysalad/junoguard init
```

Use `JUNO_MOCK=1` to prove the UX without credentials. For live policy, bring a gateway and a `JUNO_PROJECT_KEY` you chose — not one we embedded for you.[^8]

The afternoon was always at risk. The new part is measuring the cost before it is gone.

---

## Notes

[^1]: Cybersecurity and Infrastructure Security Agency, “Widespread Supply Chain Compromise Impacting npm Ecosystem,” CISA Alert, September 23, 2025, https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem; Microsoft Security, “Shai-Hulud 2.0: Guidance for Detecting, Investigating, and Defending against the Supply Chain Attack,” December 9, 2025, https://www.microsoft.com/en-us/security/blog/2025/12/09/shai-hulud-2-0-guidance-for-detecting-investigating-and-defending-against-the-supply-chain-attack/; Cloud Security Alliance, “TrapDoor: Multi-Ecosystem Supply Chain AI Targeting,” CSA Labs Research Note, 2026, https://labs.cloudsecurityalliance.org/research/csa-research-note-trapdoor-multi-ecosystem-supply-chain-ai-t/.

[^2]: Beurer-Kellner and Fischer, “MCP Security Notification.”

[^3]: npm, Inc., “Details about the event-stream Incident.”

[^4]: BerriAI, “Virtual Keys,” LiteLLM Docs, accessed August 3, 2026, https://docs.litellm.ai/docs/proxy/virtual_keys.

[^5]: Ossprey Security, “Malicious Code Detection for Open Source,” Ossprey, accessed August 3, 2026, https://www.ossprey.com/.

[^6]: Modal Labs, “Sandboxes,” Modal Docs, accessed August 3, 2026, https://modal.com/docs/guide/sandboxes.

[^7]: HeySalad, “JunoGuard,” accessed August 3, 2026, https://junoguard.com.

[^8]: HeySalad, “@heysalad/junoguard,” npm, August 1, 2026, https://www.npmjs.com/package/@heysalad/junoguard.

---

## Bibliography

Beurer-Kellner, Luca, and Marc Fischer. “MCP Security Notification: Tool Poisoning Attacks.” Invariant Labs, April 2025. https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks.

BerriAI. “Virtual Keys.” LiteLLM Docs. Accessed August 3, 2026. https://docs.litellm.ai/docs/proxy/virtual_keys.

Cloud Security Alliance. “TrapDoor: Multi-Ecosystem Supply Chain AI Targeting.” CSA Labs Research Note, 2026. https://labs.cloudsecurityalliance.org/research/csa-research-note-trapdoor-multi-ecosystem-supply-chain-ai-t/.

Cybersecurity and Infrastructure Security Agency. “Widespread Supply Chain Compromise Impacting npm Ecosystem.” CISA Alert, September 23, 2025. https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem.

HeySalad. “@heysalad/junoguard.” npm, August 1, 2026. https://www.npmjs.com/package/@heysalad/junoguard.

———. “JunoGuard.” Accessed August 3, 2026. https://junoguard.com.

Microsoft Security. “Shai-Hulud 2.0: Guidance for Detecting, Investigating, and Defending against the Supply Chain Attack.” December 9, 2025. https://www.microsoft.com/en-us/security/blog/2025/12/09/shai-hulud-2-0-guidance-for-detecting-investigating-and-defending-against-the-supply-chain-attack/.

Modal Labs. “Sandboxes.” Modal Docs. Accessed August 3, 2026. https://modal.com/docs/guide/sandboxes.

npm, Inc. “Details about the event-stream Incident.” npm Blog, November 26, 2018. Archived at https://web.archive.org/web/20191031163820/https:/blog.npmjs.org/post/180565383195/details-about-the-event-stream-incident.

Ossprey Security. “Malicious Code Detection for Open Source.” Ossprey. Accessed August 3, 2026. https://www.ossprey.com/.
