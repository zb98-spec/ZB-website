"""End-to-end tests: full user journeys that chain several features
together in one session, the way a real person actually moves through the
app - as opposed to test_integration.py, where each test checks one
route/feature in isolation.

The app has no client-side JS, so there is no separate browser layer to
drive; "end to end" here means through Flask's test client, but following
a whole story (sign up -> use several projects -> sign back in) rather
than a single action. Run these before deploying, as the final check that
the pieces still work together.
"""

import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _unique_username():
    return f"user-{uuid.uuid4().hex[:12]}"


def test_new_user_wine_cellar_and_account_lifecycle():
    """Sign up -> land on the empty hub -> add a wine -> log a tasting
    (quantity drops) -> edit the wine -> see the change reflected in the
    list -> change the account password -> sign out -> sign back in with
    the new password and confirm the cellar is still there."""
    app = _app()
    client = app.test_client()
    username = _unique_username()

    resp = client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Welcome back" in resp.data
    assert b"Wine Library" in resp.data

    resp = client.get("/wines/")
    assert b"Your cellar is empty" in resp.data

    resp = client.post(
        "/wines/new",
        data={"name": "Chateauneuf-du-Pape", "vintage": "2019", "quantity": "3"},
        follow_redirects=True,
    )
    assert b"Wine added to your cellar" in resp.data
    assert b"Chateauneuf-du-Pape" in resp.data

    with app.app_context():
        from app.models import Wine
        wine_id = Wine.query.filter_by(name="Chateauneuf-du-Pape").one().id

    resp = client.post(
        f"/wines/{wine_id}/tastings",
        data={"tasted_on": "2026-02-01", "score": "90", "decrement_quantity": "on"},
        follow_redirects=True,
    )
    assert b"Tasting logged" in resp.data

    resp = client.post(
        f"/wines/{wine_id}/edit",
        data={"name": "Chateauneuf-du-Pape Reserve", "vintage": "2019", "quantity": "2"},
        follow_redirects=True,
    )
    assert b"Wine updated" in resp.data

    resp = client.get("/wines/")
    assert b"Chateauneuf-du-Pape Reserve" in resp.data
    with app.app_context():
        from app.models import Wine
        wine = db.session.get(Wine, wine_id)
        assert wine.quantity == 2  # 3 at purchase, minus 1 from the tasting

    resp = client.post(
        "/account",
        data={
            "action": "change_password",
            "current_password": "correcthorse",
            "new_password": "newerpassword1",
            "confirm_new_password": "newerpassword1",
        },
        follow_redirects=True,
    )
    assert b"Password updated" in resp.data

    client.post("/logout", follow_redirects=True)
    resp = client.get("/wines/", follow_redirects=False)
    assert resp.status_code == 302  # signed out, cellar no longer reachable

    fresh_client = app.test_client()
    resp = fresh_client.post(
        "/login/password",
        data={"username": username, "password": "newerpassword1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    resp = fresh_client.get("/wines/")
    assert b"Chateauneuf-du-Pape Reserve" in resp.data  # still there


def test_recipe_to_shared_grocery_list_across_two_users():
    """One user builds a recipe and sends its ingredients to the shared
    grocery list; a second, unrelated user sees those items appear (with
    attribution), removes one, and clears the rest - the full lifecycle of
    the one list every signed-in user shares."""
    app = _app()
    alice = app.test_client()
    alice_username = _unique_username()
    alice.post(
        "/register",
        data={"username": alice_username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    resp = alice.post(
        "/recipes/new",
        data={
            "name": "Weeknight Tacos",
            "servings": "2",
            "ingredient_name[]": ["tortillas", "ground beef"],
            "ingredient_qty[]": ["8", "1"],
            "ingredient_unit[]": ["", "lb"],
            "step[]": ["Brown the beef.", "Warm the tortillas."],
        },
        follow_redirects=True,
    )
    assert b"Recipe saved" in resp.data

    with app.app_context():
        from app.models import Recipe
        recipe_id = Recipe.query.filter_by(name="Weeknight Tacos").one().id

    resp = alice.post(
        f"/recipes/{recipe_id}/add-to-grocery-list",
        data={"servings": "4"},  # double the recipe's 2 servings
        follow_redirects=True,
    )
    assert b"Added 2 ingredient(s)" in resp.data

    with app.app_context():
        bob_user = User(email=f"bob-{uuid.uuid4()}@example.com", name="Bob")
        db.session.add(bob_user)
        db.session.commit()
        bob_id = bob_user.id

    bob = app.test_client()
    with bob.session_transaction() as sess:
        sess["_user_id"] = str(bob_id)
        sess["_fresh"] = True

    resp = bob.get("/grocery/")
    assert b"tortillas" in resp.data
    assert b"ground beef" in resp.data
    assert alice_username.encode() in resp.data  # attributed to whoever added it

    with app.app_context():
        from app.models import GroceryItem
        beef_item_id = GroceryItem.query.filter_by(name="ground beef").one().id

    resp = bob.post(f"/grocery/{beef_item_id}/delete", follow_redirects=True)
    assert b"ground beef" not in resp.data
    assert b"tortillas" in resp.data  # untouched

    resp = bob.post("/grocery/clear", follow_redirects=True)
    assert b"tortillas" not in resp.data
    assert b"The list is empty" in resp.data

    # And the recipe itself, viewed by its owner, is unaffected by any of
    # what Bob did to the (separate) grocery list.
    resp = alice.get(f"/recipes/{recipe_id}")
    assert b"tortillas" in resp.data
