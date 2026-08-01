import { motion, useReducedMotion } from "motion/react";

const decisions = [
  { time: "10:41:08", lane: "PKG", target: "@scope/telemetry-kit", verdict: "BLOCK", tone: "block" },
  { time: "10:41:05", lane: "LLM", target: "claude-sonnet · 4.2k", verdict: "ALLOW", tone: "allow" },
  { time: "10:40:59", lane: "PKG", target: "fastapi@0.115.0", verdict: "ALLOW", tone: "allow" },
  { time: "10:40:53", lane: "LLM", target: "gpt-5 · burst detected", verdict: "FLAG", tone: "flag" },
];

function BrandMark() {
  return (
    <span className="landing-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

function DecisionConsole() {
  return (
    <div className="decision-console" aria-label="Example JunoGuard decision console">
      <div className="console-bar">
        <div className="console-project">
          <BrandMark />
          <span>PROJECT / TOKEN-GUARD</span>
        </div>
        <span className="console-live"><i />GATE ACTIVE</span>
      </div>
      <div className="console-metrics">
        <div><span>REQUESTS GATED</span><strong>12,842</strong></div>
        <div><span>SPEND TODAY</span><strong>$18.42</strong></div>
        <div><span>BLOCKED</span><strong className="red">27</strong></div>
      </div>
      <div className="console-feed-head">
        <span>LIVE DECISIONS</span>
        <span>POLICY / STRICT</span>
      </div>
      <div className="console-feed">
        {decisions.map((decision) => (
          <div className="console-row" key={`${decision.time}-${decision.target}`}>
            <time>{decision.time}</time>
            <span className="console-lane">{decision.lane}</span>
            <span className="console-target">{decision.target}</span>
            <strong data-tone={decision.tone}>{decision.verdict}</strong>
          </div>
        ))}
      </div>
      <div className="blast-preview">
        <span>BLAST RADIUS / INTERCEPTED</span>
        <p>Postinstall script requested environment access and unrestricted outbound network.</p>
        <div><b>3</b> credentials protected <b>1</b> install stopped</div>
      </div>
    </div>
  );
}

export function Landing() {
  const reduce = useReducedMotion() ?? false;
  const reveal = reduce ? {} : { initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: 0.2 }, transition: { duration: 0.55, ease: [0.23, 1, 0.32, 1] as const } };

  return (
    <main className="landing-shell">
      <header className="landing-nav">
        <a className="landing-brand" href="#top" aria-label="JunoGuard home">
          <BrandMark />
          <span>JUNOGUARD</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#product">Product</a>
          <a href="#how">How it works</a>
          <a href="#architecture">Architecture</a>
          <a href="https://github.com/cosmicoral/TokenGuard" target="_blank" rel="noreferrer">GitHub</a>
        </nav>
        <a className="nav-console" href="/dashboard">Live console <span>↗</span></a>
      </header>

      <section className="landing-hero" id="top">
        <motion.div
          className="hero-copy"
          initial={reduce ? false : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: [0.23, 1, 0.32, 1] }}
        >
          <p className="hero-brand">
            <BrandMark />
            <span>JUNOGUARD</span>
          </p>
          <h1>The control plane between your agent and the blast radius.</h1>
          <p className="hero-lede">
            Every install, model call, and policy breach — decided before it
            lands. One deterministic gate. Allow, flag, or stop.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="/dashboard">
              Open live console <span>→</span>
            </a>
            <a className="text-action" href="#how">
              See the gate in action
            </a>
          </div>
        </motion.div>

        <motion.div
          className="hero-console-wrap"
          initial={reduce ? false : { opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.12, duration: 0.7, ease: [0.23, 1, 0.32, 1] }}
        >
          <div className="console-caption">
            <span>LIVE PRODUCT SURFACE</span>
            <span>GATE / ACTIVE</span>
          </div>
          <DecisionConsole />
        </motion.div>
      </section>

      <div className="system-strip" aria-label="JunoGuard integrations">
        <span>BUILT FOR</span>
        <div>
          <b>MCP</b><b>CURSOR</b><b>CLAUDE CODE</b><b>CODEX</b><b>OSSPREY</b><b>SUPABASE</b><b>MODAL</b>
        </div>
      </div>

      <section className="thesis-section" id="product">
        <motion.div {...reveal}>
          <p className="section-index">THE PROBLEM / 01</p>
          <h2>Your coding agent has your credentials, your shell, and no judgment.</h2>
        </motion.div>
        <motion.div className="thesis-copy" {...reveal}>
          <p>A dependency can instruct an agent to install malware. A stolen key can burn budget in minutes. Default tooling shows the damage after it happens.</p>
          <p>JunoGuard is the interrupt: a supervision layer that sits between intent and execution.</p>
        </motion.div>
      </section>

      <section className="gate-section" id="how">
        <div className="gate-intro">
          <p className="section-index">THE GATE / 02</p>
          <h2>One decision engine.<br />Two attack lanes.</h2>
        </div>
        <div className="gate-grid">
          <motion.article className="gate-card supply" {...reveal}>
            <div className="card-number">A</div>
            <div>
              <p className="card-label">SUPPLY CHAIN</p>
              <h3>Stop the package before it reaches disk.</h3>
              <p>Every install is intercepted over MCP, scanned for known risk, and refused with a structured reason the agent can understand.</p>
            </div>
            <ul>
              <li><span>01</span> Pre-install interception</li>
              <li><span>02</span> Malware and SBOM verdicts</li>
              <li><span>03</span> Sandboxed deep analysis</li>
            </ul>
          </motion.article>

          <motion.article className="gate-card tokens" {...reveal}>
            <div className="card-number">B</div>
            <div>
              <p className="card-label">TOKENS &amp; COST</p>
              <h3>Make abnormal spend a security signal.</h3>
              <p>Local pricing, hard budgets, rate limits, and burst detection stop runaway loops without spending more AI tokens to protect them.</p>
            </div>
            <div className="rate-plot" aria-label="Request rate crossing a policy limit">
              <span className="plot-limit">POLICY LIMIT</span>
              {[22, 35, 28, 48, 58, 38, 72, 88, 44, 63, 96, 68].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
            </div>
          </motion.article>
        </div>
      </section>

      <section className="architecture-section" id="architecture">
        <div className="architecture-head">
          <p className="section-index">ARCHITECTURE / 03</p>
          <h2>Fast where it must be.<br />Deep where it matters.</h2>
        </div>
        <div className="flow" aria-label="JunoGuard request flow">
          <div><span>01</span><strong>AGENT</strong><small>requests an action</small></div>
          <i>→</i>
          <div className="flow-core"><span>02</span><strong>JUNO</strong><small>evaluates policy</small></div>
          <i>→</i>
          <div><span>03</span><strong>DECISION</strong><small>allow / flag / block</small></div>
          <i>→</i>
          <div><span>04</span><strong>EVIDENCE</strong><small>records the radius</small></div>
        </div>
        <div className="principles">
          <div><b>~0 ms</b><span>LLM latency added</span></div>
          <div><b>1 gate</b><span>across both lanes</span></div>
          <div><b>100%</b><span>deterministic hot path</span></div>
          <p>AI runs only on the cold path, where flagged packages can be detonated safely and analyzed without holding up the agent.</p>
        </div>
      </section>

      <section className="final-cta">
        <p className="section-index">READY / 04</p>
        <h2>Give your agent<br />a line it cannot cross.</h2>
        <div>
          <a className="primary-action" href="/dashboard">Launch the live console <span>→</span></a>
          <a className="text-action" href="https://github.com/cosmicoral/TokenGuard" target="_blank" rel="noreferrer">Read the source on GitHub ↗</a>
        </div>
      </section>

      <footer className="landing-footer">
        <a className="landing-brand" href="#top"><BrandMark /><span>JUNOGUARD</span></a>
        <p>The supervision layer for AI coding agents.</p>
        <span>BUILT IN LONDON · 2026</span>
      </footer>
    </main>
  );
}
