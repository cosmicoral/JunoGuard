-- JG-004 follow-up: the SQL default disagreed with the engine's default.
--
-- The decision engine treats `unknown` as the floor — a package nobody has
-- established a reputation for is not one an agent should install unattended —
-- but the policies table still handed new projects `malicious`. A project
-- created through the database would silently be more permissive than one
-- running on the engine's own defaults, which is the kind of disagreement
-- nobody notices until it matters.

alter table public.policies
    alter column block_severity set default 'unknown';

-- Existing rows are left alone on purpose. A project already carrying
-- `malicious` may have been set that way deliberately, and quietly tightening a
-- running project's policy is an operator's decision, not a migration's.
