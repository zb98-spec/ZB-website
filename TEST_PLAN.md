# ZB Hub — Test Plan

Guides the automated test pass performed on branch `claude/testing-agent-error-log-jpltof`
(code under test: `claude/project-hub-website-auth-8lqf7g`, PR #1). This document
describes what is tested, how, and why — not the results. Results and any
defects found are recorded separately in `ERROR_LOG.md`. **No application
code was modified as part of this pass.**

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
every existing test talks to a real Postgres database that must already have
migrations applied. This test pass preserves that convention rather than
introducing an in-memory/sqlite shortcut, since sqlite would silently skip
Postgres-only behavior (e.g. `UniqueConstraint` semantics, numeric/decimal
column behavior).

## 2. Test environment

- Python 3.11 virtualenv, `pip install -r requirements-dev.txt` (Flask, pytest, Authlib, psycopg2, etc.)
- Local PostgreSQL 16 server, database `zbhub` / role `zbhub` (matches the DSN
  every test file already hard-codes: `postgresql://zbhub:zbhub@localhost:5432/zbhub`)
- Schema brought up to date with `flask db upgrade` (all 5 Alembic revisions)
- Environment variables: `SECRET_KEY=test-secret`, `DATABASE_URL` as above.
  `GOOGLE_CLIENT_ID/SECRET`, `APPLE_*`, `GEMINI_API_KEY`, and `MAIL_*` are all
  deliberately left **unset**, so tests exercise the "feature not configured"
  code paths by default; a couple of tests set/unset specific variables to
  toggle between the configured/unconfigured states.
- `WTF_CSRF_ENABLED = False` and `TESTING = True` on every test app instance,
  matching the existing suite's convention (CSRF form-token plumbing is not
  under test here).
- Runner: `pytest` (`pytest.ini` sets `pythonpath = .`).

## 3. Scope

**In scope:** functional/integration behavior reachable through Flask's
test client — route responses, status codes, redirects, flashed messages,
rendered-page content, and resulting database state. Includes ownership/
authorization checks (a user cannot see or modify another user's wines or
recipes), input validation on forms, and pure-function helpers
(`format_qty`, `_parse_servings`, `_parse_quantity`).

**Out of scope (not exercised by this pass):**
- Real OAuth handshakes with Google/Apple, and real Gemini/SMTP network
  calls — these require live third-party credentials and are exercised here
  only through their "not configured" / failure branches.
- Browser/JS behavior (the app has no client-side JS) and CSS/visual checks.
- Load, performance, and concurrency testing.
- Static analysis / type checking (no `mypy` config present in the repo).

## 4. Approach

1. **Baseline** the pre-existing suite (`tests/test_*.py`, 28 tests) as-is,
   unmodified, to confirm the starting state before adding anything.
2. **Extend coverage** with new test modules for gaps identified while
   reading every route in `app/*.py`, following the existing suite's
   conventions exactly (same env-var bootstrap, same `_app()` /
   `_logged_in_client()` helper pattern, `uuid`-suffixed emails/usernames to
   avoid cross-test collisions in the shared database):
   - `tests/test_navigation.py` — landing page (logged in vs. out), login
     gating on Recipe Tracker and Grocery List, unknown-route 404.
   - `tests/test_units.py` — pure helper functions (`format_qty` in
     `app/recipes.py`, `_parse_servings`, `_parse_quantity`) called directly,
     no HTTP/DB involved.
   - `tests/test_wines_extra.py` — editing a wine, malformed decimal price
     input, tasting-note deletion ownership check, 404 on a non-existent
     wine id.
   - `tests/test_recipes_extra.py` — editing a recipe (including the
     blank-name rejection path), deleting a recipe, 404 on a non-existent
     recipe id, cross-user comment-deletion ownership check.
   - `tests/test_account.py` — updating account email (success + duplicate
     rejection), password-change validation (short password, mismatched
     confirmation), and the "set a first password/username for an
     OAuth-only account" path.
   - `tests/test_oauth.py` — `/login/<provider>` and the OAuth callback
     route when Google/Apple are not configured in the environment.
   - `tests/test_grocery_extra.py` — blank-name submissions are ignored,
     deleting a single item.
3. **Run the full combined suite** (`pytest -q` and `-v`), capturing full
   output.
4. **Log** every failure/error, plus any non-fatal observations (warnings,
   flaky-looking behavior, notable design risks surfaced while writing
   tests) into `ERROR_LOG.md`. Per instructions, **no fix is attempted** —
   this pass only builds, runs, and reports.

## 5. Known risks / test-suite limitations worth flagging up front

- **Shared, non-isolated database.** No test resets or truncates tables
  between runs (except `test_clear_list_removes_everything`, which empties
  the *entire* `grocery_item` table — a table shared by every other test in
  the file/suite). Tests avoid collisions today only because they run
  serially and use unique usernames/emails; this would not survive
  parallelization (`pytest-xdist`) or reordering.
- **No fixtures/teardown.** Every test file re-declares `_app()` /
  `_logged_in_client()` locally instead of sharing a `conftest.py`. Rows
  created by one test run persist into the next `pytest` invocation (the DB
  is never dropped/recreated by the suite itself).
- **Environment coupling.** Tests that toggle "is this feature configured"
  (OAuth, Gemini, mail) mutate/rely on `os.environ` at import time in one
  file (`test_chat.py` pops `GEMINI_API_KEY`); running files in a different
  order or in the same process could leak state between them.
