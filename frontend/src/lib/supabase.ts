import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  resolveDataSource,
  resolveJunoMode,
  type DataSource,
  type JunoMode,
} from "./mode";

export type { DataSource, JunoMode };

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

/** Gateway base URL. Required for SSE mode and the kill switch. */
export const apiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");

/**
 * Data source precedence, matching docs/api-contract.md:
 *   Supabase (if VITE_SUPABASE_URL) > SSE (if VITE_API_URL) > mock
 */
export const isSupabaseConfigured = Boolean(url && anonKey);

export const dataSource: DataSource = resolveDataSource(
  isSupabaseConfigured,
  Boolean(apiUrl),
);

/**
 * Whether this build is a demo or a control plane.
 *
 * Previously this was inferred from whether credentials happened to be present,
 * which made two bad outcomes possible at once: a clean checkout could not reach
 * the dashboard at all (sign-in was mandatory but impossible), and a real
 * deployment could in principle be softened by removing a variable.
 *
 * It is now declared. `VITE_JUNO_MODE=live` means authentication is mandatory —
 * and if its credentials are missing the app says so and stops, rather than
 * falling back to something more permissive. Only an undeclared local build
 * falls back to demo.
 */
const resolved = resolveJunoMode(
  import.meta.env.VITE_JUNO_MODE as string | undefined,
  isSupabaseConfigured,
);

export const modeIsDeclared = resolved.modeIsDeclared;
export const mode: JunoMode = resolved.mode;

/**
 * Live mode declared, but the credentials it needs are absent. Never resolved
 * by relaxing the gate: removing a variable must not be a way past sign-in.
 */
export const isMisconfigured = resolved.isMisconfigured;

/** True when the feed is driven by a live source rather than the mock timer. */
export const isLive = dataSource !== "mock";

export const supabase: SupabaseClient | null =
  isSupabaseConfigured
    ? createClient(url!, anonKey!, {
        auth: {
          autoRefreshToken: true,
          detectSessionInUrl: false,
          flowType: "pkce",
          persistSession: true,
        },
        realtime: { params: { eventsPerSecond: 20 } },
      })
    : null;

/**
 * Agent key for the local SSE lane, read from the environment — never baked in.
 *
 * A key compiled into the bundle is a published credential: anyone who loaded
 * the page could replay it against the gateway. It is also the wrong kind of
 * credential for a browser to hold at all, which is why it authorizes only the
 * read-only feed here and nothing on the control plane.
 */
export const JUNO_KEY = (import.meta.env.VITE_JUNO_KEY as string | undefined) ?? "";

/**
 * Operator credential for the local lane's kill switch, for deployments with no
 * Supabase to sign into. Suspend and resume refuse agent keys outright, so
 * without this the kill switch is correctly unavailable rather than quietly
 * falling back to something weaker.
 */
export const OPERATOR_TOKEN =
  (import.meta.env.VITE_JUNO_OPERATOR_TOKEN as string | undefined) ?? "";
