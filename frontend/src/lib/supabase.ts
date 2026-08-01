import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isLive = Boolean(url && anonKey);

export const supabase: SupabaseClient | null = isLive
  ? createClient(url!, anonKey!, { realtime: { params: { eventsPerSecond: 20 } } })
  : null;

export const apiUrl = import.meta.env.VITE_API_URL as string | undefined;
