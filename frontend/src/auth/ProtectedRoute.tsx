import { useEffect, type ReactNode } from "react";
import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { loading, session } = useAuth();

  useEffect(() => {
    if (!loading && !session) window.location.replace("/auth/sign-in");
  }, [loading, session]);

  if (loading || !session) {
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
