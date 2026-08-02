-- JG-002: make rate and budget enforcement atomic.
--
-- Policy evaluation used to read the current spend and request count, call the
-- provider, and record the action as three separate operations. Twenty
-- concurrent requests against an 8/min limit all observed the same pre-limit
-- state and all proceeded.
--
-- A reservation is taken under a per-project advisory lock before the provider
-- is called, and counts toward both limits until it is released. Concurrency is
-- therefore bounded by the policy rather than by luck.

create extension if not exists "pgcrypto";

create table if not exists public.spend_reservations (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references public.projects(id) on delete cascade,
    est_cost_usd numeric(10, 6) not null default 0,
    created_at   timestamptz not null default now(),
    released_at  timestamptz
);

create index if not exists spend_reservations_open_idx
    on public.spend_reservations (project_id, created_at desc)
    where released_at is null;

-- Replaying a request must not buy a second completion from the provider.
create table if not exists public.idempotency_keys (
    project_id uuid not null references public.projects(id) on delete cascade,
    key        text not null,
    response   jsonb not null,
    created_at timestamptz not null default now(),
    primary key (project_id, key)
);

create index if not exists idempotency_keys_created_idx
    on public.idempotency_keys (created_at);

-- Reservations are never browser-readable.
alter table public.spend_reservations enable row level security;
alter table public.idempotency_keys   enable row level security;
revoke all on public.spend_reservations from anon, authenticated;
revoke all on public.idempotency_keys   from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Reserve one request's worth of rate and budget, atomically.
--
-- Returns one of:
--   {"outcome": "ok", "reservation_id": uuid, "spend_today": n, "requests_last_min": n}
--   {"outcome": "rate_exceeded",   "spend_today": n, "requests_last_min": n}
--   {"outcome": "budget_exceeded", "spend_today": n, "requests_last_min": n}
--
-- The caller owns the decision text; this function owns the counters. Keeping
-- reason strings in one language (Python) and atomicity in the database avoids
-- two implementations of the same rule drifting apart.
-- ---------------------------------------------------------------------------

create or replace function public.reserve_action(
    p_project_id   uuid,
    p_est_cost     numeric,
    p_daily_budget numeric,
    p_max_per_min  integer,
    p_stale_after  interval default interval '2 minutes'
)
returns jsonb
language plpgsql
as $$
declare
    v_spend numeric;
    v_rate  integer;
    v_id    uuid;
begin
    -- Serialises every reserve for this project for the life of this
    -- statement's transaction, which is what closes the race.
    perform pg_advisory_xact_lock(hashtextextended(p_project_id::text, 0));

    -- A crashed request must not hold budget forever.
    update public.spend_reservations
       set released_at = now()
     where project_id = p_project_id
       and released_at is null
       and created_at < now() - p_stale_after;

    -- Billable spend is any charged action, whatever the gateway decided to
    -- label it, plus everything currently reserved.
    select coalesce(sum(cost_usd), 0) into v_spend
      from public.agent_actions
     where project_id = p_project_id
       and cost_usd > 0
       and created_at >= date_trunc('day', now());

    select v_spend + coalesce(sum(est_cost_usd), 0) into v_spend
      from public.spend_reservations
     where project_id = p_project_id
       and released_at is null;

    select count(*) into v_rate
      from public.agent_actions
     where project_id = p_project_id
       and action_type <> 'status_check'
       and created_at >= now() - interval '1 minute';

    select v_rate + count(*) into v_rate
      from public.spend_reservations
     where project_id = p_project_id
       and released_at is null
       and created_at >= now() - interval '1 minute';

    if v_rate >= p_max_per_min then
        return jsonb_build_object(
            'outcome', 'rate_exceeded',
            'spend_today', v_spend,
            'requests_last_min', v_rate
        );
    end if;

    if v_spend + p_est_cost > p_daily_budget then
        return jsonb_build_object(
            'outcome', 'budget_exceeded',
            'spend_today', v_spend,
            'requests_last_min', v_rate
        );
    end if;

    insert into public.spend_reservations (project_id, est_cost_usd)
    values (p_project_id, p_est_cost)
    returning id into v_id;

    return jsonb_build_object(
        'outcome', 'ok',
        'reservation_id', v_id,
        'spend_today', v_spend,
        'requests_last_min', v_rate
    );
end
$$;

create or replace function public.release_reservation(p_id uuid)
returns void
language sql
as $$
    update public.spend_reservations
       set released_at = now()
     where id = p_id
       and released_at is null;
$$;

revoke all on function public.reserve_action(uuid, numeric, numeric, integer, interval)
    from anon, authenticated;
revoke all on function public.release_reservation(uuid) from anon, authenticated;
