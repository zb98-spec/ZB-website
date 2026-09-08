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


def _register(app, client, username=None, password="correcthorse"):
    username = username or f"user-{uuid.uuid4().hex[:12]}"
    client.post(
        "/register",
        data={"username": username, "password": password, "confirm_password": password},
        follow_redirects=True,
    )
    return username


def _oauth_only_client(app, name="OAuth Only"):
    """A user created via Google/Apple: has an email, no username/password."""
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
    client = _oauth_only_client(app)
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
