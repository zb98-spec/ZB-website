# ZB Hub

A simple, central hub/landing page for personal projects, with account
creation via Google or Apple sign-in.

- **Framework**: Next.js 16 (App Router) + Tailwind CSS
- **Auth**: [Auth.js](https://authjs.dev) (NextAuth v5) with Google and Apple providers
- **Database**: PostgreSQL via [Prisma](https://prisma.io) (works great with any free Postgres host, see below)
- **Containerized**: Docker + docker-compose for local dev
- **Deploy target**: Google Cloud Run

## Pages

- `/` — welcome page. Signed out: hero + "Get started". Signed in: a simple
  dashboard listing the user's projects (`Project` table).
- `/login` — account creation / sign-in page with "Continue with Google" and
  "Continue with Apple" buttons. There's no separate sign-up form — the
  first OAuth sign-in creates the account automatically.

## 1. Local setup

```bash
npm install
cp .env.example .env
```

Fill in `.env`:

- `AUTH_SECRET` — generate with `npx auth secret` (or `openssl rand -base64 33`).
- `DATABASE_URL` / `DIRECT_URL` — see the free database section below.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — see below.
- `APPLE_CLIENT_ID` / `APPLE_CLIENT_SECRET` — see below.

Run migrations and start the dev server:

```bash
npx prisma migrate dev --name init
npm run dev
```

Visit http://localhost:3000.

## 2. Free database

Any managed Postgres works since this is just Prisma + `DATABASE_URL`, but
two good free options:

- **[Neon](https://neon.tech)** (recommended) — free tier, serverless
  Postgres, scales to zero, gives you both a pooled connection string (use
  as `DATABASE_URL`) and a direct one (use as `DIRECT_URL` for migrations).
  Pairs well with Cloud Run's scale-to-zero behavior.
- **[Supabase](https://supabase.com)** — free tier Postgres, also gives a
  pooled (port 6543) and direct (port 5432) connection string.

Create a project on either, copy the connection strings into `.env`, then
run `npx prisma migrate dev`.

## 3. Google OAuth setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth client ID** (type: Web application).
3. Authorized redirect URI:
   - Local: `http://localhost:3000/api/auth/callback/google`
   - Production: `https://<your-domain>/api/auth/callback/google`
4. Copy the Client ID/Secret into `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

## 4. Sign in with Apple setup

Requires an active [Apple Developer Program](https://developer.apple.com/programs/) membership ($99/yr).

1. Create an **App ID** with "Sign in with Apple" enabled.
2. Create a **Services ID** — this is your `APPLE_CLIENT_ID`. Configure its
   return URL: `https://<your-domain>/api/auth/callback/apple` (Apple does
   not allow `http://localhost`, so Apple login can only be tested against
   a deployed HTTPS URL or a tunnel like ngrok).
3. Create a **Sign in with Apple key**, note the Key ID and Team ID.
4. Generate `APPLE_CLIENT_SECRET`, a signed JWT, from that key. Auth.js
   docs show how: https://authjs.dev/getting-started/providers/apple
5. Until this is configured, the "Continue with Apple" button will simply
   error — Google login works independently.

## 5. Run with Docker

```bash
docker compose up --build
```

This starts a local Postgres container plus the app (built from the
`Dockerfile`) on http://localhost:3000. Fill in `.env` first (OAuth
credentials, `AUTH_SECRET`) — the compose file overrides `DATABASE_URL` to
point at the bundled Postgres container automatically.

To use a hosted free database (Neon/Supabase) instead of the bundled
container even during `docker compose`, remove the `db` service and the
`DATABASE_URL`/`DIRECT_URL` overrides under `web.environment` from
`docker-compose.yml` so your `.env` values are used as-is.

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
  --set-env-vars AUTH_URL=https://<your-cloud-run-url>,AUTH_TRUST_HOST=true \
  --set-secrets AUTH_SECRET=auth-secret:latest,DATABASE_URL=database-url:latest,DIRECT_URL=direct-url:latest,GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,APPLE_CLIENT_ID=apple-client-id:latest,APPLE_CLIENT_SECRET=apple-client-secret:latest
```

Notes:

- Store secrets in [Secret Manager](https://cloud.google.com/secret-manager)
  rather than plain `--set-env-vars`; the command above references secrets
  by name (create them first with `gcloud secrets create ...`).
- Cloud Run injects `PORT` automatically; the Dockerfile's `server.js`
  (Next's "standalone" output) already respects it.
- After the first deploy, update `AUTH_URL` and both OAuth providers'
  redirect URIs to the real Cloud Run URL (or a custom domain mapped to it).
- Run `npx prisma migrate deploy` (locally, or as a one-off Cloud Run job)
  against the production `DIRECT_URL` before/after each deploy that
  changes `prisma/schema.prisma`.
- Both Cloud Run and Neon/Supabase free tiers scale to zero, so this whole
  stack can run at $0 for low-traffic personal use — Cloud Run's free tier
  covers a generous number of requests/month, and Cloud Build has a free
  monthly quota for image builds.

## Adding projects to the hub

There's no admin UI yet — the dashboard just reads the `Project` table.
Add rows directly (via `npx prisma studio` or SQL) with `userId`, `name`,
`description`, and `url`, and they'll show up on the welcome page for that
user.
