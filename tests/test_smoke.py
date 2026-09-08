import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402


def _client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app.test_client()


def test_welcome_page_loads():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert b"ZB Hub" in resp.data


def test_login_page_loads():
    resp = _client().get("/login")
    assert resp.status_code == 200
    assert b"Continue with" in resp.data or b"not configured" in resp.data


def test_wines_requires_login():
    resp = _client().get("/wines/", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Sign in" in resp.data
