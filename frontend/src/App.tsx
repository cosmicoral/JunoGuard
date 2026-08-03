import { Dashboard } from "./Dashboard";
import { Landing } from "./Landing";
import { AuthCallback } from "./auth/AuthCallback";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { SignIn } from "./auth/SignIn";
import { BlogIndex } from "./blog/BlogIndex";
import { BlogPost } from "./blog/BlogPost";

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

  if (path === "/blog") return <BlogIndex />;

  const blogMatch = path.match(/^\/blog\/([^/]+)$/);
  if (blogMatch) return <BlogPost slug={blogMatch[1]} />;

  return <Landing />;
}
