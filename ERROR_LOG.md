# ZB Hub — Error Log

Results of the test pass described in `TEST_PLAN.md`, run against
`claude/project-hub-website-auth-8lqf7g` (PR #1, commit `4a9e6d0`). This is
a report only — **no application code was modified** to fix anything
listed below.

## Summary

| Run | Result |
|---|---|
| Pre-existing suite alone, clean DB (baseline) | 28/28 passed |
| Full suite (pre-existing + new tests added this pass), clean DB | 65/65 passed |
| Full suite **+ 2 new regression tests for defects found below** | 65 passed, **2 failed** |
| Same suite, re-run again with **no DB reset** between runs | 12-13 additional spurious failures (see Finding 3) |

The 2 failures below are reproducible defects in the application, isolated
with dedicated tests in `tests/test_known_defects.py`. Everything else in
the 67-test suite passes.

```
$ pytest -v
...
FAILED tests/test_known_defects.py::test_non_numeric_vintage_should_not_crash_the_server
FAILED tests/test_known_defects.py::test_reset_link_for_a_deleted_account_should_not_crash_the_server
========================= 2 failed, 65 passed in 6.26s =========================
```

---

## Finding 1 — Unhandled `ValueError` crashes wine/tasting forms on non-numeric input

- **Severity:** Medium (crashes the request with a 500; reachable by any
  logged-in user through normal form fields, no special access needed)
- **Location:** `app/wines.py:23-25`, `_optional_int()`
- **Reproduced by:** `tests/test_known_defects.py::test_non_numeric_vintage_should_not_crash_the_server`

```python
def _optional_int(form, key: str):
    value = form.get(key, "").strip()
    return int(value) if value else None
```

`int(value)` is not guarded. Its sibling `_optional_decimal()` right below
it *does* catch `InvalidOperation` and returns `None` on bad input — this
one doesn't catch the equivalent `ValueError`. `_optional_int` backs six
form fields across three routes:

- `POST /wines/new` and `POST /wines/<id>/edit` — `vintage`, `quantity`,
  `rating`, `drink_from`, `drink_by`
- `POST /wines/<id>/tastings` — `score`

**Repro:** `POST /wines/new` with `vintage=not-a-year` (or any non-numeric
value in any of the six fields above) → unhandled `ValueError`, Flask
returns HTTP 500 instead of a validation message like the rest of the form
uses (e.g. "Score is required to log a tasting.").

```
File "app/wines.py", line 71, in new_wine
    wine = Wine(user_id=current_user.id, **_wine_fields_from_form(request.form))
File "app/wines.py", line 42, in _wine_fields_from_form
    "vintage": _optional_int(form, "vintage"),
File "app/wines.py", line 25, in _optional_int
    return int(value) if value else None
ValueError: invalid literal for int() with base 10: 'not-a-year'
```

The HTML `<input type="number">` on the real form discourages this from a
mouse/keyboard user, but it's still directly reachable (curl, a modified
request, a non-JS client) and produces a bare 500 rather than a handled
error.

---

## Finding 2 — Unhandled `AttributeError` if a password-reset token outlives its account

- **Severity:** Low (narrow race window, not attacker-controlled) but a
  genuine unhandled crash path
- **Location:** `app/auth.py:250-252`, `reset_password()`
- **Reproduced by:** `tests/test_known_defects.py::test_reset_link_for_a_deleted_account_should_not_crash_the_server`

```python
else:
    user = db.session.get(User, user_id)
    user.set_password(password)
```

`_verify_reset_token()` only checks the signature and max-age of the token
— it does not check that the `user_id` it encodes still exists. If the
account is deleted (or, in principle, never existed) between the token
being issued and the reset form being submitted, `db.session.get(User,
user_id)` returns `None` and the very next line crashes:

```
File "app/auth.py", line 252, in reset_password
    user.set_password(password)
AttributeError: 'NoneType' object has no attribute 'set_password'
```

The 30-minute token lifetime (`RESET_TOKEN_MAX_AGE`) keeps the window
small, but the failure mode when it does happen is a bare 500 rather than
the same "invalid or has expired" message already used elsewhere in this
function for a bad token.

---

## Finding 3 — Test suite is not idempotent against its own (persistent) database

- **Severity:** Test-infrastructure issue, not an application defect —
  flagged because it was directly observed while running the suite twice.
- **Where:** every test file under `tests/` (pre-existing and newly added
  alike)

None of the test files reset, truncate, or use a transactional rollback
around the shared Postgres database (no `conftest.py`, no `create_all` /
`drop_all`, no per-test transaction). Several tests look up rows they just
created by a **non-unique** field using `.filter_by(...).one()` (e.g. wine
or recipe `name`, a hard-coded literal like `"Sancerre"` or `"Pancakes"`).

The first `pytest` run after a fresh migration passes cleanly (65/65 — see
summary table). Running `pytest` again immediately afterward, against the
same database and with no changes, reproducibly breaks 12 of the
already-passed tests:

```
$ pytest -q        # first run
65 passed in 5.93s

$ pytest -q        # second run, same DB, nothing else changed
FAILED tests/test_recipes.py::test_create_recipe_with_ingredients_and_steps
FAILED tests/test_recipes.py::test_recipe_scaling_doubles_quantities
FAILED tests/test_recipes.py::test_add_and_delete_comment
FAILED tests/test_recipes.py::test_add_recipe_ingredients_to_grocery_list
FAILED tests/test_recipes.py::test_recipe_requires_ownership
FAILED tests/test_recipes_extra.py::test_edit_recipe_rejects_blank_name
FAILED tests/test_recipes_extra.py::test_add_comment_requires_ownership
FAILED tests/test_wines.py::test_tasting_log_decrements_quantity_and_lists_history
FAILED tests/test_wines.py::test_tasting_requires_score
FAILED tests/test_wines.py::test_wine_detail_requires_ownership
FAILED tests/test_wines_extra.py::test_invalid_purchase_price_is_stored_as_none
FAILED tests/test_wines_extra.py::test_delete_tasting_requires_ownership
12 failed, 53 passed in 6.86s
```

Every failure is the same root cause — `sqlalchemy.exc.MultipleResultsFound:
Multiple rows were found when exactly one was required` — because the
second run inserted a second "Sancerre", second "Pancakes", etc., and the
helper that looks the row back up by name (`_wine_id()` / `_recipe_id()` in
each test file) can no longer disambiguate. This reproduces with the
pre-existing test files alone (`test_recipes.py`, `test_wines.py`); the new
files added this pass (`test_wines_extra.py`, `test_recipes_extra.py`)
inherited the same convention and fail the same way on a second run.

This does not affect the pass/fail counts reported above (both official
runs were against a freshly migrated, empty database), but it means:
- CI or any environment that reuses a database across test runs (rather
  than recreating it) will see intermittent, confusing failures unrelated
  to any real code change.
- `pytest-xdist` / parallel execution would very likely hit the same
  collisions even on a single fresh run.

No fix (e.g. adding a `conftest.py` with per-test transaction rollback, or
switching lookups to a value scoped by the owning user/uuid) was applied,
per the instructions for this pass.

---

## Everything else: passing

The remaining 65 tests — the full pre-existing suite (28 tests) plus the
new coverage added for this pass (37 tests across `test_navigation.py`,
`test_units.py`, `test_wines_extra.py`, `test_recipes_extra.py`,
`test_account.py`, `test_oauth.py`, `test_grocery_extra.py`) — pass
consistently on a freshly migrated database. See `TEST_PLAN.md` §4 for what
each new file covers.
