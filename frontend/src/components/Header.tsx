import { motion } from "motion/react";

function JunoMark({ suspended }: { suspended: boolean }) {
  const color = suspended ? "var(--block)" : "var(--juno)";
  return (
    <svg className="mark" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="8" fill="none" stroke={color} strokeWidth="1.25" opacity="0.4" />
      <circle cx="10" cy="10" r="5" fill="none" stroke={color} strokeWidth="1.25" opacity="0.7" />
      <circle cx="10" cy="10" r="2.1" fill={color} />
    </svg>
  );
}

export function Header({
  projectName,
  suspended,
  actionsToday,
  onToggleSuspend,
}: {
  projectName: string;
  suspended: boolean;
  actionsToday: number;
  onToggleSuspend: () => void;
}) {
  return (
    <header className="panel header" data-suspended={suspended}>
      <div className="brand">
        <JunoMark suspended={suspended} />
        <span className="wordmark">JUNO</span>
      </div>

      <div className="brand-rule" />
      <span className="project">{projectName}</span>

      <div className="status" data-suspended={suspended}>
        <motion.span
          className="dot"
          animate={{ scale: 1 }}
          initial={false}
          transition={{ type: "spring", bounce: 0, duration: 0.3 }}
        />
        {suspended ? "SUSPENDED" : "ACTIVE"}
      </div>

      <div className="spacer" />

      <span className="uptime">
        {actionsToday.toLocaleString("en-US")} actions gated today
      </span>

      <button
        className="kill"
        data-suspended={suspended}
        onClick={onToggleSuspend}
        aria-pressed={suspended}
      >
        {suspended ? "RESET" : "SUSPEND"}
      </button>
    </header>
  );
}
