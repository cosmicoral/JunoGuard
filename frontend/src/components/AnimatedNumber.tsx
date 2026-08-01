import { useEffect, useState } from "react";
import { useMotionValue, useReducedMotion, useSpring } from "motion/react";

/**
 * Numbers transition rather than snap. Tabular figures upstream keep the
 * width fixed, so nothing around them shifts while a value settles.
 */
export function AnimatedNumber({
  value,
  format,
}: {
  value: number;
  format: (n: number) => string;
}) {
  const reduce = useReducedMotion();
  const motionValue = useMotionValue(value);
  const spring = useSpring(motionValue, { bounce: 0, duration: 0.5 });
  const [display, setDisplay] = useState(() => format(value));

  useEffect(() => {
    if (reduce) setDisplay(format(value));
    else motionValue.set(value);
  }, [value, reduce, format, motionValue]);

  useEffect(() => {
    if (reduce) return;
    return spring.on("change", (v) => setDisplay(format(v)));
  }, [spring, format, reduce]);

  return <>{display}</>;
}
