import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

/** Gateway base URL. Required for SSE mode and the kill switch. */
export const apiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");

/**
 * Data source precedence, matching docs/api-contract.md:
 *   Supabase (if VITE_SUPABASE_URL) > SSE (if VITE_API_URL) > mock
 */
export type DataSource = "supabase" | "sse" | "mock";

export const dataSource: DataSource =
  url && anonKey ? "supabase" : apiUrl ? "sse" : "mock";

/** True when the feed is driven by a live source rather than the mock timer. */
export const isLive = dataSource !== "mock";

export const supabase: SupabaseClient | null =
  dataSource === "supabase"
    ? createClient(url!, anonKey!, { realtime: { params: { eventsPerSecond: 20 } } })
    : null;

/** Demo project key from the frozen API contract. */
export const JUNO_KEY = "jg_demo_key_cursorhack2026";
