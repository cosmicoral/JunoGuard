-- JunoGuard schema — readable snapshot of the intended end state.
--
-- Do not apply this file directly to a database. Schema evolution lives in
-- supabase/migrations/ and is applied with:
--
--   DATABASE_URL=postgres://... ./supabase/apply.sh
--
-- That path is re-runnable on empty and already-migrated databases (JG-019).
-- One action table for both lanes, which is what lets a single kill switch
-- cover everything an agent can do.

create extension if not exists "pgcrypto";

-- Hosted Supabase installs pgcrypto into `extensions`; a stock Postgres puts it
-- in `public`. Naming both keeps digest() resolvable either way — Postgres
-- ignores a schema in search_path that does not exist.
set search_path = public, extensions, pg_temp;

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

-- The agent key is never stored. Only its SHA-256 hash (looked up on every
-- guarded call) and a short prefix for identifying a key in the dashboard.
create table if not exists projects (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    api_key_hash    text not null unique,
    api_key_prefix  text not null,
    key_rotated_at  timestamptz,
    key_revoked_at  timestamptz,
    status      text not null default 'active'
                check (status in ('active', 'suspended')),
    suspended_at    timestamptz,
    suspended_reason text,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- project_members
-- Authorization for every browser read. Roles are ordered:
-- viewer < operator < owner.
-- ---------------------------------------------------------------------------

create table if not exists project_members (
    project_id  uuid not null references projects(id) on delete cascade,
    user_id     uuid not null references auth.users(id) on delete cascade,
    role        text not null default 'viewer'
                check (role in ('viewer', 'operator', 'owner')),
    created_at  timestamptz not null default now(),
    primary key (project_id, user_id)
);

create index if not exists project_members_user_idx
    on project_members (user_id);

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
    block_severity          text           not null default 'unknown'
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
-- control_events
-- Every human decision about project state. Append-only: an audit row that can
-- be edited is not an audit row.
-- ---------------------------------------------------------------------------

create table if not exists control_events (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references projects(id) on delete cascade,

    action          text not null check (action in ('suspend', 'resume')),
    previous_status text not null,
    next_status     text not null,

    actor_kind      text not null check (actor_kind in ('user', 'operator_token')),
    actor_id        text not null,
    actor_role      text not null,
    actor_email     text,

    reason          text,
    incident_id     uuid references incidents(id) on delete set null,

    created_at      timestamptz not null default now()
);

create index if not exists control_events_project_time_idx
    on control_events (project_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Spend rollup — read on every Lane B request, so keep it cheap.
--
-- Billable spend is any action that cost money, whatever the gateway labelled
-- it. `flag` is proceedable: the provider is called and the charge is real.
-- ---------------------------------------------------------------------------

create or replace function daily_spend_usd(p_project_id uuid)
returns numeric
language sql
stable
as $$
    select coalesce(sum(cost_usd), 0)
    from agent_actions
    where project_id = p_project_id
      and cost_usd > 0
      and created_at >= date_trunc('day', now());
$$;

-- ---------------------------------------------------------------------------
-- Realtime — drives the live dashboard.
-- Add each table only when the publication exists and the table is not
-- already a member. Re-applying must not fail midway (JG-019).
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
-- Membership predicates
-- security definer so a policy on agent_actions does not itself have to
-- satisfy project_members' RLS to answer "is this row mine?".
-- ---------------------------------------------------------------------------

create or replace function project_role(p_project_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select m.role
      from project_members m
     where m.project_id = p_project_id
       and m.user_id = (select auth.uid())
     limit 1;
$$;

create or replace function is_project_member(p_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select project_role(p_project_id) is not null;
$$;

revoke all on function project_role(uuid) from public;
revoke all on function is_project_member(uuid) from public;
grant execute on function project_role(uuid) to authenticated;
grant execute on function is_project_member(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- RLS
-- The gateway uses the service role and bypasses these. The browser client
-- carries the signed-in user's JWT, and reads are scoped to the projects that
-- user is a member of — being signed in is not itself authorization.
-- Writes remain closed: nothing but Juno may record a decision.
-- ---------------------------------------------------------------------------

alter table projects        enable row level security;
alter table project_members enable row level security;
alter table policies       enable row level security;
alter table agent_actions  enable row level security;
alter table incidents      enable row level security;
alter table control_events enable row level security;

drop policy if exists "members read own memberships" on project_members;
create policy "members read own memberships"
    on project_members for select to authenticated
    using (user_id = (select auth.uid()));

drop policy if exists "dashboard reads projects" on projects;
create policy "dashboard reads projects"
    on projects for select to authenticated
    using (is_project_member(id));

drop policy if exists "dashboard reads policies" on policies;
create policy "dashboard reads policies"
    on policies for select to authenticated
    using (is_project_member(project_id));

drop policy if exists "dashboard reads actions" on agent_actions;
create policy "dashboard reads actions"
    on agent_actions for select to authenticated
    using (is_project_member(project_id));

drop policy if exists "dashboard reads incidents" on incidents;
create policy "dashboard reads incidents"
    on incidents for select to authenticated
    using (is_project_member(project_id));

drop policy if exists "members read control events" on control_events;
create policy "members read control events"
    on control_events for select to authenticated
    using (is_project_member(project_id));

-- Append-only, enforced rather than assumed.
create or replace function control_events_are_immutable()
returns trigger
language plpgsql
as $$
begin
    raise exception 'control_events is append-only';
end
$$;

drop trigger if exists control_events_no_update on control_events;
create trigger control_events_no_update
    before update or delete on control_events
    for each row execute function control_events_are_immutable();

-- ---------------------------------------------------------------------------
-- Column privileges
-- RLS filters rows; this is what keeps the key hash out of a `select *`.
-- ---------------------------------------------------------------------------

revoke all on projects from anon;
revoke all on projects from authenticated;
grant select (id, name, status, suspended_at, suspended_reason, created_at,
              api_key_prefix, key_rotated_at, key_revoked_at)
    on projects to authenticated;

revoke all on project_members from anon;
grant select on project_members to authenticated;

-- ---------------------------------------------------------------------------
-- Demo seed
-- No key is baked in. Supply one for the session and only its hash is stored:
--   select set_config('junoguard.demo_project_key', 'jg_local_yourkey', false);
-- Then grant yourself access:
--   insert into project_members (project_id, user_id, role)
--   values ('<project id>', '<your auth.users id>', 'owner');
-- ---------------------------------------------------------------------------

do $$
declare
    demo_key text := nullif(current_setting('junoguard.demo_project_key', true), '');
    demo_id  uuid;
begin
    if demo_key is null then
        return;
    end if;

    insert into projects (name, api_key_hash, api_key_prefix, status)
    values ('Demo Project', encode(digest(demo_key, 'sha256'), 'hex'),
            left(demo_key, 12), 'active')
    on conflict (api_key_hash) do nothing;

    select id into demo_id
      from projects
     where api_key_hash = encode(digest(demo_key, 'sha256'), 'hex');

    insert into policies (project_id)
    values (demo_id)
    on conflict (project_id) do nothing;
end
$$;
