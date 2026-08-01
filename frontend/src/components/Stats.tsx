import { motion } from "motion/react";
import { AnimatedNumber } from "./AnimatedNumber";
import { count, integer, usd } from "../lib/format";
import type { AgentAction, Incident, Policy } from "../lib/types";

type Tone = "default" | "allow" | "flag" | "block" | "muted";

/**
 * One sparkline in the whole dashboard, and it is here: the burst spike is
 * the entire Lane B argument in a single glyph. Bars over a line — at
 * projector distance a 2px stroke disappears and a bar does not.
 */
function Sparkline({ series, limit }: { series: number[]; limit: number }) {
  const n = Math.max(series.length, 1);
  const barW = 4;
  const gap = 2.5;
  const width = n * (barW + gap) - gap;
  const height = 30;
  const peak = Math.max(...series, limit * 1.4, 1);
  const limitY = height - (limit / peak) * height;

  return (
    <svg
      className="spark"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <line className="spark-limit" x1="0" y1={limitY} x2={width} y2={limitY} />
      {series.map((v, i) => {
        const h = Math.max((v / peak) * height, 1);
        const over = v > limit;
        const near = !over && v > limit * 0.8;
        return (
          <rect
            key={i}
            className="spark-bar"
            x={i * (barW + gap)}
            y={height - h}
            width={barW}
            height={h}
            rx={0.75}
            fill={over ? "var(--block)" : near ? "var(--flag)" : "var(--allow)"}
            opacity={over ? 1 : near ? 0.9 : 0.62}
          />
        );
      })}
    </svg>
  );
}

function Meter({ ratio, tone }: { ratio: number; tone: Tone }) {
  return (
    <div className="meter">
      <motion.div
        className="meter-fill"
        data-tone={tone}
        initial={false}
        animate={{ transform: `scaleX(${Math.min(ratio, 1)})` }}
        transition={{ type: "spring", bounce: 0, duration: 0.5 }}
      />
    </div>
  );
}

function Tile({
  label,
  value,
  format,
  unit,
  tone = "default",
  children,
}: {
  label: string;
  value: number;
  format: (n: number) => string;
  unit?: string;
  tone?: Tone;
  children?: React.ReactNode;
}) {
  return (
    <div className="panel tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value" data-tone={tone}>
        <AnimatedNumber value={value} format={format} />
        {unit && <span className="tile-unit">{unit}</span>}
      </div>
      {children && <div className="tile-bottom">{children}</div>}
    </div>
  );
}

export function Stats({
  actions,
  incidents,
  policy,
  spendToday,
  blockedCount,
  openIncidents,
  reqPerMin,
  rate,
}: {
  actions: AgentAction[];
  incidents: Incident[];
  policy: Policy;
  spendToday: number;
  blockedCount: number;
  openIncidents: number;
  reqPerMin: number;
  rate: number[];
}) {
  const budgetRatio = spendToday / policy.daily_budget_usd;
  const spendTone: Tone = budgetRatio >= 1 ? "block" : budgetRatio > 0.75 ? "flag" : "allow";

  const blocks = actions.filter((a) => a.decision === "block");
  const supplyBlocks = blocks.filter((a) => a.action_type === "package_install").length;
  const tokenBlocks = blocks.length - supplyBlocks;

  const worst = incidents
    .filter((i) => i.status === "open")
    .some((i) => i.severity === "critical")
    ? "critical"
    : openIncidents > 0
      ? "high"
      : "clear";

  const rateTone: Tone =
    reqPerMin > policy.max_requests_per_min
      ? "block"
      : reqPerMin > policy.max_requests_per_min * 0.8
        ? "flag"
        : "default";

  return (
    <div className="stats">
      <Tile label="Spend today" value={spendToday} format={usd} tone="default">
        <Meter ratio={budgetRatio} tone={spendTone} />
        <div className="tile-foot">of {usd(policy.daily_budget_usd)} daily cap</div>
      </Tile>

      <Tile
        label="Blocked"
        value={blockedCount}
        format={integer}
        tone={blockedCount > 0 ? "block" : "muted"}
      >
        <div className="tile-foot">
          {supplyBlocks} supply chain · {tokenBlocks} tokens
        </div>
      </Tile>

      <Tile
        label="Incidents"
        value={openIncidents}
        format={integer}
        unit="open"
        tone={openIncidents > 0 ? "flag" : "muted"}
      >
        <div className="tile-foot">
          {worst === "clear" ? "no active findings" : `severity: ${worst}`}
        </div>
      </Tile>

      <Tile label="Req / min" value={reqPerMin} format={count} tone={rateTone}>
        <Sparkline series={rate} limit={policy.max_requests_per_min} />
        <div className="tile-foot">last 2 min · cap {policy.max_requests_per_min}/min</div>
      </Tile>
    </div>
  );
}
