import type { CSSProperties } from "react";

type BrandProps = {
  className?: string;
  size?: number | string;
  suspended?: boolean;
};

const RING_PATH = "M21.04 24.06A9.5 9.5 0 1 1 25.22 18.3";
const DOT = { cx: 21.04, cy: 24.06, r: 3.85 };

function tone(suspended: boolean | undefined) {
  return suspended ? "var(--block, #f85149)" : "var(--accent, #00C16A)";
}

export function BrandMark({ className, size = 32, suspended }: BrandProps) {
  const color = tone(suspended);

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={RING_PATH}
        stroke={color}
        strokeWidth="4.75"
        strokeLinecap="round"
      />
      <circle cx={DOT.cx} cy={DOT.cy} r={DOT.r} fill={color} />
    </svg>
  );
}

export function BrandLockup({ className, size = 28, suspended }: BrandProps) {
  const color = tone(suspended);
  const wordmarkSize = typeof size === "number" ? `${Math.max(11, size * 0.46)}px` : undefined;
  const style: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.58em",
    color,
  };

  return (
    <span className={className} style={style} aria-label="JunoGuard">
      <BrandMark size={size} suspended={suspended} />
      <span
        aria-hidden="true"
        style={{
          color,
          fontFamily: "var(--mono)",
          fontSize: wordmarkSize,
          fontWeight: 700,
          letterSpacing: "0.18em",
          lineHeight: 1,
        }}
      >
        JUNOGUARD
      </span>
    </span>
  );
}
