import { Dashboard } from "./Dashboard";
import { Landing } from "./Landing";
import { AuthCallback } from "./auth/AuthCallback";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { SignIn } from "./auth/SignIn";

export default function App() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";

  if (path === "/auth/callback") return <AuthCallback />;
  if (path === "/auth/sign-in") return <SignIn />;
  if (path.startsWith("/dashboard")) {
    return (
      <ProtectedRoute>
        <Dashboard />
      </ProtectedRoute>
    );
  }

  return <Landing />;
}
