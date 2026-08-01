# Repository Workflow

Use this Git workflow for every change in this repository:

1. Start from `main` and run `git pull --ff-only origin main` before changing files.
2. Create a scoped branch named `codex/<short-description>`.
3. Keep changes focused and preserve unrelated work already in the worktree.
4. Run the checks relevant to the files that changed.
5. Commit every intentional project change on the scoped branch with a descriptive message. Do not leave completed work only in the worktree.
6. Merge the scoped branch into local `main`, then push `main` to `origin`.
7. Verify that local `main` is clean and matches `origin/main` after the push.

Do not force-push or rewrite `main` history. If `main` cannot be fast-forwarded or a merge has conflicts, stop and resolve the discrepancy explicitly before continuing.

## Cursor Cloud specific instructions

Cloud agents use `.cursor/environment.json` (and `.cursor/Dockerfile`) for this repo.

- Dependencies are installed by the environment `install` script: backend requirements, editable `mcp`/`cli`, and `npm ci` for `frontend` and `packages/junoguard`.
- Gateway and dashboard terminals start automatically on `:8000` and `:5173`. Prefer `GET /ready` over `/health` when checking a production-shaped gateway.
- For production-shaped deploys, set `JUNO_ENV=production` and follow `docs/deploy.md`. Demo/local work can omit secrets and stay in mock mode.
- Never put `SUPABASE_SERVICE_ROLE_KEY`, `OPERATOR_TOKEN`, or `STREAM_TOKEN_SECRET` in `VITE_*` variables.
- Database migrations: `DATABASE_URL='postgres://…' ./supabase/apply.sh` (see `docs/deploy.md`).
- Secrets belong in the Cloud Agents dashboard Secrets tab, not in committed files.
