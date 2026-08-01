import type { ReactNode } from "react";
import { motion } from "motion/react";
import { AnimatedNumber } from "./AnimatedNumber";
import { count, integer, usd } from "../lib/format";
import type { AgentAction, Policy } from "../lib/types";

type Tone = "default" | "allow" | "flag" | "block" | "muted";

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
  chip,
  chipTone = "allow",
  children,
}: {
  label: string;
  value: number;
  format: (n: number) => string;
  unit?: string;
  tone?: Tone;
  chip?: string;
  chipTone?: Tone;
  children?: ReactNode;
}) {
  return (
    <div className="panel tile kpi-card">
      <div className="tile-topline">
        <div className="tile-label">{label}</div>
        {chip && (
          <span className="trend-chip" data-tone={chipTone}>
            {chip}
          </span>
        )}
      </div>
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
  policy,
  spendToday,
  blockedCount,
  reqPerMin,
  actionsToday,
}: {
  actions: AgentAction[];
  policy: Policy;
  spendToday: number;
  blockedCount: number;
  reqPerMin: number;
  actionsToday: number;
}) {
  const budgetRatio = policy.daily_budget_usd > 0 ? spendToday / policy.daily_budget_usd : 0;
  const spendTone: Tone = budgetRatio >= 1 ? "block" : budgetRatio > 0.75 ? "flag" : "allow";
  const healthLabel =
    budgetRatio >= 1 ? "cap reached" : budgetRatio > 0.75 ? "budget watch" : "gate healthy";

  const blocks = actions.filter((a) => a.decision === "block");
  const packageBlocks = blocks.filter((a) => a.action_type === "package_install").length;
  const llmBlocks = blocks.length - packageBlocks;

  const rateTone: Tone =
    reqPerMin > policy.max_requests_per_min
      ? "block"
      : reqPerMin > policy.max_requests_per_min * 0.8
        ? "flag"
        : "default";

  return (
    <div className="stats">
      <Tile
        label="Spend today"
        value={spendToday}
        format={usd}
        chip={healthLabel}
        chipTone={spendTone}
      >
        <Meter ratio={budgetRatio} tone={spendTone} />
        <div className="tile-foot">
          {Math.round(Math.min(budgetRatio, 1) * 100)}% of {usd(policy.daily_budget_usd)} daily
          budget
        </div>
      </Tile>

      <Tile
        label="Blocked"
        value={blockedCount}
        format={integer}
        tone={blockedCount > 0 ? "block" : "muted"}
      >
        <div className="tile-foot">
          {packageBlocks} package · {llmBlocks} LLM decisions
        </div>
      </Tile>

      <Tile
        label="Actions gated"
        value={actionsToday}
        format={integer}
        unit="total"
        tone={rateTone}
      >
        <div className="kpi-split">
          <span>{count(reqPerMin)}</span>
          <small>req / min</small>
        </div>
        <div className="tile-foot">last minute · cap {policy.max_requests_per_min}/min</div>
      </Tile>
    </div>
  );
}
