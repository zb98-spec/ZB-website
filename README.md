# ZB Hub

A simple, central hub/landing page for personal projects, with account
creation via username/password, or Google/Apple sign-in.

- **Framework**: Flask (app factory + blueprints), server-rendered Jinja templates
- **Auth**: username/password (Werkzeug password hashing, Flask-Login sessions)
  plus optional [Authlib](https://authlib.org) OAuth with Google and Apple
- **Database**: PostgreSQL via Flask-SQLAlchemy + Flask-Migrate (Alembic)
- **Containerized**: Docker + docker-compose for local dev
- **Deploy target**: Google Cloud Run

## Structure

```
app/
  __init__.py     app factory, wires up extensions and blueprints
  extensions.py   db, migrate, login_manager, csrf singletons
  models.py       User, OAuthAccount, Wine, TastingNote
  auth.py         /login, /register, OAuth redirect + callback, /logout
  main.py         welcome page / hub dashboard
  wines.py        Wine Library CRUD + tasting log (first project on the hub)
  templates/
  static/css/
wsgi.py           entrypoint (`app = create_app()`), used by gunicorn/flask run
migrations/       Alembic migrations (flask db migrate/upgrade)
```

## Pages

- `/` — welcome page. Signed out: hero + "Get started". Signed in: a
  dashboard of hub projects — currently just "Wine Library".
- `/login` — sign-in page: a username/password form (works out of the box,
  no setup needed) plus "Continue with Google"/"Continue with Apple"
  buttons, shown disabled until those are configured (see §3 and §4).
- `/register` — create an account with a username and password. Usernames
  are 3-80 characters (letters, numbers, `_ . -`) and must be unique;
  passwords need to be at least 8 characters. Registering logs you in
  immediately — there's no email verification step.
- `/wines` — **Wine Library**: add, edit, delete, and list every bottle in
  your cellar (name, producer, vintage, type, varietal, region, quantity,
  purchase price, rating, drinking window, notes). Each user only sees
  their own wines. Each row has a **Log tasting** button.
- `/wines/<id>` — a wine's detail page: cellar info plus its tasting
  history, newest-first.
- `/wines/<id>/tastings/new` — log a tasting: date and score (1-100) are
  required; occasion, people, and notes are optional. Optionally
  decrements the wine's cellar quantity by one (checked by default, since
  logging a tasting usually means a bottle got opened).

## 1. Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- `SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `DATABASE_URL` — see the free database section below.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — see below.
- `APPLE_CLIENT_ID` / `APPLE_TEAM_ID` / `APPLE_KEY_ID` / `APPLE_PRIVATE_KEY` — see below.

Run migrations and start the dev server:

```bash
export FLASK_APP=wsgi.py
flask db upgrade
flask run
```

Visit http://localhost:5000. If Google/Apple credentials aren't set yet,
`/login` still loads — the corresponding button is just shown disabled, so
you can develop the rest of the app before OAuth is wired up.

## 2. Free database

Any managed Postgres works, since this is just Flask-SQLAlchemy +
`DATABASE_URL`, but two good free options:

- **[Neon](https://neon.tech)** (recommended) — free tier, serverless
  Postgres, scales to zero. Pairs well with Cloud Run's scale-to-zero
  behavior.
- **[Supabase](https://supabase.com)** — free tier Postgres.

Create a project on either, copy the connection string into `.env` as
`DATABASE_URL` (Flask accepts either `postgres://` or `postgresql://`),
then run `flask db upgrade`.

## 3. Google OAuth setup

This has to be done in your own Google account — there's no API for it, it's
a few clicks in the console:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   (same project you used for Cloud Run/Neon, or a fresh one).
2. If you haven't already, configure the **OAuth consent screen** first
   (Console will prompt you): User type "External" is fine for personal use;
   fill in an app name, your email as support/developer contact. Leave it in
   "Testing" status — you don't need Google's review for personal use, you
   just have to add your own Google account under **Test users** on that
   screen, or sign-in will be rejected.
3. Under **Credentials**, create an **OAuth client ID** (type: Web application).
4. Authorized redirect URI — add both while developing:
   - Local: `http://127.0.0.1:5000/login/google/callback`
   - Production: `https://<your-cloud-run-url>/login/google/callback`
5. Copy the Client ID/Secret into `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
   (in `.env` locally, and as the `google-client-id` / `google-client-secret`
   Secret Manager secrets for Cloud Run — see §6).
6. Restart the app (`flask run`) — the "Continue with Google" button on
   `/login` goes from disabled to live as soon as both env vars are set;
   nothing else in the code needs to change.

## 4. Sign in with Apple setup

Also has to be done in your own account, and requires an active
[Apple Developer Program](https://developer.apple.com/programs/) membership
($99/yr) — there's no free tier for this one.

1. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list),
   create an **App ID** (or use an existing one) with the "Sign in with
   Apple" capability turned on.
2. Create a **Services ID** — this is your `APPLE_CLIENT_ID`. Under its
   "Sign in with Apple" configuration, set the primary App ID from step 1,
   and add a return URL: `https://<your-cloud-run-url>/login/apple/callback`
   (Apple requires HTTPS and refuses `localhost`/`127.0.0.1`, so Apple login
   can only be tested against a deployed URL or a tunnel like ngrok, never a
   plain local dev server).
3. Under **Keys**, create a new key with "Sign in with Apple" enabled,
   associated with the App ID from step 1. Note its Key ID (`APPLE_KEY_ID`)
   and your Team ID, shown at the top right of the developer portal
   (`APPLE_TEAM_ID`). Download the `.p8` private key file **once** — Apple
   won't let you download it again — and paste its full contents (including
   the `-----BEGIN/END PRIVATE KEY-----` lines) into `APPLE_PRIVATE_KEY`.
4. That's it — the app signs its own Apple client-secret JWT at startup
   (see `_generate_apple_client_secret` in `app/auth.py`), so there's no
   separate manual JWT-generation step, and no expiry to track (it's
   re-signed fresh on every process start, well within Apple's 6-month cap).
5. Until all four `APPLE_*` variables are set, the "Continue with Apple"
   button on `/login` is shown disabled — Google login works independently
   of Apple being configured, and vice versa.
6. First-time sign-in quirk: Apple only ever sends the user's name once, on
   the very first authorization for a given Apple ID — the app captures it
   then (see the `apple_user` handling in `app/auth.py`); if you deny the
   name/email prompt or it's a returning user, the account still gets
   created, just without a name.

## 5. Run with Docker

```bash
docker compose up --build
```

This starts a local Postgres container plus the app on
http://localhost:3000. Fill in `.env` first (OAuth credentials,
`SECRET_KEY`) — the compose file overrides `DATABASE_URL` to point at the
bundled Postgres container automatically. Run migrations once against it:

```bash
docker compose exec web flask db upgrade
```

To use a hosted free database (Neon/Supabase) instead of the bundled
container even during `docker compose`, remove the `db` service and the
`DATABASE_URL` override under `web.environment` from `docker-compose.yml`
so your `.env` value is used as-is.

## 6. Deploy to Google Cloud Run

### One-time GCP setup

Create the Secret Manager secrets the app needs at runtime (repeat for
each one: `secret-key`, `database-url`, `google-client-id`,
`google-client-secret`, `apple-client-id`, `apple-team-id`,
`apple-key-id`, `apple-private-key`):

```bash
echo -n "VALUE" | gcloud secrets create secret-key --data-file=-
```

### First deploy (manual, to confirm everything works)

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/zb-hub
gcloud run deploy zb-hub \
  --image gcr.io/PROJECT_ID/zb-hub \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest,GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,APPLE_CLIENT_ID=apple-client-id:latest,APPLE_TEAM_ID=apple-team-id:latest,APPLE_KEY_ID=apple-key-id:latest,APPLE_PRIVATE_KEY=apple-private-key:latest
```

After this deploy, update both OAuth providers' redirect URIs to the real
Cloud Run URL (or a custom domain mapped to it) — you'll get that URL
back from the command above, or from `gcloud run services describe
zb-hub --region us-central1 --format 'value(status.url)'`. That URL is
also what you'll open on your iPhone (see below).

### Automatic deploys via GitHub Actions

`.github/workflows/deploy.yml` runs on every push to `main`: it runs the
test suite against a throwaway Postgres container, and — only if that
passes — builds the image, runs `flask db upgrade` against your real Neon
database, and deploys to Cloud Run. Pull requests only run the tests.

One-time setup, once you have a GCP project and this repo pushed to
GitHub:

```bash
PROJECT_ID=your-project REGION=us-central1 GITHUB_REPO=your-user/your-repo \
  ./scripts/setup_gcp_ci.sh
```

This script creates a Cloud Run/Artifact Registry deploy service account
and a Workload Identity Federation provider scoped to your repo, so
GitHub Actions can deploy without ever holding a long-lived GCP key. It
prints four values at the end — add them as **GitHub repo secrets**
(Settings -> Secrets and variables -> Actions):

- `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_SA_EMAIL`, `GCP_WIF_PROVIDER`

Also add two more repo secrets, used only to run migrations directly
against Neon from the workflow (Neon is reachable over the public
internet, so this needs no special networking):

- `SECRET_KEY` — same value as the `secret-key` Secret Manager secret
- `DATABASE_URL` — your Neon connection string

From then on, every push to `main` that passes tests deploys automatically.

Notes:

- Cloud Run injects `PORT` automatically; gunicorn in the Dockerfile binds
  to it already.
- Both Cloud Run and Neon's free tiers scale to zero, so this whole stack
  can run at $0 for low-traffic personal use — Cloud Run's free tier
  covers a generous number of requests/month, and Cloud Build has a free
  monthly quota for image builds.

## Viewing it on your iPhone

Once it's deployed to Cloud Run (above), the service URL is a normal
public HTTPS address — open it in Safari on your iPhone like any other
site, no extra setup needed. This is also the easiest way to test Apple
Sign In, since Apple refuses to redirect to `localhost`.

Before deploying, you can still preview it from your phone if it's on the
same Wi-Fi as the computer running the app:

```bash
flask run --host 0.0.0.0
```

then visit `http://<your-computer's-LAN-IP>:5000` in Safari (find the IP
with `ipconfig getifaddr en0` on a Mac). Google/Apple sign-in won't work
over plain `http://`, but the welcome page and (once you're logged in via
a proper deploy) the Wine Library pages will.

## Adding more projects to the hub

Each project is just another blueprint (see `app/wines.py` for the
pattern: a `Blueprint`, its own models, and CRUD routes scoped to
`current_user.id`). Register it in `app/__init__.py` and add an entry to
the `PROJECTS` list in `app/main.py` so it shows up as a card on `/`.
