/**
 * Pure mode / data-source resolution for the dashboard (JG-007 / JG-008).
 *
 * Kept free of `import.meta.env` so the security suite can pin the invariants
 * without booting Vite.
 */

export type JunoMode = "demo" | "live";
export type DataSource = "supabase" | "sse" | "mock";

export function resolveDataSource(
  supabaseConfigured: boolean,
  hasApiUrl: boolean,
): DataSource {
  if (supabaseConfigured) return "supabase";
  if (hasApiUrl) return "sse";
  return "mock";
}

export function resolveJunoMode(
  declared: string | undefined,
  supabaseConfigured: boolean,
): { mode: JunoMode; modeIsDeclared: boolean; isMisconfigured: boolean } {
  const normalized = declared?.trim().toLowerCase();
  const modeIsDeclared = normalized === "live" || normalized === "demo";
  const mode: JunoMode =
    normalized === "live"
      ? "live"
      : normalized === "demo"
        ? "demo"
        : supabaseConfigured
          ? "live"
          : "demo";
  return {
    mode,
    modeIsDeclared,
    isMisconfigured: mode === "live" && !supabaseConfigured,
  };
}
