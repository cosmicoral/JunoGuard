import { useEffect, useState } from "react";
import { BrandLockup } from "../components/BrandMark";
import { supabase } from "../lib/supabase";

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
      if (!data.session) throw new Error("OAuth sign-in completed without a session.");

      window.location.replace("/dashboard");
    })().catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : "Unable to complete OAuth sign-in.");
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="auth-page">
      <section className="auth-card" aria-live="polite">
        <a className="auth-brand" href="/" aria-label="JunoGuard home">
          <BrandLockup size={28} />
        </a>
        {error ? (
          <>
            <p className="auth-kicker">AUTHENTICATION FAILED</p>
            <h1>Sign-in could not be completed.</h1>
            <p className="auth-error" role="alert">{error}</p>
            <a className="auth-retry" href="/auth/sign-in">Return to sign in</a>
          </>
        ) : (
          <>
            <div className="auth-spinner" aria-hidden="true" />
            <p className="auth-kicker">SECURE SESSION</p>
            <h1>Completing sign-in…</h1>
            <p>JunoGuard is exchanging the provider authorization for your Supabase session.</p>
          </>
        )}
      </section>
    </main>
  );
}
