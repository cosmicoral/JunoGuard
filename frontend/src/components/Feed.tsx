import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { clockTime, tokens, usdFine } from "../lib/format";
import type { AgentAction, BlastRadius, Decision } from "../lib/types";

/** Rendering the whole in-memory buffer costs layout work we do not need. */
const VISIBLE_ROWS = 60;

const BLOCK_RESTING = "rgba(248, 81, 73, 0.055)";
const BLOCK_FLASH = "rgba(248, 81, 73, 0.28)";
const TRANSPARENT = "rgba(248, 81, 73, 0)";

const GLYPH: Record<Decision, string> = { allow: "✓", flag: "!", block: "✕" };
const LABEL: Record<Decision, string> = { allow: "allow", flag: "FLAGGED", block: "BLOCKED" };

/**
 * "BLOCKED" on its own leaves the room asking why. Two words of cause, pulled
 * off the reason the gateway already wrote, answers it from twenty feet.
 */
function blockNote(action: AgentAction): string | null {
  if (action.decision !== "block") return null;
  const reason = action.reason.toLowerCase();
  if (reason.startsWith("project suspended")) return "project suspended";
  if (reason.includes("rate limit")) return "rate limit";
  if (reason.includes("budget")) return "budget exceeded";
  if (reason.includes("malicious")) return "malicious";
  return "policy";
}

function BlastRadiusPanel({ reason, blast }: { reason: string; blast: BlastRadius }) {
  return (
    <div className="blast-inner">
      <div className="blast-reason">{reason}</div>
      <div className="blast-grid">
        <div className="blast-key">Credentials in scope</div>
        <div className="blast-val">
          {blast.credentials.map((c) => (
            <span className="cred" key={c}>
              {c}
            </span>
          ))}
        </div>
        <div className="blast-key">Network egress</div>
        <div className="blast-val">{blast.network_egress}</div>
        <div className="blast-key">Write access</div>
        <div className="blast-val">{blast.write_access}</div>
      </div>
      <div className="blast-summary">Estimated blast radius — {blast.summary}</div>
      <div className="blast-hint">Refused pre-install. Nothing reached disk.</div>
    </div>
  );
}

function Row({
  action,
  fresh,
  expanded,
  onToggle,
  reduce,
}: {
  action: AgentAction;
  fresh: boolean;
  expanded: boolean;
  onToggle: () => void;
  reduce: boolean;
}) {
  const isBlock = action.decision === "block";
  const blast = action.metadata?.blast_radius;
  const resting = isBlock ? BLOCK_RESTING : TRANSPARENT;
  const animate = fresh
    ? {
        opacity: 1,
        y: 0,
        // One red flash on arrival. Once — then it just sits there.
        backgroundColor: isBlock && !reduce ? [BLOCK_FLASH, resting] : resting,
      }
    : { opacity: 1, y: 0, backgroundColor: resting };

  const note = blockNote(action);

  return (
    <motion.li
      layout={reduce ? false : "position"}
      className="row"
      data-decision={action.decision}
      data-expandable={Boolean(blast)}
      initial={fresh && !reduce ? { opacity: 0, y: -10 } : false}
      animate={animate}
      transition={{
        default: { type: "spring", bounce: 0, duration: 0.3 },
        backgroundColor: { duration: 0.9, ease: [0.23, 1, 0.32, 1] },
        layout: { type: "spring", bounce: 0, duration: 0.32 },
      }}
    >
      <div
        className="row-main"
        onClick={blast ? onToggle : undefined}
        role={blast ? "button" : undefined}
        tabIndex={blast ? 0 : undefined}
        onKeyDown={
          blast
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onToggle();
                }
              }
            : undefined
        }
      >
        <span className="cell-time">{clockTime(action.created_at)}</span>
        <span className="cell-glyph" data-tone={action.decision}>
          {GLYPH[action.decision]}
        </span>
        <span className="cell-lane">
          {action.action_type === "package_install" ? "pkg" : "llm"}
        </span>
        <span className="cell-target">{action.target}</span>

        <span className="cell-meta">
          <span className="tok">
            {action.tokens_in != null
              ? tokens((action.tokens_in ?? 0) + (action.tokens_out ?? 0))
              : ""}
          </span>
          <span className="cost">
            {action.cost_usd != null ? usdFine(Number(action.cost_usd)) : ""}
          </span>
          <span
            className="note"
            data-tone={note ? "block" : action.decision === "flag" ? "flag" : undefined}
          >
            {note ??
              (action.action_type === "package_install"
                ? (action.metadata?.ossprey?.verdict ?? "")
                : "")}
          </span>
        </span>

        <span className="cell-decision" data-tone={action.decision}>
          {LABEL[action.decision]}
        </span>
      </div>

      <AnimatePresence initial={false}>
        {blast && expanded && (
          <motion.div
            className="blast"
            initial={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            animate={reduce ? { opacity: 1 } : { height: "auto", opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ type: "spring", bounce: 0, duration: 0.34 }}
          >
            <BlastRadiusPanel reason={action.reason} blast={blast} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

export function Feed({
  actions,
  freshIds,
  live,
}: {
  actions: AgentAction[];
  freshIds: Set<string>;
  live: boolean;
}) {
  const reduce = useReducedMotion() ?? false;
  // Only holds explicit user overrides. The default is derived, so a blocked
  // row is open the frame it lands — the blast radius is the payload of the
  // whole demo and must not depend on hitting a 28px row on stage.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});

  const rows = actions.slice(-VISIBLE_ROWS).reverse();

  return (
    <section className="panel feed">
      <div className="feed-head">
        <span className="feed-title">Live</span>
        <span className="feed-mode">{live ? "SUPABASE REALTIME" : "MOCK"}</span>
        <span className="feed-count">both lanes · newest first</span>
      </div>
      <ul className="feed-list">
        {rows.map((action) => {
          const fresh = freshIds.has(action.id);
          const openByDefault = fresh && Boolean(action.metadata?.blast_radius);
          const expanded = overrides[action.id] ?? openByDefault;
          return (
            <Row
              key={action.id}
              action={action}
              fresh={fresh}
              expanded={expanded}
              onToggle={() => setOverrides((prev) => ({ ...prev, [action.id]: !expanded }))}
              reduce={reduce}
            />
          );
        })}
      </ul>
    </section>
  );
}
