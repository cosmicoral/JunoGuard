#!/usr/bin/env bash
#
# Apply JunoGuard's migrations in order.
#
#   DATABASE_URL=postgres://... ./supabase/apply.sh
#   DATABASE_URL=postgres://... ./supabase/apply.sh --dry-run
#
# Migrations are named with a sortable prefix and are written to be safely
# re-runnable, so applying this to an already-migrated database is a no-op
# rather than an error. Each file runs in its own transaction: a failure leaves
# that migration unapplied instead of half-applied.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dry_run=false
[[ "${1:-}" == "--dry-run" ]] && dry_run=true

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required." >&2
    echo "Supabase: Project Settings → Database → Connection string (URI)." >&2
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "psql is not on PATH. Install the PostgreSQL client." >&2
    exit 2
fi

shopt -s nullglob
migrations=("$here"/migrations/*.sql)
if (( ${#migrations[@]} == 0 )); then
    echo "No migrations found in $here/migrations" >&2
    exit 1
fi

echo "Applying ${#migrations[@]} migration(s):"
for file in "${migrations[@]}"; do
    name="$(basename "$file")"
    if $dry_run; then
        echo "  would apply  $name"
        continue
    fi
    echo "  applying     $name"
    # --single-transaction so a failure rolls the whole file back.
    # ON_ERROR_STOP so it does not carry on past a broken statement.
    psql "$DATABASE_URL" \
        --quiet \
        --single-transaction \
        --set ON_ERROR_STOP=1 \
        --file "$file"
done

$dry_run || echo "Done. Re-running this script is safe."
