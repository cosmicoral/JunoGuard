-- Require a Supabase Auth session for all browser-readable dashboard data.
-- The service-role gateway continues to bypass RLS.

drop policy if exists "dashboard reads projects" on public.projects;
create policy "dashboard reads projects"
    on public.projects for select to authenticated
    using ((select auth.uid()) is not null);

drop policy if exists "dashboard reads policies" on public.policies;
create policy "dashboard reads policies"
    on public.policies for select to authenticated
    using ((select auth.uid()) is not null);

drop policy if exists "dashboard reads actions" on public.agent_actions;
create policy "dashboard reads actions"
    on public.agent_actions for select to authenticated
    using ((select auth.uid()) is not null);

drop policy if exists "dashboard reads incidents" on public.incidents;
create policy "dashboard reads incidents"
    on public.incidents for select to authenticated
    using ((select auth.uid()) is not null);
