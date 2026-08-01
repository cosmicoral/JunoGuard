-- JG-019: baseline schema for an empty database.
--
-- Later migrations (0001+) evolve this shape. Everything here is written to be
-- safely re-runnable: create-if-not-exists for tables, drop-if-exists for
-- policies, and catalog checks before altering the realtime publication.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

create table if not exists public.projects (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    api_key     text not null unique,
    status      text not null default 'active'
                check (status in ('active', 'suspended')),
    suspended_at    timestamptz,
    suspended_reason text,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- policies
-- ---------------------------------------------------------------------------

create table if not exists public.policies (
    project_id              uuid primary key references public.projects(id) on delete cascade,
    daily_budget_usd        numeric(10, 4) not null default 1.0000,
    per_request_budget_usd  numeric(10, 4) not null default 0.0500,
    max_request_tokens      integer        not null default 4000,
    max_requests_per_min    integer        not null default 8,
    block_severity          text           not null default 'malicious'
                            check (block_severity in ('malicious', 'suspicious', 'unknown')),
    suspend_on_malware      boolean        not null default true,
    updated_at              timestamptz    not null default now()
);

-- ---------------------------------------------------------------------------
-- agent_actions
-- ---------------------------------------------------------------------------

create table if not exists public.agent_actions (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references public.projects(id) on delete cascade,

    action_type  text not null
                 check (action_type in ('llm_call', 'package_install', 'status_check')),
    target       text not null,

    decision     text not null
                 check (decision in ('allow', 'flag', 'block')),
    reason       text not null,
    risk_level   text not null default 'low'
                 check (risk_level in ('low', 'medium', 'high', 'critical')),

    tokens_in    integer,
    tokens_out   integer,
    cost_usd     numeric(10, 6),

    metadata     jsonb not null default '{}'::jsonb,

    created_at   timestamptz not null default now()
);

create index if not exists agent_actions_project_time_idx
    on public.agent_actions (project_id, created_at desc);

create index if not exists agent_actions_spend_idx
    on public.agent_actions (project_id, action_type, created_at desc);

-- ---------------------------------------------------------------------------
-- incidents
-- ---------------------------------------------------------------------------

create table if not exists public.incidents (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references public.projects(id) on delete cascade,
    action_id   uuid references public.agent_actions(id) on delete set null,

    severity    text not null default 'medium'
                check (severity in ('low', 'medium', 'high', 'critical')),
    title       text not null,
    evidence    jsonb not null default '{}'::jsonb,
    status      text not null default 'open'
                check (status in ('open', 'resolved')),

    created_at  timestamptz not null default now(),
    resolved_at timestamptz
);

create index if not exists incidents_project_time_idx
    on public.incidents (project_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Spend rollup — later migrations redefine the billable filter.
-- ---------------------------------------------------------------------------

create or replace function public.daily_spend_usd(p_project_id uuid)
returns numeric
language sql
stable
as $$
    select coalesce(sum(cost_usd), 0)
    from public.agent_actions
    where project_id = p_project_id
      and decision = 'allow'
      and created_at >= date_trunc('day', now());
$$;

-- ---------------------------------------------------------------------------
-- Realtime — add each table only when the publication exists and the table is
-- not already a member. Re-applying must not fail midway.
-- ---------------------------------------------------------------------------

create or replace function public.junoguard_ensure_realtime(p_table regclass)
returns void
language plpgsql
as $$
declare
    v_schema text;
    v_name   text;
begin
    if not exists (
        select 1 from pg_publication where pubname = 'supabase_realtime'
    ) then
        return;
    end if;

    select n.nspname, c.relname into v_schema, v_name
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where c.oid = p_table;

    if exists (
        select 1
          from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = v_schema
           and tablename = v_name
    ) then
        return;
    end if;

    execute format(
        'alter publication supabase_realtime add table %I.%I',
        v_schema, v_name
    );
end
$$;

do $$
begin
    perform public.junoguard_ensure_realtime('public.agent_actions'::regclass);
    perform public.junoguard_ensure_realtime('public.incidents'::regclass);
    perform public.junoguard_ensure_realtime('public.projects'::regclass);
end
$$;

-- ---------------------------------------------------------------------------
-- RLS — enable here; 0001+ install the actual policies. Re-applying this
-- file must not weaken policies that later migrations already installed.
-- ---------------------------------------------------------------------------

alter table public.projects      enable row level security;
alter table public.policies      enable row level security;
alter table public.agent_actions enable row level security;
alter table public.incidents     enable row level security;
