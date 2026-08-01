import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Header } from "./components/Header";
import { Stats } from "./components/Stats";
import { Feed } from "./components/Feed";
import { useJuno } from "./lib/useJuno";

export default function App() {
  const juno = useJuno();
  const reduce = useReducedMotion() ?? false;

  // The kill switch is a whole-screen state change, so it lives on <body>.
  useEffect(() => {
    document.body.dataset.suspended = String(juno.suspended);
  }, [juno.suspended]);

  return (
    <>
      <AnimatePresence>
        {juno.suspended && (
          <motion.div
            className="rail"
            initial={reduce ? { opacity: 0 } : { scaleX: 0, opacity: 0 }}
            animate={reduce ? { opacity: 1 } : { scaleX: 1, opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", bounce: 0, duration: 0.4 }}
          />
        )}
      </AnimatePresence>

      {/* One wash, on the transition into suspension. Not a loop, not a shake. */}
      <AnimatePresence>
        {juno.suspended && !reduce && (
          <motion.div
            key={juno.suspendedAt ?? "flash"}
            className="flash"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.62, times: [0, 0.16, 1], ease: [0.23, 1, 0.32, 1] }}
          />
        )}
      </AnimatePresence>

      <div className="app">
        <Header
          projectName={juno.project.name}
          suspended={juno.suspended}
          actionsToday={juno.actionsToday}
          killError={juno.killError}
          onToggleSuspend={juno.toggleSuspend}
        />

        <Stats
          actions={juno.actions}
          incidents={juno.incidents}
          policy={juno.policy}
          spendToday={juno.spendToday}
          blockedCount={juno.blockedCount}
          openIncidents={juno.openIncidents}
          reqPerMin={juno.reqPerMin}
          rate={juno.rate}
        />

        <Feed actions={juno.actions} freshIds={juno.freshIds} source={juno.source} />
      </div>
    </>
  );
}
