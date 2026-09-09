# ZB Hub — Test Plan

Guides the automated test pass performed on branch `claude/testing-agent-error-log-jpltof`
(code under test: `claude/project-hub-website-auth-8lqf7g`, PR #1). This document
describes what is tested, how, why, and **when to run which tier** —
not the results. Results and any defects found are recorded separately in
`ERROR_LOG.md`. **No application code was modified as part of this pass.**

## 1. System under test

A Flask 3 monolith ("ZB Hub") with five feature areas, each a blueprint:

| Area | Module | Notes |
|---|---|---|
| Auth | `app/auth.py` | Username/password + Google/Apple OAuth, password reset, account-lockout |
| Main hub | `app/main.py` | Landing page, project links |
| Wine Library | `app/wines.py` | Cellar CRUD, tasting notes, Gemini chat assistant |
| Recipe Tracker | `app/recipes.py` | Recipe CRUD, ingredient scaling, comments, "add to grocery list" |
| Grocery List | `app/grocery.py` | One list shared by every signed-in user |

Persistence is PostgreSQL via SQLAlchemy + Alembic migrations (`migrations/`).
There is no ORM-level test fixture (no `conftest.py`, no `create_all()`) —
every test that touches the database talks to a real Postgres database that
must already have migrations applied. This test pass preserves that
convention rather than introducing an in-memory/sqlite shortcut, since
sqlite would silently skip Postgres-only behavior (e.g. `UniqueConstraint`
semantics, numeric/decimal column behavior).

## 2. Test environment

- Python 3.11 virtualenv, `pip install -r requirements-dev.txt` (Flask, pytest, Authlib, psycopg2, etc.)
- Local PostgreSQL 16 server, database `zbhub` / role `zbhub` (matches the DSN
  every DB-backed test file hard-codes: `postgresql://zbhub:zbhub@localhost:5432/zbhub`) —
  **not needed** to run `tests/test_unit.py`, which touches no database.
- Schema brought up to date with `flask db upgrade` (all 5 Alembic revisions)
- Environment variables: `SECRET_KEY=test-secret`, `DATABASE_URL` as above.
  `GOOGLE_CLIENT_ID/SECRET`, `APPLE_*`, `GEMINI_API_KEY`, and `MAIL_*` are all
  deliberately left **unset**, so tests exercise the "feature not configured"
  code paths by default.
- `WTF_CSRF_ENABLED = False` and `TESTING = True` on every test app instance
  (CSRF form-token plumbing is not under test here).
- Runner: `pytest` (`pytest.ini` sets `pythonpath = .`).

## 3. The three test files

The suite is split into exactly three files, one per tier, run bottom-to-top
in cost (unit is instant; e2e is the slowest and broadest):

| File | Tier | What it covers | DB needed? |
|---|---|---|---|
| `tests/test_unit.py` | Unit | Pure functions only — `format_qty`, `_parse_servings`, `_parse_quantity` from `app/recipes.py`. No Flask app, no HTTP, no database. | No |
| `tests/test_integration.py` | Integration | Every route/feature exercised **in isolation**, one at a time, through Flask's test client against a real Postgres DB: auth (register/login/lockout/reset), account settings, OAuth routing, Wine Library, AI wine research (Gemini, mocked), Telegram bot webhook (mocked), Recipe Tracker, Grocery List, ownership/authorization checks, input validation. Also holds the two regression tests for real bugs found during this pass (`test_non_numeric_vintage_should_not_crash_the_server`, `test_reset_link_for_a_deleted_account_should_not_crash_the_server`) — see `ERROR_LOG.md`. | Yes |
| `tests/test_e2e.py` | End-to-end | Full multi-step user journeys that chain several features together in one session, the way a real person actually uses the app — e.g. sign up → add a wine → log a tasting → edit it → change password → sign out → sign back in; or one user builds a recipe and pushes it to the shared grocery list, a second user sees it, deletes an item, and clears the rest. The app has no client-side JS, so "end to end" here means through the same test client as integration, but following a whole story instead of one action. | Yes |

Every unit test is naturally idempotent (no state to collide on). The
integration and e2e files are **not** idempotent against a reused database —
see §6 below before relying on repeated runs against the same DB.

## 4. Scope

**In scope:** functional behavior reachable through Flask's test client —
route responses, status codes, redirects, flashed messages, rendered-page
content, and resulting database state. Includes ownership/authorization
checks (a user cannot see or modify another user's wines or recipes), input
validation on forms, pure-function helpers, and cross-feature user journeys.

**Out of scope (not exercised by this pass):**
- Real OAuth handshakes with Google/Apple, and real Gemini/SMTP network
  calls — these require live third-party credentials and are exercised here
  only through their "not configured" / failure branches.
- Browser/JS behavior (the app has no client-side JS) and CSS/visual checks.
- Load, performance, and concurrency testing.
- Static analysis / type checking (no `mypy` config present in the repo).

## 5. Development workflow — when to run which tier

| When | Run | Why |
|---|---|---|
| **After each feature implementation** (any time you finish writing or touching a function) | `pytest tests/test_unit.py` | Instant, no DB required — the cheapest possible feedback loop. Run it constantly while coding, not just once at the end. |
| **Before committing/pushing changes to git** | `pytest tests/test_integration.py` (or `pytest tests/test_unit.py tests/test_integration.py`) | Confirms the specific route/feature you touched still behaves correctly in isolation, plus everything else in the affected blueprints, before the change leaves your machine. |
| **Before deployment** | `pytest` (the full suite, `test_unit.py` + `test_integration.py` + `test_e2e.py`) | The final gate — proves the pieces still work *together* across a full user journey, not just individually, before the change reaches production. |

Rationale: unit tests are cheap enough to run on every save; integration
tests take longer (they hit Postgres and register/log in real users) so
they belong at the commit boundary, not on every keystroke; e2e tests are
the broadest and slowest, and exist specifically to catch the class of bug
that only shows up when several features are used back-to-back in one
session — the right place for that check is the last gate before shipping,
not mid-development.

## 6. Known-defect convention

`tests/test_integration.py` ends with a "Known defects" section: real,
open application bugs get a regression test, same as anything else, but
marked `@pytest.mark.xfail(reason="...", strict=True)` instead of left to
fail outright. That keeps `pytest`'s exit code (and CI, which the repo's
`deploy` job is gated on) green while a documented bug is still open,
without hiding it — it still shows up as `xfailed` in the run summary, and
`strict=True` means the day someone actually fixes the bug, that test
starts "unexpectedly passing" (`XPASS`), which itself fails the run — the
signal to remove the marker rather than let a fix go untracked. See
`ERROR_LOG.md` for what's currently marked this way and why.

## 7. Known risks / test-suite limitations worth flagging up front

- **Shared, non-isolated database.** No test resets or truncates tables
  between runs (`test_clear_list_removes_everything` in `test_integration.py`
  is the one exception, and it empties the *entire* `grocery_item` table —
  shared by every other test in the suite). Tests avoid collisions today
  only because they run serially within one `pytest` invocation and use
  unique usernames/emails; **running the suite twice in a row against the
  same database, without recreating it, reproducibly breaks a dozen tests**
  with `sqlalchemy.exc.MultipleResultsFound` (rows looked up by a
  non-unique name collide with the previous run's rows of the same name).
  See `ERROR_LOG.md` for the reproduction. Always start from a freshly
  migrated database for a trustworthy result, or add per-test isolation
  before relying on repeat runs.
- **No fixtures/teardown.** `test_integration.py` and `test_e2e.py` each
  declare their own `_app()` helper rather than sharing a `conftest.py`.
  Rows created by one test run persist into the next `pytest` invocation
  (the DB is never dropped/recreated by the suite itself).
- **Environment coupling.** `test_integration.py` unsets the OAuth/Gemini
  environment variables at import time so its "not configured" tests are
  deterministic regardless of what the shell environment carries in.
