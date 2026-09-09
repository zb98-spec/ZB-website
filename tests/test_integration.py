"""Integration tests: exercise one feature/route at a time through Flask's
test client against a real database (migrations applied, see TEST_PLAN.md).
Each test targets a single blueprint's behavior in relative isolation -
auth, wines, recipes, grocery, account, OAuth routing, AI wine research,
the Telegram bot webhook, and the two known defects captured as regression
tests at the bottom of this file.

For multi-step flows that chain several features together in one session
(the way a real user actually moves through the app), see test_e2e.py.
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)
# Exercise the "not configured" branches of OAuth/Gemini by default - a
# couple of tests below rely on these being unset.
for _var in (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "APPLE_CLIENT_ID",
    "APPLE_TEAM_ID",
    "APPLE_KEY_ID",
    "APPLE_PRIVATE_KEY",
    "GEMINI_API_KEY",
):
    os.environ.pop(_var, None)
# The Telegram bot section below needs these set to reach its routes at
# all (telegram_enabled() gates them) - every test in this file that
# doesn't care about Telegram is unaffected, since nothing else in this
# suite renders Telegram-conditional content except account.html's
# "Telegram" section, which no other test asserts the absence of.
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:fake-token-for-tests"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-webhook-secret"
TELEGRAM_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]

from app import create_app  # noqa: E402
from app.auth import _make_reset_token  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import GroceryItem, Recipe, TastingNote, User, Wine  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _logged_in_client(app, name="Pytest"):
    client = app.test_client()
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", name=name)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


def _unique_username():
    return f"user-{uuid.uuid4().hex[:12]}"


def _register(app, client, username=None, password="correcthorse"):
    username = username or _unique_username()
    client.post(
        "/register",
        data={"username": username, "password": password, "confirm_password": password},
        follow_redirects=True,
    )
    return username


def _wine_id(app, name):
    with app.app_context():
        return Wine.query.filter_by(name=name).one().id


def _recipe_id(app, name):
    with app.app_context():
        return Recipe.query.filter_by(name=name).one().id


def _create_pancakes(client, name="Pancakes", servings="4"):
    return client.post(
        "/recipes/new",
        data={
            "name": name,
            "servings": servings,
            # a trailing blank row (as the real form would submit for
            # unused rows) should be skipped rather than saved
            "ingredient_name[]": ["flour", "sugar", "salt", ""],
            "ingredient_qty[]": ["2", "3", "", ""],
            "ingredient_unit[]": ["cup", "tbsp", "", ""],
            "step[]": ["Mix dry ingredients.", "Cook on a griddle.", ""],
        },
        follow_redirects=True,
    )


def _create_simple_recipe(client, name, servings="4"):
    return client.post(
        "/recipes/new",
        data={
            "name": name,
            "servings": servings,
            "ingredient_name[]": ["rice"],
            "ingredient_qty[]": ["1"],
            "ingredient_unit[]": ["cup"],
            "step[]": ["Cook it."],
        },
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Smoke / navigation
# ---------------------------------------------------------------------------

def test_welcome_page_loads():
    resp = _app().test_client().get("/")
    assert resp.status_code == 200
    assert b"ZB Hub" in resp.data


def test_login_page_loads():
    resp = _app().test_client().get("/login")
    assert resp.status_code == 200
    assert b"Continue with" in resp.data or b"not configured" in resp.data


def test_wines_requires_login():
    resp = _app().test_client().get("/wines/", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_index_page_logged_out_shows_hero():
    resp = _app().test_client().get("/")
    assert resp.status_code == 200
    assert b"Get started" in resp.data
    assert b"Welcome back" not in resp.data


def test_index_page_logged_in_shows_projects():
    app = _app()
    client = _logged_in_client(app, name="Pytest Nav")
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Welcome back" in resp.data
    assert b"Wine Library" in resp.data
    assert b"Recipe Tracker" in resp.data
    assert b"Grocery List" in resp.data


def test_recipes_requires_login():
    resp = _app().test_client().get("/recipes/", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_grocery_requires_login():
    resp = _app().test_client().get("/grocery/", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_unknown_route_returns_404():
    resp = _app().test_client().get("/this-route-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth: username/password registration and login
# ---------------------------------------------------------------------------

def test_register_creates_account_and_logs_in():
    app = _app()
    client = app.test_client()
    username = _unique_username()

    resp = client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert username.encode() in resp.data  # shown in the nav once logged in

    with app.app_context():
        user = User.query.filter_by(username=username).one()
        assert user.check_password("correcthorse")
        assert not user.check_password("wrongpassword")


def test_register_rejects_mismatched_passwords_and_short_passwords():
    app = _app()
    client = app.test_client()
    username = _unique_username()

    resp = client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "different"},
        follow_redirects=True,
    )
    assert b"Passwords don&#39;t match" in resp.data or b"don't match" in resp.data
    with app.app_context():
        assert User.query.filter_by(username=username).first() is None

    resp = client.post(
        "/register",
        data={"username": username, "password": "short", "confirm_password": "short"},
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data
    with app.app_context():
        assert User.query.filter_by(username=username).first() is None


def test_register_rejects_duplicate_username():
    app = _app()
    username = _unique_username()

    client1 = app.test_client()
    client1.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    client2 = app.test_client()
    resp = client2.post(
        "/register",
        data={"username": username, "password": "anotherpassword", "confirm_password": "anotherpassword"},
        follow_redirects=True,
    )
    assert b"already taken" in resp.data


def test_login_with_username_and_password():
    app = _app()
    username = _unique_username()

    setup_client = app.test_client()
    setup_client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    login_client = app.test_client()
    resp = login_client.post(
        "/login/password",
        data={"username": username, "password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert username.encode() in resp.data

    resp = login_client.get("/wines/")
    assert resp.status_code == 200  # logged in, not redirected to /login


def test_login_with_wrong_password_fails():
    app = _app()
    username = _unique_username()

    setup_client = app.test_client()
    setup_client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    login_client = app.test_client()
    resp = login_client.post(
        "/login/password",
        data={"username": username, "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert b"Incorrect username or password" in resp.data

    resp = login_client.get("/wines/", follow_redirects=False)
    assert resp.status_code == 302  # still logged out


# ---------------------------------------------------------------------------
# Account & login security: change password, lockout, password reset
# ---------------------------------------------------------------------------

def test_change_password_requires_current_password():
    app = _app()
    client = app.test_client()
    _register(app, client, password="originalpass")

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "current_password": "wrongpass",
            "new_password": "newpassword1",
            "confirm_new_password": "newpassword1",
        },
        follow_redirects=True,
    )
    assert b"Current password is incorrect" in resp.data


def test_change_password_success():
    app = _app()
    client = app.test_client()
    username = _register(app, client, password="originalpass")

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "current_password": "originalpass",
            "new_password": "newpassword1",
            "confirm_new_password": "newpassword1",
        },
        follow_redirects=True,
    )
    assert b"Password updated" in resp.data

    old_password_client = app.test_client()
    resp = old_password_client.post(
        "/login/password",
        data={"username": username, "password": "originalpass"},
        follow_redirects=True,
    )
    assert b"Incorrect username or password" in resp.data

    new_password_client = app.test_client()
    resp = new_password_client.post(
        "/login/password",
        data={"username": username, "password": "newpassword1"},
        follow_redirects=True,
    )
    assert username.encode() in resp.data


def test_login_locks_out_after_repeated_failures():
    app = _app()
    setup_client = app.test_client()
    username = _register(app, setup_client, password="correcthorse")

    attacker = app.test_client()
    for _ in range(5):
        attacker.post(
            "/login/password",
            data={"username": username, "password": "wrongpassword"},
            follow_redirects=True,
        )

    # 6th attempt, even with the RIGHT password, should now be locked out
    resp = attacker.post(
        "/login/password",
        data={"username": username, "password": "correcthorse"},
        follow_redirects=True,
    )
    assert b"Too many failed attempts" in resp.data

    resp = attacker.get("/wines/", follow_redirects=False)
    assert resp.status_code == 302  # still not logged in


def test_successful_login_resets_failed_count():
    app = _app()
    setup_client = app.test_client()
    username = _register(app, setup_client, password="correcthorse")

    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.failed_login_count = 3
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        "/login/password",
        data={"username": username, "password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        user = User.query.filter_by(username=username).one()
        assert user.failed_login_count == 0
        assert user.locked_until is None


def test_forgot_password_redirects_when_mail_not_configured():
    app = _app()
    client = app.test_client()
    resp = client.get("/forgot-password", follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_reset_password_rejects_invalid_token():
    app = _app()
    client = app.test_client()
    resp = client.get("/reset-password/not-a-real-token", follow_redirects=True)
    assert b"invalid or has expired" in resp.data


# ---------------------------------------------------------------------------
# Account: email updates, password-change validation, OAuth-only accounts
# ---------------------------------------------------------------------------

def test_update_email_success():
    app = _app()
    client = app.test_client()
    _register(app, client)
    new_email = f"new-address-{uuid.uuid4()}@example.com"

    resp = client.post(
        "/account",
        data={"action": "update_email", "email": new_email},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Email updated" in resp.data
    assert new_email.encode() in resp.data


def test_update_email_rejects_duplicate():
    app = _app()
    taken_email = f"taken-{uuid.uuid4()}@example.com"

    holder_client = app.test_client()
    _register(app, holder_client)
    holder_client.post(
        "/account", data={"action": "update_email", "email": taken_email}, follow_redirects=True
    )

    other_client = app.test_client()
    _register(app, other_client)
    resp = other_client.post(
        "/account", data={"action": "update_email", "email": taken_email}, follow_redirects=True
    )
    assert b"already in use by another account" in resp.data


def test_change_password_rejects_short_new_password():
    app = _app()
    client = app.test_client()
    _register(app, client, password="originalpass")

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "current_password": "originalpass",
            "new_password": "short",
            "confirm_new_password": "short",
        },
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data


def test_change_password_rejects_mismatched_confirmation():
    app = _app()
    client = app.test_client()
    _register(app, client, password="originalpass")

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "current_password": "originalpass",
            "new_password": "newpassword1",
            "confirm_new_password": "somethingelse",
        },
        follow_redirects=True,
    )
    assert b"don&#39;t match" in resp.data or b"don't match" in resp.data


def test_oauth_only_account_can_set_first_password_and_username():
    app = _app()
    client = _logged_in_client(app, name="OAuth Only")
    new_username = f"oauth-user-{uuid.uuid4().hex[:10]}"

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "username": new_username,
            "new_password": "brandnewpass",
            "confirm_new_password": "brandnewpass",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Password updated" in resp.data

    login_client = app.test_client()
    resp = login_client.post(
        "/login/password",
        data={"username": new_username, "password": "brandnewpass"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"OAuth Only" in resp.data  # nav shows the logged-in user's name


# ---------------------------------------------------------------------------
# OAuth routes (Google/Apple deliberately left unconfigured - see top of file)
# ---------------------------------------------------------------------------

def test_login_redirect_flashes_when_google_not_configured():
    client = _app().test_client()
    resp = client.get("/login/google", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Google sign-in isn&#39;t configured yet" in resp.data


def test_login_redirect_flashes_when_apple_not_configured():
    client = _app().test_client()
    resp = client.get("/login/apple", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Apple sign-in isn&#39;t configured yet" in resp.data


def test_oauth_callback_404s_for_unconfigured_provider():
    client = _app().test_client()
    resp = client.get("/login/google/callback")
    assert resp.status_code == 404


def test_oauth_callback_404s_for_unknown_provider():
    client = _app().test_client()
    resp = client.get("/login/not-a-real-provider/callback")
    assert resp.status_code == 404


def test_login_page_shows_disabled_buttons_when_unconfigured():
    client = _app().test_client()
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Google sign-in not configured" in resp.data
    assert b"Apple sign-in not configured" in resp.data


# ---------------------------------------------------------------------------
# Wine Library
# ---------------------------------------------------------------------------

def test_add_edit_delete_wine():
    app = _app()
    client = _logged_in_client(app)

    resp = client.post(
        "/wines/new",
        data={"name": "Opus One", "vintage": "2018", "quantity": "2"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Opus One" in resp.data

    resp = client.get("/wines/")
    assert b"Opus One" in resp.data
    assert b"2018" in resp.data

    wine_id = _wine_id(app, "Opus One")
    resp = client.post(
        f"/wines/{wine_id}/delete", data={}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Wine removed from your cellar" in resp.data


def test_tasting_log_decrements_quantity_and_lists_history():
    app = _app()
    client = _logged_in_client(app)

    client.post(
        "/wines/new",
        data={"name": "Sancerre", "vintage": "2021", "quantity": "3"},
        follow_redirects=True,
    )
    wine_id = _wine_id(app, "Sancerre")

    resp = client.get(f"/wines/{wine_id}")
    assert resp.status_code == 200
    assert b"Sancerre" in resp.data
    assert b"No tastings logged yet" in resp.data

    resp = client.post(
        f"/wines/{wine_id}/tastings",
        data={
            "tasted_on": "2026-01-15",
            "score": "92",
            "occasion": "Anniversary dinner",
            "people": "Sarah, John",
            "notes": "Bright citrus, great with oysters.",
            "decrement_quantity": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Tasting logged" in resp.data
    assert b"92" in resp.data
    assert b"Anniversary dinner" in resp.data
    assert b"Sarah, John" in resp.data
    assert b"Bright citrus" in resp.data
    assert b"No tastings logged yet" not in resp.data

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.quantity == 2  # dropped from 3


def test_tasting_requires_score():
    app = _app()
    client = _logged_in_client(app)

    client.post(
        "/wines/new",
        data={"name": "Ridge Zinfandel", "quantity": "1"},
        follow_redirects=True,
    )
    wine_id = _wine_id(app, "Ridge Zinfandel")

    resp = client.post(
        f"/wines/{wine_id}/tastings",
        data={"tasted_on": "2026-01-15"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Score is required" in resp.data

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert len(wine.tastings) == 0
        assert wine.quantity == 1  # unchanged - nothing was logged


def test_wine_detail_requires_ownership():
    app = _app()
    owner_client = _logged_in_client(app)
    owner_client.post(
        "/wines/new", data={"name": "Private Bottle", "quantity": "1"}, follow_redirects=True
    )
    wine_id = _wine_id(app, "Private Bottle")

    other_client = _logged_in_client(app)
    resp = other_client.get(f"/wines/{wine_id}")
    assert resp.status_code == 404


def test_edit_wine_updates_fields():
    app = _app()
    client = _logged_in_client(app)
    client.post(
        "/wines/new",
        data={"name": "Barolo", "vintage": "2015", "quantity": "1"},
        follow_redirects=True,
    )
    wine_id = _wine_id(app, "Barolo")

    resp = client.post(
        f"/wines/{wine_id}/edit",
        data={"name": "Barolo Riserva", "vintage": "2016", "quantity": "5"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Wine updated" in resp.data
    assert b"Barolo Riserva" in resp.data

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.name == "Barolo Riserva"
        assert wine.vintage == 2016
        assert wine.quantity == 5


def test_invalid_purchase_price_is_stored_as_none():
    app = _app()
    client = _logged_in_client(app)
    client.post(
        "/wines/new",
        data={"name": "Bad Price Wine", "quantity": "1", "purchase_price": "not-a-number"},
        follow_redirects=True,
    )
    wine_id = _wine_id(app, "Bad Price Wine")

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.purchase_price is None


def test_delete_tasting_requires_ownership():
    app = _app()
    owner_client = _logged_in_client(app)
    owner_client.post(
        "/wines/new", data={"name": "Guarded Wine", "quantity": "1"}, follow_redirects=True
    )
    wine_id = _wine_id(app, "Guarded Wine")
    owner_client.post(
        f"/wines/{wine_id}/tastings",
        data={"tasted_on": "2026-01-15", "score": "88"},
        follow_redirects=True,
    )
    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        tasting_id = wine.tastings[0].id

    other_client = _logged_in_client(app)
    resp = other_client.post(
        f"/wines/{wine_id}/tastings/{tasting_id}/delete", follow_redirects=False
    )
    assert resp.status_code == 404

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert len(wine.tastings) == 1  # untouched


def test_wine_detail_404_for_nonexistent_wine():
    app = _app()
    client = _logged_in_client(app)
    resp = client.get("/wines/999999999")
    assert resp.status_code == 404


def test_new_wine_page_requires_login():
    resp = _app().test_client().get("/wines/new", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


# ---------------------------------------------------------------------------
# Wine chat assistant (Gemini deliberately left unconfigured - see top of file)
# ---------------------------------------------------------------------------

def test_chat_redirects_when_gemini_not_configured():
    app = _app()
    client = _logged_in_client(app)
    resp = client.get("/wines/chat", follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_wine_library_hides_chat_link_when_not_configured():
    app = _app()
    client = _logged_in_client(app)
    resp = client.get("/wines/")
    assert b"Ask the Wine Assistant" not in resp.data


# ---------------------------------------------------------------------------
# AI wine research ("Research all with AI", Gemini deliberately left
# unconfigured by default - individual tests below toggle GEMINI_API_KEY
# and mock the network call rather than hitting the real Gemini API).
# ---------------------------------------------------------------------------

def test_research_all_redirects_when_not_configured():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Test Wine", "quantity": "1"}, follow_redirects=True)

    resp = client.post("/wines/research-all", follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_research_all_updates_wine_fields():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Researchable Wine", "quantity": "1"}, follow_redirects=True)

    fake_result = {
        "rating": 92,
        "estimated_price": 45.5,
        "drink_from": 2024,
        "drink_by": 2030,
        "tasting_notes": "Notes of cherry and oak.",
    }

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", return_value=fake_result) as mocked:
            resp = client.post("/wines/research-all", follow_redirects=True)
        assert mocked.called
        assert b"Researched 1 wine" in resp.data

        with app.app_context():
            wine = Wine.query.filter_by(name="Researchable Wine").one()
            assert wine.rating == 92
            assert float(wine.estimated_price) == 45.5
            assert wine.drink_from == 2024
            assert wine.drink_by == 2030
            assert wine.tasting_profile == "Notes of cherry and oak."
            assert wine.researched_at is not None
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_research_all_counts_failures_without_crashing():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Failing Wine", "quantity": "1"}, follow_redirects=True)

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", side_effect=RuntimeError("boom")):
            resp = client.post("/wines/research-all", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Researched 0 wines" in resp.data
        assert b"1 failed" in resp.data
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_research_all_ignores_out_of_range_rating():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Bad Data Wine", "quantity": "1"}, follow_redirects=True)

    fake_result = {
        "rating": 500,  # out of 1-100 range - should be rejected, not stored
        "estimated_price": -10,  # negative - should be rejected
        "drink_from": 2030,
        "drink_by": 2020,  # from > by - should be rejected as a pair
        "tasting_notes": "Fine.",
    }

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", return_value=fake_result):
            client.post("/wines/research-all", follow_redirects=True)
        with app.app_context():
            wine = Wine.query.filter_by(name="Bad Data Wine").one()
            assert wine.rating is None
            assert wine.estimated_price is None
            assert wine.drink_from is None and wine.drink_by is None
            assert wine.tasting_profile == "Fine."  # the one valid field is still saved
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


# ---------------------------------------------------------------------------
# Recipe Tracker
# ---------------------------------------------------------------------------

def test_create_recipe_with_ingredients_and_steps():
    app = _app()
    client = _logged_in_client(app)

    resp = _create_pancakes(client)
    assert resp.status_code == 200
    assert b"Pancakes" in resp.data
    assert b"flour" in resp.data
    assert b"salt" in resp.data  # has no quantity, but a name, so it's kept
    assert b"Mix dry ingredients" in resp.data

    with app.app_context():
        recipe = Recipe.query.filter_by(name="Pancakes").one()
        assert len(recipe.ingredients) == 3  # flour, sugar, salt - blank row skipped
        assert len(recipe.steps) == 2  # blank row skipped
        salt = next(i for i in recipe.ingredients if i.name == "salt")
        assert salt.quantity is None


def test_recipe_scaling_doubles_quantities():
    app = _app()
    client = _logged_in_client(app)
    _create_pancakes(client, name="Scalable Pancakes", servings="4")
    recipe_id = _recipe_id(app, "Scalable Pancakes")

    resp = client.get(f"/recipes/{recipe_id}?servings=8")
    assert resp.status_code == 200
    assert b"4 cup" in resp.data  # 2 cups flour * 2 = 4 cups
    assert b"6 tbsp" in resp.data  # 3 tbsp sugar * 2 = 6 tbsp


def test_add_and_delete_comment():
    app = _app()
    client = _logged_in_client(app)
    _create_pancakes(client, name="Commented Pancakes")
    recipe_id = _recipe_id(app, "Commented Pancakes")

    resp = client.post(
        f"/recipes/{recipe_id}/comments",
        data={"body": "Add more vanilla next time."},
        follow_redirects=True,
    )
    assert b"Add more vanilla next time." in resp.data

    with app.app_context():
        recipe = Recipe.query.filter_by(name="Commented Pancakes").one()
        comment_id = recipe.comments[0].id

    resp = client.post(
        f"/recipes/{recipe_id}/comments/{comment_id}/delete",
        follow_redirects=True,
    )
    assert b"Add more vanilla next time." not in resp.data


def test_add_recipe_ingredients_to_grocery_list():
    app = _app()
    client = _logged_in_client(app)
    _create_pancakes(client, name="Grocery Pancakes", servings="4")
    recipe_id = _recipe_id(app, "Grocery Pancakes")

    resp = client.post(
        f"/recipes/{recipe_id}/add-to-grocery-list",
        data={"servings": "4"},
        follow_redirects=True,
    )
    assert b"Added 3 ingredient(s)" in resp.data

    with app.app_context():
        names = {item.name for item in GroceryItem.query.all()}
        assert {"flour", "sugar", "salt"} <= names


def test_recipe_requires_ownership():
    app = _app()
    owner = _logged_in_client(app)
    _create_pancakes(owner, name="Private Pancakes")
    recipe_id = _recipe_id(app, "Private Pancakes")

    other = _logged_in_client(app)
    resp = other.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 404


def test_edit_recipe_rejects_blank_name():
    app = _app()
    client = _logged_in_client(app)
    _create_simple_recipe(client, "Editable Recipe")
    recipe_id = _recipe_id(app, "Editable Recipe")

    resp = client.post(
        f"/recipes/{recipe_id}/edit",
        data={"name": "", "servings": "4", "ingredient_name[]": [""], "step[]": [""]},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Recipe name is required" in resp.data

    with app.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe.name == "Editable Recipe"  # unchanged


def test_edit_recipe_updates_name_and_servings():
    app = _app()
    client = _logged_in_client(app)
    _create_simple_recipe(client, "Old Name")
    recipe_id = _recipe_id(app, "Old Name")

    resp = client.post(
        f"/recipes/{recipe_id}/edit",
        data={
            "name": "New Name",
            "servings": "8",
            "ingredient_name[]": ["rice"],
            "ingredient_qty[]": ["1"],
            "ingredient_unit[]": ["cup"],
            "step[]": ["Cook it."],
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Recipe updated" in resp.data

    with app.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe.name == "New Name"
        assert recipe.servings == 8


def test_delete_recipe_removes_it():
    app = _app()
    client = _logged_in_client(app)
    _create_simple_recipe(client, "Doomed Recipe")
    recipe_id = _recipe_id(app, "Doomed Recipe")

    resp = client.post(f"/recipes/{recipe_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Recipe deleted" in resp.data

    with app.app_context():
        assert db.session.get(Recipe, recipe_id) is None


def test_recipe_detail_404_for_nonexistent_recipe():
    app = _app()
    client = _logged_in_client(app)
    resp = client.get("/recipes/999999999")
    assert resp.status_code == 404


def test_add_comment_requires_ownership():
    app = _app()
    owner = _logged_in_client(app)
    _create_simple_recipe(owner, "Guarded Recipe")
    recipe_id = _recipe_id(app, "Guarded Recipe")

    other = _logged_in_client(app)
    resp = other.post(
        f"/recipes/{recipe_id}/comments",
        data={"body": "Sneaky comment"},
        follow_redirects=False,
    )
    assert resp.status_code == 404

    with app.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert len(recipe.comments) == 0


# ---------------------------------------------------------------------------
# Grocery List
# ---------------------------------------------------------------------------

def test_add_and_delete_item():
    app = _app()
    client = _logged_in_client(app)

    resp = client.post(
        "/grocery/add", data={"name": "Milk", "quantity": "1 gallon"}, follow_redirects=True
    )
    assert b"Milk" in resp.data
    assert b"1 gallon" in resp.data


def test_list_is_shared_across_users():
    app = _app()
    alice = _logged_in_client(app, name="Alice")
    bob = _logged_in_client(app, name="Bob")

    alice.post("/grocery/add", data={"name": "Eggs", "quantity": "1 dozen"}, follow_redirects=True)

    resp = bob.get("/grocery/")
    assert b"Eggs" in resp.data
    assert b"Alice" in resp.data  # shows who added it


def test_clear_list_removes_everything():
    app = _app()
    client = _logged_in_client(app)
    client.post("/grocery/add", data={"name": "Bread"}, follow_redirects=True)
    client.post("/grocery/add", data={"name": "Butter"}, follow_redirects=True)

    resp = client.post("/grocery/clear", follow_redirects=True)
    assert b"Bread" not in resp.data
    assert b"Butter" not in resp.data
    assert b"The list is empty" in resp.data


def test_add_item_with_blank_name_is_ignored():
    app = _app()
    client = _logged_in_client(app)

    with app.app_context():
        before_count = GroceryItem.query.count()

    resp = client.post("/grocery/add", data={"name": "   "}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert GroceryItem.query.count() == before_count


def test_delete_item_removes_only_that_item():
    app = _app()
    client = _logged_in_client(app)
    unique_a = f"Item-A-{uuid.uuid4().hex[:8]}"
    unique_b = f"Item-B-{uuid.uuid4().hex[:8]}"

    client.post("/grocery/add", data={"name": unique_a}, follow_redirects=True)
    client.post("/grocery/add", data={"name": unique_b}, follow_redirects=True)

    with app.app_context():
        item_a_id = GroceryItem.query.filter_by(name=unique_a).one().id

    resp = client.post(f"/grocery/{item_a_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert unique_a.encode() not in resp.data
    assert unique_b.encode() in resp.data


def test_delete_nonexistent_item_is_a_noop():
    app = _app()
    client = _logged_in_client(app)
    resp = client.post("/grocery/999999999/delete", follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Telegram bot webhook (TELEGRAM_BOT_TOKEN / TELEGRAM_WEBHOOK_SECRET are set
# at the top of this file so telegram_enabled() is true for every test
# below; _send_message is always mocked, so nothing here calls the real
# Telegram API).
# ---------------------------------------------------------------------------

def _make_telegram_user(app, **kwargs):
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", **kwargs)
        db.session.add(user)
        db.session.commit()
        return user.id


def _post_telegram_update(client, text, chat_id=111, secret=TELEGRAM_SECRET):
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": chat_id}, "text": text}},
        headers=headers,
    )


def _linked_telegram_client(app, chat_id):
    user_id = _make_telegram_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_chat_id = chat_id
        db.session.commit()
    return app.test_client(), user_id


def test_webhook_rejects_missing_or_wrong_secret():
    app = _app()
    client = app.test_client()
    resp = _post_telegram_update(client, "/help", secret="wrong-secret")
    assert resp.status_code == 403

    resp = _post_telegram_update(client, "/help", secret=None)
    assert resp.status_code == 403


def test_help_command_replies_without_needing_a_link():
    app = _app()
    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        resp = _post_telegram_update(client, "/help", chat_id=222)
    assert resp.status_code == 200
    assert sent.called
    chat_id, text = sent.call_args[0]
    assert chat_id == 222
    assert "/window" in text


def test_unlinked_chat_is_told_to_link():
    app = _app()
    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/window", chat_id=333)
    _, text = sent.call_args[0]
    assert "/link" in text


def test_link_flow_connects_chat_to_account():
    app = _app()
    user_id = _make_telegram_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_link_code = "ABC123"
        user.telegram_link_code_expires = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/link ABC123", chat_id=444)
    _, text = sent.call_args[0]
    assert "Linked!" in text

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.telegram_chat_id == 444
        assert user.telegram_link_code is None


def test_link_rejects_expired_code():
    app = _app()
    user_id = _make_telegram_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_link_code = "STALE1"
        user.telegram_link_code_expires = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/link STALE1", chat_id=555)
    _, text = sent.call_args[0]
    assert "invalid or expired" in text


def test_add_command_creates_wine():
    app = _app()
    client, user_id = _linked_telegram_client(app, chat_id=666)

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/add TG Opus One | Telegram Winery | 2018 | red | 2", chat_id=666)
    _, text = sent.call_args[0]
    assert "Added #" in text
    assert "TG Opus One" in text

    with app.app_context():
        wine = Wine.query.filter_by(user_id=user_id, name="TG Opus One").one()
        assert wine.producer == "Telegram Winery"
        assert wine.vintage == 2018
        assert wine.wine_type == "red"
        assert wine.quantity == 2


def test_add_command_with_only_a_name():
    app = _app()
    client, user_id = _linked_telegram_client(app, chat_id=667)

    with patch("app.telegram_bot._send_message"):
        _post_telegram_update(client, "/add Mystery Bottle", chat_id=667)

    with app.app_context():
        wine = Wine.query.filter_by(user_id=user_id, name="Mystery Bottle").one()
        assert wine.quantity == 1
        assert wine.producer is None


def test_window_command_lists_only_wines_in_range():
    app = _app()
    client, user_id = _linked_telegram_client(app, chat_id=777)
    year = datetime.utcnow().year

    with app.app_context():
        db.session.add_all([
            Wine(user_id=user_id, name="In Window", quantity=1, drink_from=year - 1, drink_by=year + 1),
            Wine(user_id=user_id, name="Too Young", quantity=1, drink_from=year + 5, drink_by=year + 10),
            Wine(user_id=user_id, name="No Window Set", quantity=1),
        ])
        db.session.commit()

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/window", chat_id=777)
    _, text = sent.call_args[0]
    assert "In Window" in text
    assert "Too Young" not in text
    assert "No Window Set" not in text


def test_notes_and_log_commands():
    app = _app()
    client, user_id = _linked_telegram_client(app, chat_id=888)

    with app.app_context():
        wine = Wine(user_id=user_id, name="TG Sancerre", quantity=3, rating=90)
        db.session.add(wine)
        db.session.commit()
        wine_id = wine.id

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/notes TG Sancerre", chat_id=888)
    _, text = sent.call_args[0]
    assert "90/100" in text

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/log TG Sancerre | 88 | Great with oysters", chat_id=888)
    _, text = sent.call_args[0]
    assert "88/100" in text

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.quantity == 2  # decremented
        tasting = TastingNote.query.filter_by(wine_id=wine_id).one()
        assert tasting.score == 88
        assert tasting.notes == "Great with oysters"


def test_ambiguous_query_lists_candidates_with_ids():
    app = _app()
    client, user_id = _linked_telegram_client(app, chat_id=999)

    with app.app_context():
        db.session.add_all([
            Wine(user_id=user_id, name="Cabernet A", quantity=1),
            Wine(user_id=user_id, name="Cabernet B", quantity=1),
        ])
        db.session.commit()

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client, "/notes Cabernet", chat_id=999)
    _, text = sent.call_args[0]
    assert "Multiple matches" in text
    assert "Cabernet A" in text and "Cabernet B" in text


def test_add_command_cannot_touch_another_users_cellar():
    app = _app()
    client_a, user_a = _linked_telegram_client(app, chat_id=1001)
    client_b, user_b = _linked_telegram_client(app, chat_id=1002)

    with patch("app.telegram_bot._send_message"):
        _post_telegram_update(client_a, "/add TG Private Bottle", chat_id=1001)

    with app.app_context():
        wine = Wine.query.filter_by(name="TG Private Bottle").one()
        assert wine.user_id == user_a
        assert wine.user_id != user_b

    with patch("app.telegram_bot._send_message") as sent:
        _post_telegram_update(client_b, "/notes TG Private Bottle", chat_id=1002)
    _, text = sent.call_args[0]
    assert "No wine found" in text


# ---------------------------------------------------------------------------
# Known defects - regression tests for real bugs found while building out
# this suite. See ERROR_LOG.md for full details. Not fixed here - marked
# xfail(strict=True) so CI reports them without going red: they show up as
# "xfailed" (expected, tracked) as long as the bug is still there, but the
# moment either underlying bug actually gets fixed, the test starts
# "xpassing" and strict=True turns that into a real CI failure - the signal
# to come remove the marker, not a bug getting silently un-tracked.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="app/wines.py:_optional_int - see ERROR_LOG.md Finding 1", strict=True)
def test_non_numeric_vintage_should_not_crash_the_server():
    """app/wines.py:_optional_int has no try/except around int(value), unlike
    its sibling _optional_decimal (which catches InvalidOperation). Any
    non-numeric value in vintage/quantity/rating/drink_from/drink_by raises
    an unhandled ValueError -> HTTP 500, instead of a friendly validation
    message like the rest of the form uses."""
    app = _app()
    client = _logged_in_client(app)

    resp = client.post(
        "/wines/new",
        data={"name": "Bad Vintage Wine", "vintage": "not-a-year", "quantity": "1"},
    )
    assert resp.status_code != 500, (
        "Expected graceful handling of a non-numeric vintage, got a 500 "
        "(unhandled ValueError from _optional_int)"
    )


@pytest.mark.xfail(reason="app/auth.py:reset_password - see ERROR_LOG.md Finding 2", strict=True)
def test_reset_link_for_a_deleted_account_should_not_crash_the_server():
    """app/auth.py:reset_password loads the user with db.session.get(User,
    user_id) and immediately calls user.set_password(...) with no None
    check. A still-valid (unexpired) token whose account no longer exists
    (e.g. deleted between requesting and using the reset link) raises
    AttributeError: 'NoneType' object has no attribute 'set_password'."""
    app = _app()
    with app.app_context():
        user = User(email=f"ghost-{uuid.uuid4()}@example.com", name="Ghost")
        db.session.add(user)
        db.session.commit()
        token = _make_reset_token(user.id)
        db.session.delete(user)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        f"/reset-password/{token}",
        data={"password": "newpassword1", "confirm_password": "newpassword1"},
    )
    assert resp.status_code != 500, (
        "Expected a friendly 'invalid/expired link' response for a reset "
        "token whose account was deleted, got a 500 (unhandled "
        "AttributeError on a None user)"
    )
