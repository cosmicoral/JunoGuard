-- JG-001: authorization by project membership, and agent keys that are never
-- readable from the browser.
--
-- Before this migration every `authenticated` user could select every row in
-- projects, policies, agent_actions and incidents — and because projects stored
-- api_key in plaintext, that included the control key for every project.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Membership. Roles are ordered: viewer < operator < owner.
-- ---------------------------------------------------------------------------

create table if not exists public.project_members (
    project_id  uuid not null references public.projects(id) on delete cascade,
    user_id     uuid not null references auth.users(id) on delete cascade,
    role        text not null default 'viewer'
                check (role in ('viewer', 'operator', 'owner')),
    created_at  timestamptz not null default now(),
    primary key (project_id, user_id)
);

create index if not exists project_members_user_idx
    on public.project_members (user_id);

-- ---------------------------------------------------------------------------
-- Agent keys: store a hash and an identifying prefix, never the key.
-- ---------------------------------------------------------------------------

alter table public.projects add column if not exists api_key_hash   text;
alter table public.projects add column if not exists api_key_prefix text;
alter table public.projects add column if not exists key_rotated_at timestamptz;
alter table public.projects add column if not exists key_revoked_at timestamptz;

-- Migrate any plaintext key, then drop the column. Guarded so re-running the
-- migration after the column is gone is a no-op rather than a parse error.
do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'projects'
          and column_name = 'api_key'
    ) then
        execute $migrate$
            update public.projects
               set api_key_hash   = encode(digest(api_key, 'sha256'), 'hex'),
                   api_key_prefix = left(api_key, 12)
             where api_key_hash is null
        $migrate$;
        execute 'alter table public.projects drop column api_key';
    end if;
end
$$;

alter table public.projects alter column api_key_hash   set not null;
alter table public.projects alter column api_key_prefix set not null;

create unique index if not exists projects_api_key_hash_key
    on public.projects (api_key_hash);

-- ---------------------------------------------------------------------------
-- Membership predicates used by every read policy.
--
-- security definer so a policy on agent_actions does not have to satisfy
-- project_members' own RLS to answer "is this row mine?".
-- ---------------------------------------------------------------------------

create or replace function public.project_role(p_project_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select m.role
      from public.project_members m
     where m.project_id = p_project_id
       and m.user_id = (select auth.uid())
     limit 1;
$$;

create or replace function public.is_project_member(p_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select public.project_role(p_project_id) is not null;
$$;

revoke all on function public.project_role(uuid) from public;
revoke all on function public.is_project_member(uuid) from public;
grant execute on function public.project_role(uuid) to authenticated;
grant execute on function public.is_project_member(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Read policies: membership, not "is signed in".
-- ---------------------------------------------------------------------------

alter table public.project_members enable row level security;

drop policy if exists "members read own memberships" on public.project_members;
create policy "members read own memberships"
    on public.project_members for select to authenticated
    using (user_id = (select auth.uid()));

drop policy if exists "dashboard reads projects" on public.projects;
create policy "dashboard reads projects"
    on public.projects for select to authenticated
    using (public.is_project_member(id));

drop policy if exists "dashboard reads policies" on public.policies;
create policy "dashboard reads policies"
    on public.policies for select to authenticated
    using (public.is_project_member(project_id));

drop policy if exists "dashboard reads actions" on public.agent_actions;
create policy "dashboard reads actions"
    on public.agent_actions for select to authenticated
    using (public.is_project_member(project_id));

drop policy if exists "dashboard reads incidents" on public.incidents;
create policy "dashboard reads incidents"
    on public.incidents for select to authenticated
    using (public.is_project_member(project_id));

-- ---------------------------------------------------------------------------
-- Column privileges. RLS filters rows; this is what keeps the key hash out of
-- a `select *`. The gateway uses the service role and is unaffected.
-- ---------------------------------------------------------------------------

revoke all on public.projects from anon;
revoke all on public.projects from authenticated;
grant select (id, name, status, suspended_at, suspended_reason, created_at,
              api_key_prefix, key_rotated_at, key_revoked_at)
    on public.projects to authenticated;

revoke all on public.project_members from anon;
grant select on public.project_members to authenticated;

-- ---------------------------------------------------------------------------
-- Demo project. Keys are supplied by the operator; only the hash is stored.
-- Set junoguard.demo_project_key to seed a local demo project, e.g.
--   select set_config('junoguard.demo_project_key', 'jg_local_...', false);
-- ---------------------------------------------------------------------------

do $$
declare
    demo_key text := nullif(current_setting('junoguard.demo_project_key', true), '');
    demo_id  uuid;
begin
    if demo_key is null then
        return;
    end if;

    insert into public.projects (name, api_key_hash, api_key_prefix, status)
    values ('Demo Project', encode(digest(demo_key, 'sha256'), 'hex'),
            left(demo_key, 12), 'active')
    on conflict (api_key_hash) do nothing;

    select id into demo_id
      from public.projects
     where api_key_hash = encode(digest(demo_key, 'sha256'), 'hex');

    insert into public.policies (project_id)
    values (demo_id)
    on conflict (project_id) do nothing;
end
$$;
