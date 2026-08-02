-- JG-015: an immutable record of every human decision about project state.
--
-- Suspend and resume are the two most consequential actions in the product and
-- neither left a trace of who took it, why, from what state, or which incident
-- was reviewed first. "Someone reset it at some point" is not an answer an
-- incident review can use.

create table if not exists public.control_events (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references public.projects(id) on delete cascade,

    action          text not null check (action in ('suspend', 'resume')),
    previous_status text not null,
    next_status     text not null,

    -- Who. actor_kind distinguishes an identified person from the shared
    -- operator token, so the two are never confused in a review.
    actor_kind      text not null check (actor_kind in ('user', 'operator_token')),
    actor_id        text not null,
    actor_role      text not null,
    actor_email     text,

    -- Why, and what they looked at first.
    reason          text,
    incident_id     uuid references public.incidents(id) on delete set null,

    created_at      timestamptz not null default now()
);

create index if not exists control_events_project_time_idx
    on public.control_events (project_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Immutable: members may read their own project's history, and nobody may
-- rewrite it. The gateway writes with the service role.
-- ---------------------------------------------------------------------------

alter table public.control_events enable row level security;

drop policy if exists "members read control events" on public.control_events;
create policy "members read control events"
    on public.control_events for select to authenticated
    using (public.is_project_member(project_id));

revoke all on public.control_events from anon;
grant select on public.control_events to authenticated;

-- Belt and braces against a future policy that grants writes by accident: an
-- audit row that can be edited is not an audit row.
create or replace function public.control_events_are_immutable()
returns trigger
language plpgsql
as $$
begin
    raise exception 'control_events is append-only';
end
$$;

drop trigger if exists control_events_no_update on public.control_events;
create trigger control_events_no_update
    before update or delete on public.control_events
    for each row execute function public.control_events_are_immutable();
