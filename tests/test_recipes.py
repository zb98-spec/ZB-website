import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import GroceryItem, Recipe, User  # noqa: E402


def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _logged_in_client(app):
    client = app.test_client()
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", name="Pytest")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


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
