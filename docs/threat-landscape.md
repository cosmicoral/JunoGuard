# Threat Landscape

How companies actually get breached, how AI agents specifically get abused, and
which defenses have evidence behind them. Compiled 2026-08-02 from primary
sources; every claim links to one.

Two reasons this file exists. It is the threat model JunoGuard is built against,
and it is the honest map of what we cover, what we do not, and what nobody does.
The last section is the part to argue with.

---

## 1. How companies get breached

Ranked by how often it is the way in, not by how exciting it is.

### 1.1 The help desk, not the firewall

Attackers phone IT support impersonating an employee and ask for an MFA reset.
They already have the password from a prior breach dump. The help desk enrols a
device the attacker controls.

Scattered Spider is the reference actor: help-desk impersonation, push-bombing,
SIM swaps, and Evilginx AiTM phishing kits rather than malware or exploits. In
April 2025 Marks & Spencer disclosed ransomware after attackers talked its IT
help desk into resetting employee credentials.

**What stops it:** phishing-resistant MFA (nothing to phish), plus a verification
procedure for resets that does not accept voice as identity — callback on a known
number, manager attestation, or in-person.

Sources: [CISA AA23-320A](https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-320a) ·
[ReliaQuest](https://reliaquest.com/blog/scattered-spider-cyber-attacks-using-phishing-social-engineering-2025/)

### 1.2 Stolen credentials

Still the single largest initial-access category. Verizon's DBIR put stolen
credentials behind 22% of breaches in the 2025 report, down from 31% the year
before — falling, but still first.

**What stops it:** FIDO2/passkeys. Google reports 400M+ accounts on passkeys;
FIDO Alliance recorded zero phishing incidents at Mercari post-rollout; Microsoft
reports a ~99% block rate for phishing-resistant MFA. Push-based MFA is no longer
sufficient — the ShinyHunters SSO campaign bypassed it in real time.

Sources: [DBIR 2025 summary](https://www.descope.com/blog/post/dbir-2025) ·
[DBIR 2026](https://www.descope.com/blog/post/verizon-dbir-2026)

### 1.3 Software supply chain — now self-propagating

This is the category that changed shape.

**Shai-Hulud** (disclosed 15 Sept 2025) was the first true worm in the npm
ecosystem. Mechanism: phishing aimed at maintainers spoofing npm MFA updates →
steal npm token → authenticate as the maintainer → inject into every other
package they maintain → publish. It spread exponentially with no operator, poisoned
500+ packages including `@ctrl/tinycolor`, harvested cloud tokens, and ran secret
scanners on infected machines. A significantly evolved V2 landed 24 Nov 2025.

The important property: **the payload runs at install time, on a developer or CI
machine, with that machine's credentials.** No exploit, no CVE. You typed
`npm install`.

Related, same family: typosquatting, dependency confusion, compromised maintainer
accounts, CI/CD poisoning, and the `xz-utils` class of long-game maintainer
infiltration.

Sources: [CISA alert](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem) ·
[Unit 42](https://unit42.paloaltonetworks.com/npm-supply-chain-attack/) ·
[Microsoft on Shai-Hulud 2.0](https://www.microsoft.com/en-us/security/blog/2025/12/09/shai-hulud-2-0-guidance-for-detecting-investigating-and-defending-against-the-supply-chain-attack/)

### 1.4 Cloud, SaaS and identity

OAuth token abuse, over-permissive IAM, SaaS-to-SaaS integration abuse, session
and token theft. The pattern: attackers stop trying to break authentication and
start stealing the thing issued *after* authentication.

**What stops it:** short-lived credentials over static keys, workload identity
instead of long-lived API keys, and scoping tokens to one job.

---

## 2. How AI agents get abused

### 2.1 Prompt injection, and why it is not fixed

An LLM has no boundary between code and data. Everything in the context window is
tokens, processed identically. Content the agent *reads* is therefore
indistinguishable from instructions the user *gave*.

**Filtering does not solve it.** Blocklisting "ignore previous instructions" fails
because the same instruction can be given in French, in base64, in a synonym, or
in a paraphrase nobody enumerated. Willison's framing is the one to internalise:
in application security 99% is a failing grade, because the attacker's whole job
is to find the 1%. We would never accept a 99% XSS filter.

Sources: [OWASP LLM Prompt Injection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) ·
[The Register / Willison](https://www.theregister.com/2023/04/26/simon_willison_prompt_injection/)

### 2.2 The lethal trifecta

Willison's model, and the most useful single idea in agent security. Risk becomes
severe when an agent has all three:

1. **Access to private data** — repos, email, customer records, `.env` files
2. **Exposure to untrusted content** — web pages, issues, PR descriptions, docs, package code
3. **A way to communicate externally** — HTTP, email, tool side effects

Any two are survivable. All three is an exfiltration primitive. **Removing any one
leg is worth more than any amount of prompt hardening**, and that is a design
decision, not a filter.

Source: [The lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)

### 2.3 AI coding tools are the current soft target

This is not theoretical and it is where JunoGuard lives.

- **IDEsaster** (Dec 2025): 24+ CVEs across every major AI IDE. Includes
  **CVE-2025-59536** — RCE via a `.claude/settings.json` file committed to a repo.
- **CVE-2025-53773** (CVSS 9.6): hidden prompt injection in a *pull request
  description* achieving RCE through GitHub Copilot.
- Config-file-write escalation: **CVE-2025-64660** (Copilot),
  **CVE-2025-61590** (Cursor), **CVE-2025-58372** (Roo Code) — injection edits
  workspace config to enable execution without approval.
- Mindgard catalogued 22 repeatable attack patterns across Cursor, Copilot, Kiro,
  Amazon Q, Antigravity, Jules, Windsurf, Cline, Claude Code, Codex, Devin.

The one-line summary: **the attack surface is every file the agent reads that you
did not write.**

Sources: [The Hacker News — 30+ flaws](https://thehackernews.com/2025/12/researchers-uncover-30-flaws-in-ai.html) ·
[Microsoft — when prompts become shells](https://www.microsoft.com/en-us/security/blog/2026/05/07/prompts-become-shells-rce-vulnerabilities-ai-agent-frameworks/) ·
[Cycode](https://cycode.com/blog/ai-security-vulnerabilities/)

### 2.4 MCP-specific attacks

- **Tool poisoning** — malicious instructions inside a tool *description*, which
  the model reads as guidance. The user never sees it.
- **Rug pull** — a server is approved while benign, then redefines its tools.
  Approval was granted to the old definition and silently inherits to the new one.
  Most clients show the initial description and never alert on change.
- **Cross-server shadowing** — one server's tool description influences how the
  agent uses another's.
- **Schema tampering / malicious dependency updates** in the server itself.

Proposed mitigation with real teeth: **ETDI** — bind tool definitions to signed
JWTs and express permissions as OAuth 2.0 scopes, so a redefinition breaks the
signature.

Sources: [Willison on MCP injection](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/) ·
[CSA Agentic MCP best practices](https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1/) ·
[Checkmarx](https://checkmarx.com/zero-post/11-emerging-ai-security-risks-with-mcp-model-context-protocol/)

### 2.5 Excessive agency

OWASP LLM's own framing: too many tools, too many permissions, no approval gate.
Mitigation is least-privilege tooling, human approval for high-risk actions, rate
limiting, and provenance checks — **governance and architecture, not prompting.**

Source: [OWASP Top 10 for LLM Applications 2025](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)

---

## 3. Defenses that actually work

Ranked by return on effort for a 1–5 person startup. Everything in tier 1 is
doable this week.

### Tier 1 — do these first

| Control | Stops | Effort |
|---|---|---|
| **Passkeys / FIDO2 everywhere** | 1.1, 1.2. ~99% block rate; zero phishing at Mercari | Hours |
| **`npm ci --ignore-scripts`** | Shai-Hulud's entire mechanism. Lifecycle scripts are the payload | Minutes |
| **Lockfiles + `--require-hashes`** | Dependency substitution, unreviewed transitive drift | Hours |
| **Short-lived credentials, no static keys** | 1.4, and limits what a stolen token buys | Days |
| **Secret scanning in CI + push protection** | Committed credentials, the most common own-goal | Hours |
| **Help-desk reset procedure that is not voice-based** | 1.1 | A written page |
| **Remove one leg of the lethal trifecta from every agent** | 2.1, 2.2 | Design review |

### Tier 2 — next

- **SLSA Level 2** — achievable on GitHub Actions in a day or two, and the
  standard advice is that most orgs should target it near-term. Level 3 for
  critical components. ([Trail of Bits](https://blog.trailofbits.com/2024/10/01/securing-the-software-supply-chain-with-the-slsa-framework/),
  [SLSA](https://slsa.dev/blog/2023/05/bringing-improved-supply-chain-security-to-the-nodejs-ecosystem))
- **npm provenance + `npm audit signatures`** — Sigstore-backed, keyless, logged
  in a public transparency ledger, built into the npm CLI. ([Sigstore](https://blog.sigstore.dev/npm-provenance-ga/))
- **Egress blocking by default** in build and agent environments — kills the third
  leg of the trifecta and most exfiltration.
- **Honeytokens / canary credentials** — cheap, and they detect the case where
  everything else already failed.
- **Deterministic policy gates outside the model** — see below.

### Tier 3 — architecture, when agents hold real permissions

- **Dual LLM / quarantined LLM** — a privileged model holds the tools and never
  reads untrusted content; a quarantined model reads untrusted content and holds
  no tools. Only structured summaries cross. Breaks the path from injected text to
  action. Reduces risk substantially; does not eliminate it.
- **CaMeL** — the same split plus explicit *capabilities* enforced by a custom
  interpreter, so data flow and policy are checked outside the model. The most
  promising direction currently published.

Sources: [Willison on CaMeL](https://simonwillison.net/2025/Apr/11/camel/) ·
[lethal trifecta pattern](https://github.com/nibzard/awesome-agentic-patterns/blob/main/patterns/lethal-trifecta-threat-model.md)

### Theatre — do not buy

- **Classifier-based prompt-injection filters as a primary control.** Infinite
  linguistic variation, and 99% is failing. Fine as telemetry, negligent as a gate.
- **System-prompt hardening as a security boundary.** Injected content enters the
  same context stream as the instruction telling it not to obey.
- **SBOMs generated and never read.** An artifact nobody queries is compliance,
  not security. The value is in gating on it.

---

## 4. Where JunoGuard actually sits

Honest map. Compare against README's capability table and keep both true.

**What we cover today**

| Threat | How |
|---|---|
| Malicious package install by an agent (§1.3) | Lane A: Ossprey verdict *before* the install lands; blocks on `malicious`, and on `unavailable` — an outage is never read as "probably fine" |
| Lifecycle-script payloads — Shai-Hulud's mechanism | Guarded installs add `--ignore-scripts` by default |
| Excessive agency (§2.5) | Deterministic gate outside the model. Token, per-request and daily budget caps; burst limits; kill switch with operator roles and audit |
| Unreviewable agent behaviour | Every decision is an audit record with an accountable actor |
| Blast radius of a bad install | Names-only credential scope, enriched with scanner and sandbox evidence |
| Post-hoc evidence | Modal detonation in a network-blocked sandbox; report lands on the action and its incident, and can retroactively block |

The structural bet worth stating plainly: **we are a deterministic policy gate
outside the model.** That is the same architectural claim as tier 3 above, applied
to the one action an agent takes that runs arbitrary code on your machine.

**What we do not cover — say so when asked**

- **Prompt injection itself.** We do not stop an agent being convinced. We
  constrain what it can *do* once convinced. Different, and honest.
- **Non-shell escapes.** Absolute paths and non-Cursor agents remain outside the
  shell hook. Already flagged as `planned` in README.
- **The IDE CVE class (§2.3).** `.claude/settings.json` RCE is the IDE's trust
  boundary, not ours.
- **MCP tool poisoning / rug pull (§2.4).** We *are* an MCP surface. We do not
  currently verify our own tool-definition integrity. **This is the most credible
  gap in the product.**
- **Identity and help desk (§1.1, §1.2).** Out of scope, and should stay out.

**Roadmap candidates, in the order the threat model justifies**

1. Tool-definition integrity for our MCP surface — signed definitions, alert on
   change. Directly answers §2.4, and we sell agent security.
2. Egress policy for guarded installs — take the third trifecta leg, not just the
   package verdict.
3. `npm audit signatures` / provenance checking as a verdict input — free signal,
   already in the npm CLI.
4. Detonation on the hot path for the flagged-and-proceeded case.

---

## 5. Our own launch checklist

We ship developer security tooling. Being compromised is an existential brand
event, not an incident.

- [x] Secret scanning + GitHub push protection on
- [x] Hashed dependency lock, `--require-hashes` in the image
- [x] Gateway runs as non-root, no Docker socket, untrusted code never in-process
- [x] Service-role key server-side only; never in a `VITE_` variable
- [x] Production refuses to look ready on degraded infrastructure (`/ready`)
- [x] Scanner outage fails closed
- [x] Detonation callbacks bearer-authenticated, size-capped, schema-reduced
- [ ] **Passkeys on GitHub, npm, Vercel, Supabase, Modal, OpenAI** — do this tonight
- [ ] **npm publish with provenance + 2FA on the npm org** — we ship a package; we
      are a supply-chain target ourselves
- [ ] Rotate the operator token and stream secret post-launch
- [ ] Honeytoken in the demo project so we learn if it is ever scraped

The second unchecked item is the one that matters. Shai-Hulud spread by
compromising maintainers of packages exactly like ours.
