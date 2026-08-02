import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useAuth } from "./auth/AuthContext";
import { ActivityChart } from "./components/ActivityChart";
import { Stats } from "./components/Stats";
import { Feed } from "./components/Feed";
import { PRODUCT_LINKS, Sidebar, type DashboardSection } from "./components/Sidebar";
import { mode } from "./lib/supabase";
import { useJuno } from "./lib/useJuno";

export function Dashboard() {
  const juno = useJuno();
  const { user, signOut } = useAuth();
  const reduce = useReducedMotion() ?? false;
  const [signingOut, setSigningOut] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<DashboardSection>("overview");
  const overviewRef = useRef<HTMLElement | null>(null);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const incidentsRef = useRef<HTMLElement | null>(null);
  const controlsRef = useRef<HTMLElement | null>(null);

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
  const openIncidents = juno.incidents.filter((incident) => incident.status === "open");

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    setAuthError(null);
    try {
      await signOut();
      window.location.replace("/");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Unable to sign out.");
      setSigningOut(false);
    }
  };

  const sectionNode = (section: DashboardSection) => {
    switch (section) {
      case "overview":
        return overviewRef.current;
      case "feed":
        return feedRef.current;
      case "incidents":
        return incidentsRef.current;
      case "controls":
        return controlsRef.current;
    }
  };

  const handleNavigate = (section: DashboardSection) => {
    setActiveSection(section);
    sectionNode(section)?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "start",
    });
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

      <div className="app dashboard-shell">
        <Sidebar
          activeSection={activeSection}
          suspended={juno.suspended}
          userName={userName}
          userEmail={userEmail}
          avatarUrl={avatarUrl}
          signingOut={signingOut}
          authError={authError}
          killError={juno.killError}
          canControl={juno.canControl}
          role={juno.role}
          onNavigate={handleNavigate}
          onSignOut={() => void handleSignOut()}
          onToggleSuspend={juno.toggleSuspend}
        />

        <main className="dashboard-main" data-suspended={juno.suspended}>
          <nav className="dashboard-guide-links" aria-label="Product guide">
            <strong>Product guide</strong>
            {PRODUCT_LINKS.map((link) => (
              <a href={link.href} key={link.href}>
                {link.label}
              </a>
            ))}
          </nav>

          <section ref={overviewRef} id="overview" className="dashboard-topbar">
            <div>
              <p className="section-kicker">JunoGuard</p>
              <h1>Overview</h1>
              <p>{juno.project.name}</p>
            </div>
            <div className="topbar-status" data-suspended={juno.suspended}>
              <span className="status" data-suspended={juno.suspended}>
                <motion.span
                  className="dot"
                  animate={{ scale: 1 }}
                  initial={false}
                  transition={{ type: "spring", bounce: 0, duration: 0.3 }}
                />
                {juno.suspended ? "SUSPENDED" : "ACTIVE"}
              </span>
              <span className="project-source">{juno.source.toUpperCase()}</span>
            </div>
          </section>

          <div className="dashboard-banners">
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
          </div>

          <Stats
            actions={juno.actions}
            policy={juno.policy}
            spendToday={juno.spendToday}
            blockedCount={juno.blockedCount}
            reqPerMin={juno.reqPerMin}
            actionsToday={juno.actionsToday}
          />

          <ActivityChart
            rate={juno.rate}
            limit={juno.policy.max_requests_per_min}
            reqPerMin={juno.reqPerMin}
          />

          <div ref={feedRef} id="feed" className="feed-section">
            <Feed actions={juno.actions} freshIds={juno.freshIds} source={juno.source} />
          </div>

          <div className="dashboard-support-grid">
            <section ref={incidentsRef} id="incidents" className="panel support-card incident-card">
              <div className="support-card-head">
                <div>
                  <p className="section-kicker">Incidents</p>
                  <h2>Open findings</h2>
                </div>
                <strong>{juno.openIncidents}</strong>
              </div>
              {openIncidents.length > 0 ? (
                <ul className="incident-list">
                  {openIncidents.slice(0, 5).map((incident) => (
                    <li key={incident.id}>
                      <span data-severity={incident.severity}>{incident.severity}</span>
                      <div>
                        <strong>{incident.title}</strong>
                        <small>
                          {incident.status} · {new Date(incident.created_at).toLocaleString()}
                        </small>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-copy">No open incidents returned by the current JunoGuard feed.</p>
              )}
            </section>

            <section ref={controlsRef} id="controls" className="panel support-card controls-card">
              <div className="support-card-head">
                <div>
                  <p className="section-kicker">Controls</p>
                  <h2>Operator state</h2>
                </div>
                <span className="control-role">{juno.role ?? "local"}</span>
              </div>
              <dl className="control-grid">
                <div>
                  <dt>Project</dt>
                  <dd>{juno.suspended ? "Suspended" : "Active"}</dd>
                </div>
                <div>
                  <dt>Kill switch</dt>
                  <dd>{juno.canControl ? "Available in sidebar" : "Unavailable for this session"}</dd>
                </div>
              </dl>
              {juno.lastControl ? (
                <p className="control-history">
                  Last state change: <strong>{juno.lastControl.action.toUpperCase()}</strong> by{" "}
                  {juno.lastControl.actor_email ?? juno.lastControl.actor_id} (
                  {juno.lastControl.actor_role}) at{" "}
                  {new Date(juno.lastControl.created_at).toLocaleString()}
                  {juno.lastControl.reason ? ` - ${juno.lastControl.reason}` : ""}
                  {juno.lastControl.incident_id ? " · incident reviewed" : ""}
                </p>
              ) : (
                <p className="empty-copy">No control history has been reported for this project.</p>
              )}
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
