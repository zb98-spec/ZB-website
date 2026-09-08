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


def _logged_in_client(app):
    client = app.test_client()
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", name="Pytest Nav")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


def test_index_page_logged_out_shows_hero():
    resp = _app().test_client().get("/")
    assert resp.status_code == 200
    assert b"Get started" in resp.data
    assert b"Welcome back" not in resp.data


def test_index_page_logged_in_shows_projects():
    app = _app()
    client = _logged_in_client(app)
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
