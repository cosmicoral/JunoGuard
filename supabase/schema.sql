-- JunoGuard schema
-- One action table for both lanes, which is what lets a single kill switch
-- cover everything an agent can do.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

create table if not exists projects (
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
-- One row per project. Every hot-path decision reads from here.
-- ---------------------------------------------------------------------------

create table if not exists policies (
    project_id              uuid primary key references projects(id) on delete cascade,
    daily_budget_usd        numeric(10, 4) not null default 1.0000,
    per_request_budget_usd  numeric(10, 4) not null default 0.0500,
    max_request_tokens      integer        not null default 4000,
    max_requests_per_min    integer        not null default 8,
    -- lowest Ossprey severity that causes a hard block
    block_severity          text           not null default 'malicious'
                            check (block_severity in ('malicious', 'suspicious', 'unknown')),
    -- suspend the whole project on a Lane A block, not just refuse the install
    suspend_on_malware      boolean        not null default true,
    updated_at              timestamptz    not null default now()
);

-- ---------------------------------------------------------------------------
-- agent_actions
-- Every decision Juno makes, both lanes, in one timeline.
-- ---------------------------------------------------------------------------

create table if not exists agent_actions (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references projects(id) on delete cascade,

    action_type  text not null
                 check (action_type in ('llm_call', 'package_install', 'status_check')),
    target       text not null,          -- package name, or model id

    decision     text not null
                 check (decision in ('allow', 'flag', 'block')),
    reason       text not null,
    risk_level   text not null default 'low'
                 check (risk_level in ('low', 'medium', 'high', 'critical')),

    -- Lane B only; null for package installs
    tokens_in    integer,
    tokens_out   integer,
    cost_usd     numeric(10, 6),

    -- Lane A only; Ossprey verdict payload, blast radius, sandbox result
    metadata     jsonb not null default '{}'::jsonb,

    created_at   timestamptz not null default now()
);

create index if not exists agent_actions_project_time_idx
    on agent_actions (project_id, created_at desc);

-- Powers the rate limiter and the daily spend rollup.
create index if not exists agent_actions_spend_idx
    on agent_actions (project_id, action_type, created_at desc);

-- ---------------------------------------------------------------------------
-- incidents
-- ---------------------------------------------------------------------------

create table if not exists incidents (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects(id) on delete cascade,
    action_id   uuid references agent_actions(id) on delete set null,

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
    on incidents (project_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Spend rollup — read on every Lane B request, so keep it cheap.
-- ---------------------------------------------------------------------------

create or replace function daily_spend_usd(p_project_id uuid)
returns numeric
language sql
stable
as $$
    select coalesce(sum(cost_usd), 0)
    from agent_actions
    where project_id = p_project_id
      and decision = 'allow'
      and created_at >= date_trunc('day', now());
$$;

-- ---------------------------------------------------------------------------
-- Realtime — drives the live dashboard.
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table agent_actions;
alter publication supabase_realtime add table incidents;
alter publication supabase_realtime add table projects;

-- ---------------------------------------------------------------------------
-- RLS
-- The gateway uses the service role and bypasses these. The dashboard reads
-- with the anon key, so reads are open and writes are closed: nothing but
-- Juno may record a decision.
-- ---------------------------------------------------------------------------

alter table projects      enable row level security;
alter table policies      enable row level security;
alter table agent_actions enable row level security;
alter table incidents     enable row level security;

create policy "dashboard reads projects"
    on projects for select using (true);

create policy "dashboard reads policies"
    on policies for select using (true);

create policy "dashboard reads actions"
    on agent_actions for select using (true);

create policy "dashboard reads incidents"
    on incidents for select using (true);

-- ---------------------------------------------------------------------------
-- Demo seed
-- ---------------------------------------------------------------------------

insert into projects (name, api_key, status)
values ('Demo Project', 'jg_demo_key_cursorhack2026', 'active')
on conflict (api_key) do nothing;

insert into policies (project_id)
select id from projects where api_key = 'jg_demo_key_cursorhack2026'
on conflict (project_id) do nothing;
