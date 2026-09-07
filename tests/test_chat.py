import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)
os.environ.pop("GEMINI_API_KEY", None)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


def _logged_in_client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
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


def test_chat_redirects_when_gemini_not_configured():
    client = _logged_in_client()
    resp = client.get("/wines/chat", follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_wine_library_hides_chat_link_when_not_configured():
    client = _logged_in_client()
    resp = client.get("/wines/")
    assert b"Ask the Wine Assistant" not in resp.data
