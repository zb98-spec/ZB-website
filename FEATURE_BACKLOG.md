# Feature Backlog

## Blocked on you

These need something only you can provide (an account login, a paid
membership, a live database) — the app-side code is already done and
waiting on the values.

- [ ] **Neon database** — create a Neon project and get its
  `DATABASE_URL`. Needed before any real (non-sandbox) deploy or
  migration can run. See README §2.
- [ ] **Google OAuth login** — create credentials in Google Cloud
  Console (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`). See README §3.
- [ ] **Apple Sign In** — requires a paid Apple Developer Program
  membership ($99/yr), then create a Services ID + key
  (`APPLE_CLIENT_ID` / `APPLE_TEAM_ID` / `APPLE_KEY_ID` /
  `APPLE_PRIVATE_KEY`). See README §4.
- [ ] **GCP project + CI/CD wiring** — run `scripts/setup_gcp_ci.sh`
  once (needs `gcloud auth login` and a GCP project) and add the 6
  printed values as GitHub repo secrets. See README §6.
- [ ] **First real deploy** — once the above are in place, a push to
  `main` deploys automatically. Worth a live smoke test afterward
  (hit the Cloud Run URL, try registering an account) to confirm it's
  actually working end to end, not just green in CI.

## Ideas for later

Nothing here is committed to — just things noticed along the way that
aren't needed yet.

- [ ] **Password reset / "forgot password"** — username/password
  accounts currently have no recovery path if a password is lost.
  Would need an email address on file (registration doesn't currently
  ask for one) plus a way to send mail.
- [ ] **Login rate limiting** — `/login/password` has no lockout or
  throttling on repeated failed attempts.
- [ ] **More hub projects** — Wine Library is the only one so far.
  Each new project is just another blueprint registered in
  `app/__init__.py` plus an entry in `app/main.py`'s `PROJECTS` list.
- [ ] **Wine Library search/filter** — fine for a small personal
  cellar; would matter once the list gets long.
