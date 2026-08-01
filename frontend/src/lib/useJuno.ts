import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl, isLive, supabase } from "./supabase";
import type { AgentAction, Incident, Policy, Project } from "./types";
import {
  ACTIONS_EARLIER_TODAY,
  MOCK_POLICY,
  MOCK_PROJECT,
  SPEND_EARLIER_TODAY,
  burstActions,
  maliciousIncident,
  maliciousPackage,
  nextAction,
  nextDelay,
  seedActions,
  seedIncidents,
  suspendedAction,
} from "./mock";

const MAX_ROWS = 140;

/** The headline figure: a true count of the trailing minute. */
const RATE_WINDOW_MS = 60_000;

/**
 * The sparkline reads a shorter window so a burst spikes instead of smearing,
 * scaled back up to a per-minute rate. 26 samples, 4s apart — the seed covers
 * the full span, so the line is never ramping up from nothing on load.
 */
const SPARK_WINDOW_MS = 20_000;
const SPARK_SAMPLES = 26;
const SPARK_STEP_MS = 4_000;

function sumAllowedCost(rows: AgentAction[]): number {
  let total = 0;
  for (const a of rows) if (a.decision === "allow" && a.cost_usd) total += Number(a.cost_usd);
  return total;
}

function countWithin(stamps: number[], end: number, windowMs: number): number {
  let n = 0;
  for (const t of stamps) if (t > end - windowMs && t <= end) n++;
  return n;
}

/**
 * Recomputed from the action list rather than accumulated, so it stays honest
 * after any kind of insert (seed, live, burst).
 */
function rateSeries(actions: AgentAction[], now: number): number[] {
  const stamps = actions.map((a) => Date.parse(a.created_at));
  const scale = 60_000 / SPARK_WINDOW_MS;
  const out: number[] = [];
  for (let i = SPARK_SAMPLES - 1; i >= 0; i--) {
    out.push(countWithin(stamps, now - i * SPARK_STEP_MS, SPARK_WINDOW_MS) * scale);
  }
  return out;
}

function ratePerMinute(actions: AgentAction[], now: number): number {
  return countWithin(
    actions.map((a) => Date.parse(a.created_at)),
    now,
    RATE_WINDOW_MS,
  );
}

export interface JunoState {
  project: Project;
  policy: Policy;
  actions: AgentAction[];
  incidents: Incident[];
  spendToday: number;
  blockedCount: number;
  openIncidents: number;
  reqPerMin: number;
  rate: number[];
  actionsToday: number;
  suspended: boolean;
  suspendedAt: number | null;
  live: boolean;
  freshIds: Set<string>;
  toggleSuspend: () => void;
}

export function useJuno(): JunoState {
  const [seed] = useState(() => {
    const a = seedActions();
    return { actions: a, incidents: seedIncidents(a) };
  });
  const [project, setProject] = useState<Project>(MOCK_PROJECT);
  const [policy] = useState<Policy>(MOCK_POLICY);
  const [actions, setActions] = useState<AgentAction[]>(seed.actions);
  const [incidents, setIncidents] = useState<Incident[]>(seed.incidents);
  const [rate, setRate] = useState<number[]>([]);
  const [reqPerMin, setReqPerMin] = useState(0);
  const [suspendedAt, setSuspendedAt] = useState<number | null>(null);

  // Rollups accumulate. Deriving them from the visible buffer would make both
  // figures fall as old rows are trimmed off the end, which is worse than
  // wrong — it looks like the numbers are drifting on stage.
  const [spendToday, setSpendToday] = useState(
    () => (isLive ? 0 : SPEND_EARLIER_TODAY) + sumAllowedCost(seed.actions),
  );
  const [blockedCount, setBlockedCount] = useState(
    () => seed.actions.filter((a) => a.decision === "block").length,
  );

  // Rows seeded on load must not animate in; only what arrives after does.
  const freshIds = useRef<Set<string>>(new Set());

  const suspended = project.status === "suspended";
  const suspendedRef = useRef(suspended);
  suspendedRef.current = suspended;

  const push = useCallback((incoming: AgentAction[]) => {
    if (incoming.length === 0) return;
    for (const a of incoming) freshIds.current.add(a.id);
    setSpendToday((prev) => prev + sumAllowedCost(incoming));
    setBlockedCount((prev) => prev + incoming.filter((a) => a.decision === "block").length);
    setActions((prev) => {
      const merged = [...prev, ...incoming].sort(
        (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
      );
      return merged.slice(-MAX_ROWS);
    });
  }, []);

  // ---- mock mode -----------------------------------------------------------
  useEffect(() => {
    if (isLive) return;
    let timer: number;
    const tick = () => {
      push([suspendedRef.current ? suspendedAction() : nextAction()]);
      timer = window.setTimeout(tick, nextDelay());
    };
    timer = window.setTimeout(tick, nextDelay());
    return () => window.clearTimeout(timer);
  }, [push]);

  // ---- live mode -----------------------------------------------------------
  useEffect(() => {
    if (!isLive || !supabase) return;
    const db = supabase;
    let cancelled = false;

    (async () => {
      const { data: projects } = await supabase
        .from("projects")
        .select("id, name, status")
        .order("created_at", { ascending: true })
        .limit(1);
      const p = projects?.[0] as Project | undefined;
      if (!p || cancelled) return;
      setProject(p);

      const [{ data: rows }, { data: incs }] = await Promise.all([
        supabase
          .from("agent_actions")
          .select("*")
          .eq("project_id", p.id)
          .order("created_at", { ascending: false })
          .limit(MAX_ROWS),
        supabase.from("incidents").select("*").eq("project_id", p.id).eq("status", "open"),
      ]);
      if (cancelled) return;
      if (rows) setActions((rows as AgentAction[]).slice().reverse());
      setIncidents((incs as Incident[]) ?? []);
    })();

    const channel = supabase
      .channel("juno")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "agent_actions" },
        (payload) => push([payload.new as AgentAction]),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "incidents" },
        (payload) => {
          const row = payload.new as Incident;
          setIncidents((prev) => [row, ...prev.filter((i) => i.id !== row.id)]);
        },
      )
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "projects" },
        (payload) => {
          const row = payload.new as Project;
          setProject((prev) => (prev.id === row.id ? { ...prev, ...row } : prev));
          if (row.status === "suspended") setSuspendedAt(Date.now());
        },
      )
      .subscribe();

    return () => {
      cancelled = true;
      db.removeChannel(channel);
    };
  }, [push]);

  // ---- rolling rate --------------------------------------------------------
  useEffect(() => {
    const recompute = () => {
      const now = Date.now();
      setRate(rateSeries(actions, now));
      setReqPerMin(ratePerMinute(actions, now));
    };
    recompute();
    const timer = window.setInterval(recompute, 1000);
    return () => window.clearInterval(timer);
  }, [actions]);

  // ---- demo controls (invisible; safe on stage) ----------------------------
  useEffect(() => {
    if (isLive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "b" || e.key === "B") {
        const action = maliciousPackage();
        push([action]);
        setIncidents((prev) => [maliciousIncident(action), ...prev]);
      }
      if (e.key === "r" || e.key === "R") push(burstActions());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [push]);

  const toggleSuspend = useCallback(() => {
    const next = suspendedRef.current ? "active" : "suspended";
    setProject((prev) => ({ ...prev, status: next }));
    setSuspendedAt(next === "suspended" ? Date.now() : null);
    if (apiUrl) {
      // Best effort. The dashboard never waits on the network to change state.
      void fetch(`${apiUrl}/projects/${project.id}/${next === "suspended" ? "suspend" : "resume"}`, {
        method: "POST",
      }).catch(() => {});
    }
  }, [project.id]);

  return {
    project,
    policy,
    actions,
    incidents,
    spendToday,
    blockedCount,
    openIncidents: incidents.filter((i) => i.status === "open").length,
    reqPerMin,
    rate,
    actionsToday: (isLive ? 0 : ACTIONS_EARLIER_TODAY) + actions.length,
    suspended,
    suspendedAt,
    live: isLive,
    freshIds: freshIds.current,
    toggleSuspend,
  };
}
