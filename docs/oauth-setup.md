# JunoGuard — Google & GitHub OAuth via Supabase Auth

Console runbook. Every step here needs a browser and a human; none of it can be
scripted. The repo-side wiring (schema, env vars, route guard) is already done —
see [What is already done](#what-is-already-done) at the end.

**Never paste a client secret into a chat, an issue, or a commit.** Secrets go
into the Supabase dashboard and nowhere else. The anon / publishable key is
designed to be public and is safe in the frontend bundle.

---

## The one value everything hangs off

The **project ref** is the subdomain of your Supabase project URL.

For this project it is:

```
izvcwrgfwobmmmtpubdi
```

Find it any time under **Supabase Dashboard → Project Settings → General →
Reference ID**, or read it out of the project URL:
`https://supabase.com/dashboard/project/izvcwrgfwobmmmtpubdi`.

From it comes the **provider callback URL**, which is the single value that goes
into *both* Google and GitHub:

```
https://izvcwrgfwobmmmtpubdi.supabase.co/auth/v1/callback
```

This URL points at Supabase, **not** at junoguard.com. That trips people up:
the browser goes to Google, Google returns to *Supabase*, and Supabase then
returns to your app at `/auth/callback`. Two different callbacks, two different
jobs. The one your app serves (`/auth/callback`) is configured separately, in
[step 4](#4-supabase--url-configuration).

---

## 0. Supabase project creation

Already done for JunoGuard, so skip to step 1. Recorded for reproducibility:

1. Go to <https://supabase.com/dashboard> → **New project**.
2. Organization: **HeySalad**. Name: `JunoGuard`. Region: **West EU (Ireland)**.
3. Set a database password and store it in a password manager. You will need it
   for `supabase link` and `psql`, not for OAuth.
4. Wait for provisioning (~2 min), then copy the **Reference ID** from
   **Project Settings → General**.

The current project: `JunoGuard`, ref `izvcwrgfwobmmmtpubdi`, West EU (Ireland).

---

## 1. Google Cloud Console

### 1a. OAuth consent screen

1. <https://console.cloud.google.com> → pick or create a project (e.g.
   `junoguard`) using the project picker in the top bar.
2. Left nav → **APIs & Services → OAuth consent screen**.
3. **User Type**: *External* → **Create**.
4. **App information**
   - App name: `JunoGuard`
   - User support email: `peter@heysalad.io`
5. **App domain** (optional for testing, required before Google will verify a
   public app)
   - Application home page: `https://junoguard.com`
6. **Developer contact information**: `peter@heysalad.io`
7. **Save and continue**.
8. **Scopes**: no changes needed. Supabase requests `email`, `profile`, and
   `openid`, which are non-sensitive defaults. **Save and continue**.
9. **Test users**: while the app is in *Testing* status, only listed accounts
   can sign in. Add every Google account that will be used on stage —
   including your own. **Save and continue**.

> If sign-in fails with **`Error 403: access_denied`**, the account is not on
> the test-user list, or the app is in Testing and the account was never added.
> Either add it here, or click **Publish app** to open it to any Google account.

### 1b. Web application credentials

1. Left nav → **APIs & Services → Credentials**.
2. **+ Create Credentials → OAuth client ID**.
3. **Application type**: *Web application*.
4. **Name**: `JunoGuard Web`.
5. **Authorized JavaScript origins** — not required by Supabase's server-side
   flow. Leave empty.
6. **Authorized redirect URIs** → **+ Add URI**, and paste exactly:

   ```
   https://izvcwrgfwobmmmtpubdi.supabase.co/auth/v1/callback
   ```

   No trailing slash. Not your app's domain. This is the value from
   [the section above](#the-one-value-everything-hangs-off).

7. **Create**. Google shows a **Client ID** and a **Client secret**.
8. Leave this dialog open, or copy both straight into your password manager.
   They go into Supabase in [step 3](#3-supabase--enable-the-providers).

> **`Error 400: redirect_uri_mismatch`** at sign-in means the redirect URI here
> does not byte-for-byte match what Supabase sent. Check for a trailing slash,
> `http` vs `https`, or your app's domain pasted here by mistake.

---

## 2. GitHub

1. <https://github.com> → your avatar → **Settings**.
2. Left nav, bottom → **Developer settings**.
3. **OAuth Apps** → **New OAuth App**.
   (Use *OAuth Apps*, not *GitHub Apps* — Supabase expects an OAuth App.)
4. Fill in:
   - **Application name**: `JunoGuard`
   - **Homepage URL**: `https://junoguard.com`
   - **Application description**: optional
   - **Authorization callback URL** — the same Supabase URL as Google:

     ```
     https://izvcwrgfwobmmmtpubdi.supabase.co/auth/v1/callback
     ```

5. **Register application**.
6. Copy the **Client ID**. Then **Generate a new client secret** and copy that
   too — GitHub shows the secret **once**, and you cannot read it again. If you
   lose it, generate another and update Supabase.

> A GitHub OAuth App accepts only **one** callback URL. That is fine: every
> environment (localhost, Vercel preview, production) routes through the single
> Supabase callback above. This is exactly why Supabase sits in the middle.

---

## 3. Supabase — enable the providers

1. <https://supabase.com/dashboard/project/izvcwrgfwobmmmtpubdi> →
   **Authentication** (left nav) → **Sign In / Providers**.
2. Find **Google** in the list → expand it.
   - Toggle **Enable Sign in with Google** on.
   - **Client IDs**: paste the Google Client ID from step 1b.
   - **Client Secret**: paste the Google client secret from step 1b.
   - Confirm the **Callback URL (for OAuth)** shown on this panel reads
     `https://izvcwrgfwobmmmtpubdi.supabase.co/auth/v1/callback`. It is
     read-only, and it is the value you already gave Google.
   - **Save**.
3. Find **GitHub** → expand it.
   - Toggle **Enable Sign in with GitHub** on.
   - **Client ID**: from step 2.
   - **Client Secret**: from step 2.
   - **Save**.

Verify without leaving the terminal — both flags must flip to `true`:

```bash
curl -s https://izvcwrgfwobmmmtpubdi.supabase.co/auth/v1/settings -H "apikey: sb_publishable_osfqQeq8heYHxnAB7b4f-g_wOVnNrYq" | python3 -m json.tool
```

At the time this doc was written the response had `"google": false` and
`"github": false`. After step 3 both must read `true`. That single command is
the fastest check that this step actually took effect.

---

## 4. Supabase — URL configuration

**Authentication → URL Configuration**.

**Site URL** — the default post-auth destination, and the fallback when a
`redirectTo` is not on the allow list:

```
https://junoguard.com
```

**Redirect URLs** — click **Add URL** once per entry. All four, exactly:

```
https://junoguard.com/auth/callback
https://www.junoguard.com/auth/callback
https://junoguard-dashboard.vercel.app/auth/callback
http://localhost:5173/auth/callback
```

Then **Save**.

Why all four: `AuthContext.signInWithProvider` sends
`redirectTo: ${window.location.origin}/auth/callback`, so the origin is
whichever host the browser is actually on. A missing entry does not error
loudly — Supabase silently falls back to **Site URL**, so a localhost sign-in
would bounce you to production and the local session would never appear. If
sign-in "works" but you land on the wrong host, an entry is missing here.

> `http` for localhost is correct — the dev server is plain HTTP. Everything
> else is `https`. Port `5173` is Vite's default; if you run on another port,
> add that entry too.

---

## 5. Verify end to end

1. Start the gateway (it writes the rows the dashboard reads):

   ```bash
   cd backend && ./.venv/bin/uvicorn app.main:app --reload
   ```

2. Start the dashboard:

   ```bash
   cd frontend && npm run dev
   ```

3. Open <http://localhost:5173/dashboard>. With Supabase configured you are
   redirected to `/auth/sign-in`.
4. Click **Continue with Google**. Sign in. You should land back on
   `/dashboard` with the feed populated.
5. Generate a fresh row and watch it arrive live:

   ```bash
   curl -s -X POST http://localhost:8000/v1/guard/install \
     -H "X-Juno-Key: jg_demo_key_cursorhack2026" \
     -H "Content-Type: application/json" \
     -d '{"package":"@ossprey/test-package","ecosystem":"npm"}'
   ```

   A blocked `@ossprey/test-package` row should appear at the top of the feed
   without a page refresh (Supabase Realtime).

### If the dashboard is empty after sign-in

The feed reads Supabase, not the gateway, the moment `VITE_SUPABASE_URL` is set.
An empty dashboard means the rows are not there or are not readable:

```bash
# Is the gateway actually pointed at Supabase? Must print SupabaseStore.
cd backend && ./.venv/bin/python -c "from app.store import store; print(type(store).__name__)"
```

`MemoryStore` means `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is missing
from `backend/.env` — the gateway is writing to RAM and the dashboard is
reading an empty database.

### Emergency fallback for the demo

If OAuth misbehaves on stage, comment out the two Supabase lines in
`frontend/.env.local` and restart `npm run dev`. The dashboard drops to the SSE
lane (gateway feed, no sign-in wall). Remove `VITE_API_URL` as well and it drops
to mock mode, which needs no backend at all.

---

## 6. Vercel

The deployed dashboard needs the same two public values.

```bash
cd frontend
vercel env add VITE_SUPABASE_URL production
# paste: https://izvcwrgfwobmmmtpubdi.supabase.co

vercel env add VITE_SUPABASE_ANON_KEY production
# paste: sb_publishable_osfqQeq8heYHxnAB7b4f-g_wOVnNrYq

vercel --prod   # redeploy; Vite inlines env vars at build time
```

Or **Vercel Dashboard → hey-salad-inc/junoguard-dashboard → Settings →
Environment Variables**, then redeploy from the **Deployments** tab
(**⋯ → Redeploy**).

A redeploy is mandatory. `VITE_` values are compiled into the bundle at build
time, so an existing deployment will not pick them up.

**Do not add `SUPABASE_SERVICE_ROLE_KEY` to Vercel.** Nothing in the frontend
uses it, and a `VITE_`-prefixed secret is published to every visitor.

> Setting these switches the *deployed* dashboard onto the Supabase lane too.
> It will show a sign-in wall and read from Supabase, so only do this once
> steps 3 and 4 are complete.

---

## What is already done

Committed to the repo, no console access required:

- `supabase/schema.sql` applied to `izvcwrgfwobmmmtpubdi` — `projects`,
  `policies`, `agent_actions`, `incidents`, the `daily_spend_usd` function,
  RLS policies scoped to `authenticated`, the `supabase_realtime` publication,
  and the `Demo Project` seed row.
- `backend/.env` has `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, so the
  gateway writes to Supabase instead of memory. This file is gitignored and the
  service role key is not in any `VITE_` variable.
- `frontend/.env.local` has `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`.
- `frontend/src/auth/ProtectedRoute.tsx` passes through when Supabase is not
  configured, so mock and SSE mode can still reach `/dashboard`.

Still needs a human in a browser: **steps 1, 2, 3, 4** and the Vercel
variables in step 6.
