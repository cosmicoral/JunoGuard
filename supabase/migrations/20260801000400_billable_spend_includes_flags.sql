-- JG-003: charged flags belong in the daily total.
--
-- `flag` is a proceedable decision: the gateway calls the provider and the
-- money is spent. The rollup counted only `decision = 'allow'`, so once spend
-- crossed the 80% warning threshold and decisions started coming back as
-- `flag`, real charges stopped advancing the total — and the daily cap could be
-- walked straight past.
--
-- Billable spend is now defined by cost, not by label.

create or replace function public.daily_spend_usd(p_project_id uuid)
returns numeric
language sql
stable
as $$
    select coalesce(sum(cost_usd), 0)
    from public.agent_actions
    where project_id = p_project_id
      and cost_usd > 0
      and created_at >= date_trunc('day', now());
$$;
