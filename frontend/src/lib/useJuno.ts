import { useCallback, useEffect, useRef, useState } from "react";
import { actionFromEvent, incidentFromEvent, projectFromEvent } from "./events";
import { apiUrl, dataSource, isLive, JUNO_KEY, supabase } from "./supabase";
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

/** Pause before re-issuing a stream token, so a 401 cannot become a hot loop. */
const TOKEN_RETRY_MS = 2_000;

/**
 * Billable spend is any action that cost money, whatever it was labelled.
 * `flag` is proceedable — the provider was called and the charge is real — so
 * filtering to `allow` here understated spend exactly when it mattered most,
 * above the 80% threshold where decisions start coming back flagged.
 */
function sumBillableCost(rows: AgentAction[]): number {
  let total = 0;
  for (const a of rows) if (a.cost_usd) total += Number(a.cost_usd);
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

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string | { detail?: string }; error?: string };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail === "object" && body.detail.detail) {
      return body.detail.detail;
    }
    if (body.error) return body.error;
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status})`;
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
  source: typeof dataSource;
  freshIds: Set<string>;
  killError: string | null;
  accessError: string | null;
  feedError: string | null;
  toggleSuspend: () => void;
}

export function useJuno(): JunoState {
  const [seed] = useState(() => {
    if (dataSource !== "mock") return { actions: [] as AgentAction[], incidents: [] as Incident[] };
    const a = seedActions();
    return { actions: a, incidents: seedIncidents(a) };
  });
  const [project, setProject] = useState<Project>(MOCK_PROJECT);
  // Adopted from /v1/guard/status in SSE mode — the sparkline's cap line has to
  // be the limit the gateway actually enforces, not the mock's.
  const [policy, setPolicy] = useState<Policy>(MOCK_POLICY);
  const [actions, setActions] = useState<AgentAction[]>(seed.actions);
  const [incidents, setIncidents] = useState<Incident[]>(seed.incidents);
  const [rate, setRate] = useState<number[]>([]);
  const [reqPerMin, setReqPerMin] = useState(0);
  const [suspendedAt, setSuspendedAt] = useState<number | null>(null);
  const [killError, setKillError] = useState<string | null>(null);
  const [killing, setKilling] = useState(false);
  // Set when the signed-in account has no readable project. Better to say so
  // than to render a dashboard of zeroes that looks like a quiet system.
  const [accessError, setAccessError] = useState<string | null>(null);
  // Set when the live feed itself cannot be authorized, as distinct from having
  // no project at all.
  const [feedError, setFeedError] = useState<string | null>(null);
  // Set when the gateway is configured but unreachable. An empty dashboard is
  // the one outcome the demo cannot survive, so we drop back to mock traffic
  // and say so in the feed badge rather than showing a blank screen.
  const [gatewayDown, setGatewayDown] = useState(false);
  const source: typeof dataSource = gatewayDown ? "mock" : dataSource;

  // Rollups accumulate. Deriving them from the visible buffer would make both
  // figures fall as old rows are trimmed off the end, which is worse than
  // wrong — it looks like the numbers are drifting on stage.
  const [spendToday, setSpendToday] = useState(
    () => (isLive ? 0 : SPEND_EARLIER_TODAY) + sumBillableCost(seed.actions),
  );
  const [blockedCount, setBlockedCount] = useState(
    () => seed.actions.filter((a) => a.decision === "block").length,
  );

  // Rows seeded on load must not animate in; only what arrives after does.
  const freshIds = useRef<Set<string>>(new Set());
  const seenIds = useRef<Set<string>>(new Set(seed.actions.map((a) => a.id)));
  const projectIdRef = useRef(MOCK_PROJECT.id);

  const suspended = project.status === "suspended";
  const suspendedRef = useRef(suspended);
  suspendedRef.current = suspended;

  const applyProjectStatus = useCallback((status: Project["status"], markTime: boolean) => {
    setProject((prev) => (prev.status === status ? prev : { ...prev, status }));
    if (status === "suspended" && markTime) setSuspendedAt(Date.now());
    if (status === "active") setSuspendedAt(null);
  }, []);

  const push = useCallback((incoming: AgentAction[], opts?: { fresh?: boolean }) => {
    if (incoming.length === 0) return;
    const fresh = opts?.fresh !== false;
    const novel = incoming.filter((a) => !seenIds.current.has(a.id));
    if (novel.length === 0) return;
    for (const a of novel) {
      seenIds.current.add(a.id);
      if (fresh) freshIds.current.add(a.id);
    }
    setSpendToday((prev) => prev + sumBillableCost(novel));
    setBlockedCount((prev) => prev + novel.filter((a) => a.decision === "block").length);
    setActions((prev) => {
      const merged = [...prev, ...novel].sort(
        (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
      );
      return merged.slice(-MAX_ROWS);
    });
  }, []);

  const pushIncident = useCallback((inc: Incident) => {
    setIncidents((prev) => [inc, ...prev.filter((i) => i.id !== inc.id)]);
  }, []);

  // ---- mock mode -----------------------------------------------------------
  useEffect(() => {
    if (source !== "mock") return;
    let timer: number;
    const tick = () => {
      push([suspendedRef.current ? suspendedAction() : nextAction()]);
      timer = window.setTimeout(tick, nextDelay());
    };
    timer = window.setTimeout(tick, nextDelay());
    return () => window.clearTimeout(timer);
  }, [push, source]);

  // ---- supabase mode -------------------------------------------------------
  useEffect(() => {
    if (dataSource !== "supabase" || !supabase) return;
    const db = supabase;
    let cancelled = false;

    (async () => {
      // Membership decides which project this dashboard shows. Ordering the
      // projects table and taking the first row was how one user could land on
      // another tenant's project.
      const { data: memberships, error: membershipError } = await supabase
        .from("project_members")
        .select("project_id")
        .order("created_at", { ascending: true })
        .limit(1);
      if (cancelled) return;
      if (membershipError) {
        setAccessError(membershipError.message);
        return;
      }
      const membership = memberships?.[0] as { project_id: string } | undefined;
      if (!membership) {
        setAccessError(
          "This account is not a member of any JunoGuard project. Ask an owner to add you.",
        );
        return;
      }

      const { data: projects } = await supabase
        .from("projects")
        .select("id, name, status")
        .eq("id", membership.project_id)
        .limit(1);
      const p = projects?.[0] as Project | undefined;
      if (!p || cancelled) {
        if (!cancelled) setAccessError("That project is no longer readable with this account.");
        return;
      }
      setAccessError(null);
      setProject(p);
      projectIdRef.current = p.id;

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
      if (rows) {
        const ordered = (rows as AgentAction[]).slice().reverse();
        for (const a of ordered) seenIds.current.add(a.id);
        setActions(ordered);
        setSpendToday(sumBillableCost(ordered));
        setBlockedCount(ordered.filter((a) => a.decision === "block").length);
      }
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
          if (row.status === "active") setSuspendedAt(null);
        },
      )
      .subscribe();

    return () => {
      cancelled = true;
      db.removeChannel(channel);
    };
  }, [push]);

  // ---- SSE mode (gateway fallback when Supabase is not configured) ---------
  useEffect(() => {
    if (dataSource !== "sse" || !apiUrl) return;
    let cancelled = false;
    let es: EventSource | null = null;
    let reached = false;

    (async () => {
      try {
        const statusRes = await fetch(`${apiUrl}/v1/guard/status`, {
          headers: { "X-Juno-Key": JUNO_KEY },
        });
        if (statusRes.ok && !cancelled) {
          reached = true;
          const status = (await statusRes.json()) as {
            project?: string;
            status?: string;
            spend_today_usd?: number;
            blocked_today?: number;
            daily_budget_usd?: number;
            max_requests_per_min?: number;
          };
          setProject((prev) => ({
            ...prev,
            name: status.project ?? prev.name,
            status: status.status === "suspended" ? "suspended" : "active",
          }));
          if (status.status === "suspended") setSuspendedAt(Date.now());
          if (typeof status.spend_today_usd === "number") setSpendToday(status.spend_today_usd);
          if (typeof status.blocked_today === "number") setBlockedCount(status.blocked_today);
          setPolicy((prev) => ({
            ...prev,
            daily_budget_usd: status.daily_budget_usd ?? prev.daily_budget_usd,
            max_requests_per_min: status.max_requests_per_min ?? prev.max_requests_per_min,
          }));
        }
      } catch {
        /* status is best-effort; the feed still works */
      }

      if (cancelled) return;

      let cursor = 0;
      try {
        const recentRes = await fetch(`${apiUrl}/v1/events/recent?limit=50`, {
          headers: { "X-Juno-Key": JUNO_KEY },
        });
        if (recentRes.ok && !cancelled) {
          reached = true;
          const body = (await recentRes.json()) as {
            cursor: number;
            events: { seq: number; type: string; data: Record<string, unknown> }[];
          };
          cursor = body.cursor ?? 0;
          const pid = projectIdRef.current;
          const backfillActions: AgentAction[] = [];
          const backfillIncidents: Incident[] = [];
          for (const ev of body.events ?? []) {
            if (ev.type === "action") {
              backfillActions.push(actionFromEvent(ev.data, pid));
            } else if (ev.type === "incident") {
              backfillIncidents.push(incidentFromEvent(ev.data, pid));
            } else if (ev.type === "project") {
              const p = projectFromEvent(ev.data);
              applyProjectStatus(p.status, p.status === "suspended");
            }
          }
          // History only — no enter animation, and don't re-accumulate rollups
          // that /v1/guard/status already seeded.
          for (const a of backfillActions) seenIds.current.add(a.id);
          setActions(backfillActions.slice(-MAX_ROWS));
          setIncidents(backfillIncidents.reverse());
        }
      } catch {
        /* handled by the reachability check below */
      }

      if (cancelled) return;

      // Gateway configured but not answering — usually uvicorn is not running,
      // or CORS rejected the origin. Fall back to mock rather than show nothing.
      if (!reached) {
        const fallback = seedActions();
        for (const a of fallback) seenIds.current.add(a.id);
        setActions(fallback);
        setIncidents(seedIncidents(fallback));
        setSpendToday(SPEND_EARLIER_TODAY + sumBillableCost(fallback));
        setBlockedCount(fallback.filter((a) => a.decision === "block").length);
        setPolicy(MOCK_POLICY);
        setGatewayDown(true);
        return;
      }

      // The stream is authenticated by a short-lived token rather than by the
      // project key: EventSource cannot send headers, and a long-lived key in a
      // query string ends up in logs, proxies and browser history.
      const connect = async (): Promise<void> => {
        if (cancelled) return;

        let token: string;
        try {
          const res = await fetch(`${apiUrl}/v1/events/token`, {
            method: "POST",
            headers: { "X-Juno-Key": JUNO_KEY },
          });
          if (!res.ok) {
            setFeedError(await readError(res));
            return;
          }
          token = ((await res.json()) as { token: string }).token;
        } catch (err) {
          setFeedError(err instanceof Error ? err.message : "Event feed unreachable");
          return;
        }
        if (cancelled) return;
        setFeedError(null);

        es = new EventSource(
          `${apiUrl}/v1/events/stream?cursor=${cursor}&token=${encodeURIComponent(token)}`,
        );

        es.addEventListener("action", (e) => {
          const data = JSON.parse((e as MessageEvent).data) as Record<string, unknown>;
          push([actionFromEvent(data, projectIdRef.current)]);
        });

        es.addEventListener("incident", (e) => {
          const data = JSON.parse((e as MessageEvent).data) as Record<string, unknown>;
          pushIncident(incidentFromEvent(data, projectIdRef.current));
        });

        es.addEventListener("project", (e) => {
          const data = JSON.parse((e as MessageEvent).data) as Record<string, unknown>;
          const p = projectFromEvent(data);
          applyProjectStatus(p.status, true);
          setKillError(null);
        });

        // The token authorizes a window, not a permanent subscription. Take a
        // fresh one rather than letting EventSource retry a URL that now 401s.
        const reconnect = () => {
          es?.close();
          es = null;
          if (!cancelled) window.setTimeout(() => void connect(), TOKEN_RETRY_MS);
        };
        es.addEventListener("expired", reconnect);
        es.onerror = reconnect;
      };

      await connect();
    })();

    return () => {
      cancelled = true;
      es?.close();
    };
  }, [push, pushIncident, applyProjectStatus]);

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
    if (source !== "mock") return;
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
  }, [push, source]);

  const toggleSuspend = useCallback(() => {
    if (killing) return;
    const next = suspendedRef.current ? "active" : "suspended";
    const path = next === "suspended" ? "suspend" : "resume";

    // Pure mock: flip locally. No gateway to disagree with us.
    if (!apiUrl) {
      applyProjectStatus(next, next === "suspended");
      setKillError(null);
      return;
    }

    // Live gateway: wait for the POST. Optimistic UI here is how we got a
    // dashboard that said suspended while traffic kept flowing.
    setKilling(true);
    setKillError(null);

    void (async () => {
      try {
        const res = await fetch(`${apiUrl}/v1/projects/${path}`, {
          method: "POST",
          headers: {
            "X-Juno-Key": JUNO_KEY,
            ...(next === "suspended" ? { "Content-Type": "application/json" } : {}),
          },
          body:
            next === "suspended"
              ? JSON.stringify({ reason: "Manual suspend from dashboard" })
              : undefined,
        });
        if (!res.ok) {
          setKillError(await readError(res));
          return;
        }
        const updated = (await res.json()) as { status?: string };
        const status = updated.status === "suspended" ? "suspended" : "active";
        applyProjectStatus(status, status === "suspended");
        setKillError(null);
      } catch (err) {
        setKillError(err instanceof Error ? err.message : "Kill switch unreachable");
      } finally {
        setKilling(false);
      }
    })();
  }, [apiUrl, applyProjectStatus, killing]);

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
    live: source !== "mock",
    source,
    freshIds: freshIds.current,
    killError,
    accessError,
    feedError,
    toggleSuspend,
  };
}
