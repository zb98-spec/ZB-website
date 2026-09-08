import os
import uuid
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)
os.environ.pop("GEMINI_API_KEY", None)

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


def test_research_all_redirects_when_not_configured():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Test Wine", "quantity": "1"}, follow_redirects=True)

    resp = client.post("/wines/research-all", follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_research_all_updates_wine_fields():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Researchable Wine", "quantity": "1"}, follow_redirects=True)

    fake_result = {
        "rating": 92,
        "estimated_price": 45.5,
        "drink_from": 2024,
        "drink_by": 2030,
        "tasting_notes": "Notes of cherry and oak.",
    }

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", return_value=fake_result) as mocked:
            resp = client.post("/wines/research-all", follow_redirects=True)
        assert mocked.called
        assert b"Researched 1 wine" in resp.data

        with app.app_context():
            wine = Wine.query.filter_by(name="Researchable Wine").one()
            assert wine.rating == 92
            assert float(wine.estimated_price) == 45.5
            assert wine.drink_from == 2024
            assert wine.drink_by == 2030
            assert wine.tasting_profile == "Notes of cherry and oak."
            assert wine.researched_at is not None
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_research_all_counts_failures_without_crashing():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Failing Wine", "quantity": "1"}, follow_redirects=True)

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", side_effect=RuntimeError("boom")):
            resp = client.post("/wines/research-all", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Researched 0 wines" in resp.data
        assert b"1 failed" in resp.data
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_research_all_ignores_out_of_range_rating():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Bad Data Wine", "quantity": "1"}, follow_redirects=True)

    fake_result = {
        "rating": 500,  # out of 1-100 range - should be rejected, not stored
        "estimated_price": -10,  # negative - should be rejected
        "drink_from": 2030,
        "drink_by": 2020,  # from > by - should be rejected as a pair
        "tasting_notes": "Fine.",
    }

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", return_value=fake_result):
            client.post("/wines/research-all", follow_redirects=True)
        with app.app_context():
            wine = Wine.query.filter_by(name="Bad Data Wine").one()
            assert wine.rating is None
            assert wine.estimated_price is None
            assert wine.drink_from is None and wine.drink_by is None
            assert wine.tasting_profile == "Fine."  # the one valid field is still saved
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
