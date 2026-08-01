#!/usr/bin/env bash
#
# Prove the migration chain is re-runnable on an empty database and on an
# already-migrated one (JG-019).
#
# Spins up a temporary local Postgres (no Docker required), stubs the
# Supabase auth.users table and realtime publication that the migrations
# expect, applies every migration twice, and checks the end-state catalog.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workdir="$(mktemp -d "${TMPDIR:-/tmp}/junoguard-migrate.XXXXXX")"
cleanup() {
    if [[ -n "${PG_PID:-}" ]] && kill -0 "$PG_PID" 2>/dev/null; then
        kill "$PG_PID" 2>/dev/null || true
        wait "$PG_PID" 2>/dev/null || true
    fi
    rm -rf "$workdir"
}
trap cleanup EXIT

export PGDATA="$workdir/data"
export PGHOST="$workdir"
export PGPORT=55432
export PGUSER="${USER:-junoguard}"
export PGDATABASE=junoguard
socket_dir="$workdir"

initdb --auth=trust --username="$PGUSER" --pgdata="$PGDATA" >/dev/null
# Publications that support realtime need logical decoding.
echo "wal_level = logical" >> "$PGDATA/postgresql.conf"
# Listen on a Unix socket only — no TCP, no clash with a local server.
pg_ctl -D "$PGDATA" -o "-k $socket_dir -p $PGPORT -c listen_addresses=''" -w start >/dev/null
PG_PID="$(head -n1 "$PGDATA/postmaster.pid")"

createdb -h "$socket_dir" -p "$PGPORT" "$PGDATABASE"

psql -h "$socket_dir" -p "$PGPORT" -d "$PGDATABASE" -v ON_ERROR_STOP=1 <<'SQL'
-- Minimal Supabase stubs so the migration chain can run outside a hosted
-- project. Real Supabase already provides these.
create schema if not exists auth;
create table if not exists auth.users (
    id uuid primary key
);
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin bypassrls;
    end if;
end
$$;
create publication supabase_realtime;
SQL

export DATABASE_URL="postgresql://$PGUSER@/$PGDATABASE?host=$socket_dir&port=$PGPORT"

echo "== first apply (empty database) =="
"$here/apply.sh"

echo "== second apply (already migrated) =="
"$here/apply.sh"

echo "== catalog checks =="
psql -h "$socket_dir" -p "$PGPORT" -d "$PGDATABASE" -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
    -- Core + evolved tables
    perform 'public.projects'::regclass;
    perform 'public.policies'::regclass;
    perform 'public.agent_actions'::regclass;
    perform 'public.incidents'::regclass;
    perform 'public.project_members'::regclass;
    perform 'public.spend_reservations'::regclass;
    perform 'public.idempotency_keys'::regclass;
    perform 'public.control_events'::regclass;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'projects'
          and column_name = 'api_key_hash'
    ) then
        raise exception 'projects.api_key_hash missing';
    end if;

    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'projects'
          and column_name = 'api_key'
    ) then
        raise exception 'projects.api_key should have been dropped';
    end if;

    if not exists (
        select 1 from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'agent_actions'
    ) then
        raise exception 'agent_actions missing from supabase_realtime';
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'projects'
          and policyname = 'dashboard reads projects'
    ) then
        raise exception 'membership read policy missing on projects';
    end if;
end
$$;
SQL

echo "Migrations are re-runnable and leave the expected schema."
