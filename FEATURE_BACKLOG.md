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
- [ ] **Gemini API key** — free key at aistudio.google.com/apikey
  (`GEMINI_API_KEY`). Powers both the Wine Assistant chat bot and the
  "Research checked with AI" button; without it, both stay hidden.
  See README §6.
- [ ] **Telegram bot token + webhook secret** — create a bot via
  @BotFather for `TELEGRAM_BOT_TOKEN`; make up any random string for
  `TELEGRAM_WEBHOOK_SECRET`. Needs a real deployed HTTPS URL to finish
  setup (`scripts/set_telegram_webhook.sh`), so this one has to come
  after the first real deploy, not before. See README §7.
- [ ] **GCP project + CI/CD wiring** — run `scripts/setup_gcp_ci.sh`
  once (needs `gcloud auth login` and a GCP project) and add the 6
  printed values as GitHub repo secrets. See README §9.
- [ ] **First real deploy** — once the above are in place, a push to
  `main` deploys automatically. Worth a live smoke test afterward (hit
  the Cloud Run URL, register an account, try the Wine Assistant/AI
  research if Gemini is configured, then run
  `set_telegram_webhook.sh` and try `/start` on the bot) to confirm
  it's actually working end to end, not just green in CI.

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
- [ ] **AI research background job** — the "Research checked with AI" button
  processes up to 15 wines synchronously in one request (no job queue
  exists yet); fine for a personal cellar, would need rework for a much
  larger one or to remove the 15-per-click cap.
- [ ] **Telegram bot: more commands** — e.g. editing/deleting a bottle,
  or listing the full cellar, not just what's in its drinking window.
