import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useAuth } from "./auth/AuthContext";
import { Header } from "./components/Header";
import { Stats } from "./components/Stats";
import { Feed } from "./components/Feed";
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
        <Header
          projectName={juno.project.name}
          suspended={juno.suspended}
          killError={juno.killError}
          userName={userName}
          userEmail={userEmail}
          avatarUrl={avatarUrl}
          signingOut={signingOut}
          authError={authError}
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
