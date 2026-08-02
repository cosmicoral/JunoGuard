import type { CSSProperties } from "react";

type BrandProps = {
  className?: string;
  size?: number | string;
  suspended?: boolean;
};

const RING_PATH = "M21.04 24.06A9.5 9.5 0 1 1 25.22 18.3";
const DOT = { cx: 21.04, cy: 24.06, r: 3.85 };

/**
 * Two tones, not one. In the brand board the ring is the neutral — white on
 * dark, near-black on light — and only the dot is emerald. Painting both green
 * loses the whole idea of the mark: a single live point closing an open ring.
 * The ring inherits, so the mark works on any surface.
 */
function ringTone(suspended: boolean | undefined) {
  return suspended ? "var(--block, #f85149)" : "currentColor";
}

function dotTone(suspended: boolean | undefined) {
  return suspended ? "var(--block, #f85149)" : "var(--accent, #00C16A)";
}

export function BrandMark({ className, size = 32, suspended }: BrandProps) {
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
        stroke={ringTone(suspended)}
        strokeWidth="4.75"
        strokeLinecap="round"
      />
      <circle cx={DOT.cx} cy={DOT.cy} r={DOT.r} fill={dotTone(suspended)} />
    </svg>
  );
}

export function BrandLockup({ className, size = 28, suspended }: BrandProps) {
  const wordmarkSize = typeof size === "number" ? `${Math.max(11, size * 0.46)}px` : undefined;
  // No colour forced here. The wordmark is off-white in the brand board, not
  // emerald; it inherits so the lockup sits correctly on navy or on white, and
  // the mark's ring inherits the same neutral.
  const style: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.58em",
    color: suspended ? "var(--block, #f85149)" : undefined,
  };

  return (
    <span className={className} style={style} aria-label="JunoGuard">
      <BrandMark size={size} suspended={suspended} />
      <span
        aria-hidden="true"
        style={{
          // Sans, not mono. The board sets the wordmark in Söhne; Inter is the
          // licensed stand-in it already names for body and UI.
          fontFamily: "var(--sans)",
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
