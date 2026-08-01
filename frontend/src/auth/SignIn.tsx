import { useEffect, useState } from "react";
import { isSupabaseConfigured } from "../lib/supabase";
import { useAuth, type OAuthProvider } from "./AuthContext";

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path fill="#4285f4" d="M21.6 12.2c0-.7-.1-1.5-.2-2.2H12v4.3h5.4a4.6 4.6 0 0 1-2 3v2.8h3.5c2-1.9 3.2-4.6 3.2-7.9Z" />
      <path fill="#34a853" d="M12 22c2.9 0 5.3-.9 7-2.5l-3.5-2.7c-1 .7-2.2 1-3.5 1a6.2 6.2 0 0 1-5.8-4.3H2.6v2.8A10.6 10.6 0 0 0 12 22Z" />
      <path fill="#fbbc05" d="M6.2 13.5A6.4 6.4 0 0 1 6.2 9V6.2H2.6a10.6 10.6 0 0 0 0 10l3.6-2.7Z" />
      <path fill="#ea4335" d="M12 4.2c1.6 0 3 .5 4.1 1.6l3.1-3A10.3 10.3 0 0 0 2.6 6.2L6.2 9A6.2 6.2 0 0 1 12 4.2Z" />
    </svg>
  );
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path fill="currentColor" d="M12 .7a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.4-4-1.4-.5-1.4-1.3-1.8-1.3-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0C14.2 4.8 15.2 5 15.2 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.8 5.4-5.5 5.7.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  );
}

export function SignIn() {
  const { loading, session, signInWithProvider } = useAuth();
  const [submittingProvider, setSubmittingProvider] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && session) window.location.replace("/dashboard");
  }, [loading, session]);

  const signIn = async (provider: OAuthProvider) => {
    if (submittingProvider) return;
    setSubmittingProvider(provider);
    setError(null);

    try {
      await signInWithProvider(provider);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to start ${provider} sign-in.`);
      setSubmittingProvider(null);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card">
        <a className="auth-brand" href="/" aria-label="JunoGuard home">
          <span className="auth-mark" aria-hidden="true"><span /><span /><span /></span>
          JUNOGUARD
        </a>
        <p className="auth-kicker">CONTROL PLANE ACCESS</p>
        <h1>Sign in to your JunoGuard console.</h1>
        <p>Authenticate with Google or GitHub to inspect live decisions and manage the gate.</p>

        <div className="auth-provider-list">
          <button
            className="oauth-sign-in google-provider"
            type="button"
            onClick={() => void signIn("google")}
            disabled={!isSupabaseConfigured || loading || Boolean(submittingProvider) || Boolean(session)}
          >
            <GoogleMark />
            {submittingProvider === "google" ? "Redirecting to Google…" : "Continue with Google"}
          </button>

          <button
            className="oauth-sign-in github-provider"
            type="button"
            onClick={() => void signIn("github")}
            disabled={!isSupabaseConfigured || loading || Boolean(submittingProvider) || Boolean(session)}
          >
            <GitHubMark />
            {submittingProvider === "github" ? "Redirecting to GitHub…" : "Continue with GitHub"}
          </button>
        </div>

        {!isSupabaseConfigured && (
          <p className="auth-error" role="alert">
            Supabase is not configured. Add the frontend URL and anon key before signing in.
          </p>
        )}
        {error && <p className="auth-error" role="alert">{error}</p>}

        <p className="auth-footnote">Protected by Supabase Auth. JunoGuard never receives your provider password.</p>
      </section>
    </main>
  );
}
