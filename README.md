# ZB Hub

A simple, central hub/landing page for personal projects, with account
creation via Google or Apple sign-in.

- **Framework**: Flask (app factory + blueprints), server-rendered Jinja templates
- **Auth**: [Authlib](https://authlib.org) OAuth client with Google and Apple providers, sessions via Flask-Login
- **Database**: PostgreSQL via Flask-SQLAlchemy + Flask-Migrate (Alembic)
- **Containerized**: Docker + docker-compose for local dev
- **Deploy target**: Google Cloud Run

## Structure

```
app/
  __init__.py     app factory, wires up extensions and blueprints
  extensions.py   db, migrate, login_manager, csrf singletons
  models.py       User, OAuthAccount, Wine
  auth.py         /login, OAuth redirect + callback, /logout
  main.py         welcome page / hub dashboard
  wines.py        Wine Library CRUD (first project on the hub)
  templates/
  static/css/
wsgi.py           entrypoint (`app = create_app()`), used by gunicorn/flask run
migrations/       Alembic migrations (flask db migrate/upgrade)
```

## Pages

- `/` — welcome page. Signed out: hero + "Get started". Signed in: a
  dashboard of hub projects — currently just "Wine Library".
- `/login` — account creation / sign-in page with "Continue with Google"
  and "Continue with Apple" buttons. There's no separate sign-up form —
  the first OAuth sign-in creates the account automatically.
- `/wines` — **Wine Library**: add, edit, delete, and list every bottle in
  your cellar (name, producer, vintage, type, varietal, region, quantity,
  purchase price, rating, drinking window, notes). Each user only sees
  their own wines.

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

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth client ID** (type: Web application).
3. Authorized redirect URI:
   - Local: `http://localhost:5000/login/google/callback`
   - Production: `https://<your-domain>/login/google/callback`
4. Copy the Client ID/Secret into `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

## 4. Sign in with Apple setup

Requires an active [Apple Developer Program](https://developer.apple.com/programs/) membership ($99/yr).

1. Create an **App ID** with "Sign in with Apple" enabled.
2. Create a **Services ID** — this is your `APPLE_CLIENT_ID`. Configure its
   return URL: `https://<your-domain>/login/apple/callback` (Apple requires
   HTTPS, so Apple login can only be tested against a deployed URL or a
   tunnel like ngrok, not plain `localhost`).
3. Create a **Sign in with Apple key** in the Apple Developer portal, note
   its Key ID (`APPLE_KEY_ID`) and your Team ID (`APPLE_TEAM_ID`), and
   download the `.p8` private key file — paste its contents into
   `APPLE_PRIVATE_KEY`.
4. That's it — the app signs its own Apple client-secret JWT at startup
   (see `_generate_apple_client_secret` in `app/auth.py`), so there's no
   separate manual JWT-generation step.
5. Until all four `APPLE_*` variables are set, the "Continue with Apple"
   button is shown disabled — Google login works independently.

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

```bash
# Build and push the image
gcloud builds submit --tag gcr.io/PROJECT_ID/zb-hub

# Deploy
gcloud run deploy zb-hub \
  --image gcr.io/PROJECT_ID/zb-hub \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest,GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,APPLE_CLIENT_ID=apple-client-id:latest,APPLE_TEAM_ID=apple-team-id:latest,APPLE_KEY_ID=apple-key-id:latest,APPLE_PRIVATE_KEY=apple-private-key:latest
```

Notes:

- Store secrets in [Secret Manager](https://cloud.google.com/secret-manager)
  rather than plain `--set-env-vars`; the command above references secrets
  by name (create them first with `gcloud secrets create ...`).
- Cloud Run injects `PORT` automatically; gunicorn in the Dockerfile binds
  to it already.
- After the first deploy, update both OAuth providers' redirect URIs to
  the real Cloud Run URL (or a custom domain mapped to it).
- Run `flask db upgrade` against the production database before/after each
  deploy that changes `app/models.py` — either locally with `DATABASE_URL`
  pointed at prod, or as a one-off Cloud Run job.
- Both Cloud Run and Neon/Supabase free tiers scale to zero, so this whole
  stack can run at $0 for low-traffic personal use — Cloud Run's free tier
  covers a generous number of requests/month, and Cloud Build has a free
  monthly quota for image builds.

## Adding more projects to the hub

Each project is just another blueprint (see `app/wines.py` for the
pattern: a `Blueprint`, its own models, and CRUD routes scoped to
`current_user.id`). Register it in `app/__init__.py` and add an entry to
the `PROJECTS` list in `app/main.py` so it shows up as a card on `/`.
