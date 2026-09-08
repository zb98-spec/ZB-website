import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Recipe, User  # noqa: E402


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


def _create_recipe(client, name, servings="4"):
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


def test_edit_recipe_rejects_blank_name():
    app = _app()
    client = _logged_in_client(app)
    _create_recipe(client, "Editable Recipe")
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
    _create_recipe(client, "Old Name")
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
    _create_recipe(client, "Doomed Recipe")
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
    _create_recipe(owner, "Guarded Recipe")
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
