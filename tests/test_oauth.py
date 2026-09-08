import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)
# These tests assert the "not configured" branches, so make sure none of
# these are set even if the shell environment happens to carry them.
for _var in (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "APPLE_CLIENT_ID",
    "APPLE_TEAM_ID",
    "APPLE_KEY_ID",
    "APPLE_PRIVATE_KEY",
):
    os.environ.pop(_var, None)

from app import create_app  # noqa: E402


def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def test_login_redirect_flashes_when_google_not_configured():
    client = _app().test_client()
    resp = client.get("/login/google", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Google sign-in isn&#39;t configured yet" in resp.data


def test_login_redirect_flashes_when_apple_not_configured():
    client = _app().test_client()
    resp = client.get("/login/apple", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Apple sign-in isn&#39;t configured yet" in resp.data


def test_oauth_callback_404s_for_unconfigured_provider():
    client = _app().test_client()
    resp = client.get("/login/google/callback")
    assert resp.status_code == 404


def test_oauth_callback_404s_for_unknown_provider():
    client = _app().test_client()
    resp = client.get("/login/not-a-real-provider/callback")
    assert resp.status_code == 404


def test_login_page_shows_disabled_buttons_when_unconfigured():
    client = _app().test_client()
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Google sign-in not configured" in resp.data
    assert b"Apple sign-in not configured" in resp.data
