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
- [ ] **Email for password reset** — any SMTP account works, e.g. a
  Gmail app password (`MAIL_SERVER` / `MAIL_USERNAME` / `MAIL_PASSWORD`).
  Without it, "forgot password" stays hidden (change-password while
  logged in still works). See README §5.
- [ ] **Gemini API key for the Wine Assistant chat bot** — free key at
  aistudio.google.com/apikey (`GEMINI_API_KEY`). Without it, the chat
  link on the Wine Library page stays hidden. See README §6.
- [ ] **GCP project + CI/CD wiring** — run `scripts/setup_gcp_ci.sh`
  once (needs `gcloud auth login` and a GCP project) and add the 6
  printed values as GitHub repo secrets. See README §8.
- [ ] **First real deploy** — once the above are in place, a push to
  `main` deploys automatically. Worth a live smoke test afterward
  (hit the Cloud Run URL, try registering an account, try the Wine
  Assistant if Gemini is configured) to confirm it's actually working
  end to end, not just green in CI.

## Ideas for later

Nothing here is committed to — just things noticed along the way that
aren't needed yet.

- [ ] **More hub projects** — Wine Library, Recipe Tracker, and Grocery
  List so far. Each new project is just another blueprint registered in
  `app/__init__.py` plus an entry in `app/main.py`'s `PROJECTS` list.
- [ ] **Wine Library search/filter** — fine for a small personal
  cellar; would matter once the list gets long.
- [ ] **IP-based login throttling** — the current lockout is per-account
  (5 failed attempts locks that username for 15 min); it doesn't slow
  down someone guessing many different usernames from one IP.
- [ ] **Multi-turn wine chat history** — the Wine Assistant is currently
  one question in, one answer out, with no memory between messages.
- [ ] **Grocery list item check-off** — right now items are just added
  and deleted/cleared; a "got it" checkbox (vs. deleting) could be nice
  for a mid-shop view of what's left.
- [ ] **Recipe ingredient parsing from pasted text** — right now each
  ingredient is entered into its own quantity/unit/name fields; pasting
  a whole ingredient list and auto-splitting it would be faster to use.
