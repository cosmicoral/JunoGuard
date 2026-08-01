import { useEffect, type ReactNode } from "react";
import { isMisconfigured, mode } from "../lib/supabase";
import { useAuth } from "./AuthContext";

/**
 * The gate in front of the dashboard.
 *
 * What it enforces comes from the build's declared mode, not from which
 * credentials happen to be present. In `live` mode a session is mandatory. In
 * `demo` mode there is no authentication to enforce and the dashboard is
 * reachable — labelled as simulated, which is the honest description of it.
 *
 * A `live` build missing its Supabase configuration is a configuration error and
 * is reported as one. It is never resolved by letting the request through: if
 * deleting an environment variable opened the console, the gate would be
 * decoration.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { loading, session } = useAuth();
  const enforced = mode === "live";

  useEffect(() => {
    if (enforced && !isMisconfigured && !loading && !session) {
      window.location.replace("/auth/sign-in");
    }
  }, [enforced, loading, session]);

  if (isMisconfigured) {
    return (
      <main className="auth-page">
        <section className="auth-card">
          <p className="auth-kicker">CONFIGURATION ERROR</p>
          <h1>This build runs in live mode but has no Supabase credentials.</h1>
          <p>
            Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>, or
            build with <code>VITE_JUNO_MODE=demo</code> for a simulated dashboard.
          </p>
          <p className="auth-error" role="alert">
            The console stays closed until authentication is available. Removing a
            credential is not a way past sign-in.
          </p>
        </section>
      </main>
    );
  }

  if (enforced && (loading || !session)) {
    return (
      <main className="auth-page">
        <div className="auth-route-loading" role="status">
          <div className="auth-spinner" aria-hidden="true" />
          Restoring secure session…
        </div>
      </main>
    );
  }

  return children;
}
