import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User, Wine  # noqa: E402


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


def _wine_id(app, name):
    with app.app_context():
        return Wine.query.filter_by(name=name).one().id


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
