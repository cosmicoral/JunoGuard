import { useEffect, type ReactNode } from "react";
import { isSupabaseConfigured } from "../lib/supabase";
import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { loading, session } = useAuth();

  // AuthContext can only ever produce a session when the Supabase client
  // exists. With no provider configured there is no authentication to enforce,
  // and gating anyway would make /dashboard permanently unreachable on the mock
  // and SSE lanes — sign-in cannot succeed there either. When Supabase IS
  // configured the gate stays fully intact.
  const enforced = isSupabaseConfigured;

  useEffect(() => {
    if (enforced && !loading && !session) window.location.replace("/auth/sign-in");
  }, [enforced, loading, session]);

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
