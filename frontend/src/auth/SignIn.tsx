import { useEffect, useState, type FormEvent } from "react";
import { isSupabaseConfigured } from "../lib/supabase";
import { useAuth, type OAuthProvider } from "./AuthContext";
import { BrandMark } from "../components/BrandMark";

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
  const { loading, session, signInWithProvider, signInWithEmail } = useAuth();
  const [submittingProvider, setSubmittingProvider] = useState<OAuthProvider | null>(null);
  const [email, setEmail] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [submittingEmail, setSubmittingEmail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = loading || Boolean(submittingProvider) || submittingEmail || Boolean(session);

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

  const submitEmail = async (event: FormEvent) => {
    event.preventDefault();
    if (submittingEmail || !email.trim()) return;
    setSubmittingEmail(true);
    setError(null);

    try {
      await signInWithEmail(email);
      setEmailSent(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to send the sign-in link.");
    } finally {
      setSubmittingEmail(false);
    }
  };

  return (
    <main className="auth-page">
      <header className="auth-nav">
        <a className="auth-nav-brand" href="/" aria-label="JunoGuard home">
          <BrandMark className="auth-mark" size={25} />
          <span>JUNOGUARD</span>
        </a>
        <nav aria-label="Explore JunoGuard">
          <a href="/#product">Product</a>
          <a href="/#how">How it works</a>
          <a href="/#install">Install</a>
          <a href="https://github.com/cosmicoral/JunoGuard" target="_blank" rel="noreferrer">
            GitHub ↗
          </a>
        </nav>
        <a className="auth-nav-home" href="/">Back home</a>
      </header>

      <section className="auth-card">
        <a className="auth-brand" href="/" aria-label="JunoGuard home">
          <BrandMark className="auth-mark" size={25} />
          JUNOGUARD
        </a>
        <p className="auth-kicker">Console access</p>
        <h1>Sign in to the live console</h1>
        <p className="auth-lede">
          Guarding installs and model calls through MCP or the CLI does not require an account.
          Sign in here to review Allow / Flag / Block decisions, open incidents, and use the kill switch.
        </p>

        {emailSent ? (
          <div className="auth-email-sent" role="status">
            <p className="auth-email-sent-title">Check your inbox</p>
            <p>
              We sent a sign-in link to <strong>{email.trim()}</strong>. Open it on this device to
              reach the console.
            </p>
            <button
              className="auth-email-resend"
              type="button"
              onClick={() => {
                setEmailSent(false);
                setError(null);
              }}
            >
              Use a different email
            </button>
          </div>
        ) : (
          <>
            <form className="auth-email-form" onSubmit={(event) => void submitEmail(event)}>
              <label className="auth-email-label" htmlFor="auth-email">
                Email
              </label>
              <div className="auth-email-row">
                <input
                  id="auth-email"
                  className="auth-email-input"
                  type="email"
                  name="email"
                  autoComplete="email"
                  inputMode="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={!isSupabaseConfigured || busy}
                  required
                />
                <button
                  className="auth-email-submit"
                  type="submit"
                  disabled={!isSupabaseConfigured || busy || !email.trim()}
                >
                  {submittingEmail ? "Sending…" : "Send link"}
                </button>
              </div>
              <p className="auth-email-hint">Passwordless — we email a one-time sign-in link.</p>
            </form>

            <p className="auth-divider" aria-hidden="true">
              <span>or continue with</span>
            </p>

            <div className="auth-provider-list">
              <button
                className="oauth-sign-in google-provider"
                type="button"
                onClick={() => void signIn("google")}
                disabled={!isSupabaseConfigured || busy}
              >
                <GoogleMark />
                {submittingProvider === "google" ? "Redirecting to Google…" : "Continue with Google"}
              </button>

              <button
                className="oauth-sign-in github-provider"
                type="button"
                onClick={() => void signIn("github")}
                disabled={!isSupabaseConfigured || busy}
              >
                <GitHubMark />
                {submittingProvider === "github" ? "Redirecting to GitHub…" : "Continue with GitHub"}
              </button>
            </div>
          </>
        )}

        <a className="auth-skip" href="/#install">
          Skip sign-in — install the guard with npx
        </a>

        {!isSupabaseConfigured && (
          <p className="auth-error" role="alert">
            Supabase is not configured. Add the frontend URL and anon key before signing in.
          </p>
        )}
        {error && <p className="auth-error" role="alert">{error}</p>}

        <p className="auth-footnote">
          Protected by Supabase Auth. JunoGuard never receives your provider password.
        </p>
        <nav className="auth-card-links" aria-label="More JunoGuard links">
          <a href="/#product">Explore the product</a>
          <a href="/#install">View setup guide</a>
        </nav>
      </section>
    </main>
  );
}
