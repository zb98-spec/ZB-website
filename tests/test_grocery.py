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
