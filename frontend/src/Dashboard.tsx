import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useAuth } from "./auth/AuthContext";
import { Header } from "./components/Header";
import { Stats } from "./components/Stats";
import { Feed } from "./components/Feed";
import { mode } from "./lib/supabase";
import { useJuno } from "./lib/useJuno";

export function Dashboard() {
  const juno = useJuno();
  const { user, signOut } = useAuth();
  const reduce = useReducedMotion() ?? false;
  const [signingOut, setSigningOut] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const metadata = user?.user_metadata ?? {};
  const userEmail =
    user?.email ||
    (typeof metadata.email === "string" && metadata.email) ||
    "Email unavailable";
  const userName =
    (typeof metadata.full_name === "string" && metadata.full_name) ||
    (typeof metadata.name === "string" && metadata.name) ||
    (typeof metadata.user_name === "string" && metadata.user_name) ||
    (typeof metadata.preferred_username === "string" && metadata.preferred_username) ||
    user?.email?.split("@")[0] ||
    "JunoGuard user";
  const avatarUrl =
    (typeof metadata.avatar_url === "string" && metadata.avatar_url) ||
    (typeof metadata.picture === "string" && metadata.picture) ||
    null;

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    setAuthError(null);
    try {
      await signOut();
      window.location.replace("/auth/sign-in");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Unable to sign out.");
      setSigningOut(false);
    }
  };

  useEffect(() => {
    document.body.dataset.suspended = String(juno.suspended);
    return () => {
      delete document.body.dataset.suspended;
    };
  }, [juno.suspended]);

  return (
    <div className="dashboard-page">
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
        {juno.degraded && (
          <p className="mode-banner" data-mode="degraded" role="alert">
            <strong>DEGRADED — GATEWAY UNREACHABLE</strong>
            <span>
              This console is not receiving decisions. The counters below are frozen and
              the kill switch is disabled. Agents are not necessarily unsupervised — the
              gateway may be enforcing policy while this page cannot reach it.
            </span>
            <button type="button" className="mode-action" onClick={() => window.location.reload()}>
              RETRY
            </button>
            <button type="button" className="mode-action" onClick={juno.enterSimulation}>
              ENTER DEMO SIMULATION
            </button>
          </p>
        )}

        {juno.simulating && (
          <p className="mode-banner" data-mode="simulation" role="status">
            <strong>SIMULATION</strong>
            <span>
              Invented traffic, requested by an operator after a gateway outage. Nothing on
              this page reflects a real agent.
            </span>
          </p>
        )}

        {mode === "demo" && !juno.degraded && !juno.simulating && (
          <p className="mode-banner" data-mode="demo" role="status">
            <strong>DEMO</strong>
            {juno.source === "mock"
              ? "Simulated traffic. No agent is being supervised and the kill switch changes nothing outside this page."
              : "Demo build. The decisions below are real, but this is not a production control plane."}
          </p>
        )}

        <Header
          projectName={juno.project.name}
          suspended={juno.suspended}
          killError={juno.killError}
          userName={userName}
          userEmail={userEmail}
          avatarUrl={avatarUrl}
          signingOut={signingOut}
          authError={authError}
          canControl={juno.canControl}
          role={juno.role}
          onSignOut={() => void handleSignOut()}
          onToggleSuspend={juno.toggleSuspend}
        />

        {juno.accessError && (
          <p className="access-notice" role="status">
            <strong>NO PROJECT ACCESS</strong>
            {juno.accessError}
          </p>
        )}

        {juno.feedError && (
          <p className="access-notice" role="status">
            <strong>LIVE FEED NOT AUTHORIZED</strong>
            {juno.feedError}
          </p>
        )}

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
    </div>
  );
}
