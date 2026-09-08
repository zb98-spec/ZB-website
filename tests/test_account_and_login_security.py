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
