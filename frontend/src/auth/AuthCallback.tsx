import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { BrandMark } from "../components/BrandMark";

let pendingCode: string | null = null;
let pendingExchange: Promise<void> | null = null;

function exchangeCode(code: string): Promise<void> {
  if (!supabase) return Promise.reject(new Error("Supabase is not configured."));
  if (pendingCode === code && pendingExchange) return pendingExchange;

  pendingCode = code;
  pendingExchange = supabase.auth.exchangeCodeForSession(code).then(({ error }) => {
    if (error) throw error;
  });
  return pendingExchange;
}

export function AuthCallback() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    void (async () => {
      const params = new URLSearchParams(window.location.search);
      const providerError = params.get("error_description") ?? params.get("error");
      if (providerError) throw new Error(providerError);

      if (!supabase) throw new Error("Supabase is not configured for this deployment.");

      const code = params.get("code");
      if (code) await exchangeCode(code);

      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) throw sessionError;
      if (!data.session) throw new Error("Sign-in completed without a session.");

      window.location.replace("/dashboard");
    })().catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : "Unable to complete sign-in.");
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="auth-page">
      <section className="auth-card" aria-live="polite">
        <a className="auth-brand" href="/" aria-label="JunoGuard home">
          <BrandMark className="auth-mark" size={25} />
          JUNOGUARD
        </a>
        {error ? (
          <>
            <p className="auth-kicker">Sign-in failed</p>
            <h1>Could not complete authentication</h1>
            <p className="auth-error" role="alert">{error}</p>
            <a className="auth-retry" href="/auth/sign-in">Return to sign in</a>
          </>
        ) : (
          <>
            <div className="auth-spinner" aria-hidden="true" />
            <p className="auth-kicker">Session</p>
            <h1>Completing sign-in…</h1>
            <p>Finishing your console session.</p>
          </>
        )}
      </section>
    </main>
  );
}
