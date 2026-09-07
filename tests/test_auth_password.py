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


def test_register_creates_account_and_logs_in():
    app = _app()
    client = app.test_client()
    username = _unique_username()

    resp = client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert username.encode() in resp.data  # shown in the nav once logged in

    with app.app_context():
        user = User.query.filter_by(username=username).one()
        assert user.check_password("correcthorse")
        assert not user.check_password("wrongpassword")


def test_register_rejects_mismatched_passwords_and_short_passwords():
    app = _app()
    client = app.test_client()
    username = _unique_username()

    resp = client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "different"},
        follow_redirects=True,
    )
    assert b"Passwords don&#39;t match" in resp.data or b"don't match" in resp.data
    with app.app_context():
        assert User.query.filter_by(username=username).first() is None

    resp = client.post(
        "/register",
        data={"username": username, "password": "short", "confirm_password": "short"},
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data
    with app.app_context():
        assert User.query.filter_by(username=username).first() is None


def test_register_rejects_duplicate_username():
    app = _app()
    username = _unique_username()

    client1 = app.test_client()
    client1.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    client2 = app.test_client()
    resp = client2.post(
        "/register",
        data={"username": username, "password": "anotherpassword", "confirm_password": "anotherpassword"},
        follow_redirects=True,
    )
    assert b"already taken" in resp.data


def test_login_with_username_and_password():
    app = _app()
    username = _unique_username()

    setup_client = app.test_client()
    setup_client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    login_client = app.test_client()
    resp = login_client.post(
        "/login/password",
        data={"username": username, "password": "correcthorse"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert username.encode() in resp.data

    resp = login_client.get("/wines/")
    assert resp.status_code == 200  # logged in, not redirected to /login


def test_login_with_wrong_password_fails():
    app = _app()
    username = _unique_username()

    setup_client = app.test_client()
    setup_client.post(
        "/register",
        data={"username": username, "password": "correcthorse", "confirm_password": "correcthorse"},
        follow_redirects=True,
    )

    login_client = app.test_client()
    resp = login_client.post(
        "/login/password",
        data={"username": username, "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert b"Incorrect username or password" in resp.data

    resp = login_client.get("/wines/", follow_redirects=False)
    assert resp.status_code == 302  # still logged out
