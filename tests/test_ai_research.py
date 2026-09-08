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


def _wine_id(app, name):
    with app.app_context():
        return Wine.query.filter_by(name=name).one().id


FAKE_RESULT = {
    "rating": 92,
    "estimated_price": 45.5,
    "drink_from": 2024,
    "drink_by": 2030,
    "tasting_notes": "Notes of cherry and oak.",
}


def test_preview_redirects_when_not_configured():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Preview Wine", "quantity": "1"}, follow_redirects=True)
    wine_id = _wine_id(app, "Preview Wine")

    resp = client.post("/wines/research/preview", data={"wine_ids[]": [str(wine_id)]}, follow_redirects=True)
    assert b"isn&#39;t configured yet" in resp.data


def test_preview_requires_a_selection():
    app = _app()
    client = _logged_in_client(app)
    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        resp = client.post("/wines/research/preview", data={}, follow_redirects=True)
        assert b"Select at least one wine" in resp.data
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_preview_shows_old_vs_new_without_writing_to_db():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Preview Only Wine", "quantity": "1"}, follow_redirects=True)
    wine_id = _wine_id(app, "Preview Only Wine")

    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    try:
        with patch("app.wines.ask_gemini_json", return_value=FAKE_RESULT):
            resp = client.post(
                "/wines/research/preview", data={"wine_ids[]": [str(wine_id)]}, follow_redirects=True
            )
        assert b"Review AI research" in resp.data
        assert b"92" in resp.data  # proposed rating shown
        assert b"Notes of cherry and oak." in resp.data

        # nothing should be written to the DB yet - this is only a preview
        with app.app_context():
            wine = db.session.get(Wine, wine_id)
            assert wine.rating is None
            assert wine.researched_at is None
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


def test_apply_writes_only_checked_wines():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Accepted Wine", "quantity": "1"}, follow_redirects=True)
    client.post("/wines/new", data={"name": "Rejected Wine", "quantity": "1"}, follow_redirects=True)
    accepted_id = _wine_id(app, "Accepted Wine")
    rejected_id = _wine_id(app, "Rejected Wine")

    # Simulates submitting the review form with only "Accepted Wine" checked -
    # "Rejected Wine" simply isn't in accept_wine_ids[], same as an unchecked box.
    resp = client.post(
        "/wines/research/apply",
        data={
            "accept_wine_ids[]": [str(accepted_id)],
            f"rating_{accepted_id}": "92",
            f"price_{accepted_id}": "45.5",
            f"drink_from_{accepted_id}": "2024",
            f"drink_by_{accepted_id}": "2030",
            f"notes_{accepted_id}": "Notes of cherry and oak.",
        },
        follow_redirects=True,
    )
    assert b"Updated 1 wine" in resp.data

    with app.app_context():
        accepted = db.session.get(Wine, accepted_id)
        assert accepted.rating == 92
        assert float(accepted.estimated_price) == 45.5
        assert accepted.tasting_profile == "Notes of cherry and oak."
        assert accepted.researched_at is not None

        rejected = db.session.get(Wine, rejected_id)
        assert rejected.rating is None
        assert rejected.researched_at is None


def test_apply_with_nothing_checked_changes_nothing():
    app = _app()
    client = _logged_in_client(app)
    resp = client.post("/wines/research/apply", data={}, follow_redirects=True)
    assert b"No changes applied" in resp.data


def test_apply_ignores_out_of_range_values():
    app = _app()
    client = _logged_in_client(app)
    client.post("/wines/new", data={"name": "Bad Data Wine", "quantity": "1"}, follow_redirects=True)
    wine_id = _wine_id(app, "Bad Data Wine")

    client.post(
        "/wines/research/apply",
        data={
            "accept_wine_ids[]": [str(wine_id)],
            f"rating_{wine_id}": "500",  # out of 1-100 range
            f"price_{wine_id}": "-10",  # negative
            f"drink_from_{wine_id}": "2030",
            f"drink_by_{wine_id}": "2020",  # from > by
            f"notes_{wine_id}": "Fine.",
        },
        follow_redirects=True,
    )

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.rating is None
        assert wine.estimated_price is None
        assert wine.drink_from is None and wine.drink_by is None
        assert wine.tasting_profile == "Fine."  # the one valid field is still saved


def test_apply_cannot_touch_another_users_wine():
    app = _app()
    owner = _logged_in_client(app)
    owner.post("/wines/new", data={"name": "Someone Elses Wine", "quantity": "1"}, follow_redirects=True)
    wine_id = _wine_id(app, "Someone Elses Wine")

    attacker = _logged_in_client(app)
    attacker.post(
        "/wines/research/apply",
        data={"accept_wine_ids[]": [str(wine_id)], f"rating_{wine_id}": "99"},
        follow_redirects=True,
    )

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.rating is None  # untouched
