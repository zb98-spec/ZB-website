import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import GroceryItem, User  # noqa: E402


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
