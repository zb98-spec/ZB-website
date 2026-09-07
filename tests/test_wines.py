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
            "rating": "92",
            "notes": "Bright citrus, great with oysters.",
            "decrement_quantity": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Tasting logged" in resp.data
    assert b"92" in resp.data
    assert b"Bright citrus" in resp.data
    assert b"No tastings logged yet" not in resp.data

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.quantity == 2  # dropped from 3


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
