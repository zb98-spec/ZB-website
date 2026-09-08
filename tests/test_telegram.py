import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:fake-token-for-tests"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-webhook-secret"

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import TastingNote, User, Wine  # noqa: E402

SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]


def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _make_user(app, **kwargs):
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", **kwargs)
        db.session.add(user)
        db.session.commit()
        return user.id


def _post_update(client, text, chat_id=111, secret=SECRET):
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": chat_id}, "text": text}},
        headers=headers,
    )


def test_webhook_rejects_missing_or_wrong_secret():
    app = _app()
    client = app.test_client()
    resp = _post_update(client, "/help", secret="wrong-secret")
    assert resp.status_code == 403

    resp = _post_update(client, "/help", secret=None)
    assert resp.status_code == 403


def test_help_command_replies_without_needing_a_link():
    app = _app()
    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        resp = _post_update(client, "/help", chat_id=222)
    assert resp.status_code == 200
    assert sent.called
    chat_id, text = sent.call_args[0]
    assert chat_id == 222
    assert "/window" in text


def test_unlinked_chat_is_told_to_link():
    app = _app()
    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/window", chat_id=333)
    _, text = sent.call_args[0]
    assert "/link" in text


def test_link_flow_connects_chat_to_account():
    app = _app()
    user_id = _make_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_link_code = "ABC123"
        user.telegram_link_code_expires = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/link ABC123", chat_id=444)
    _, text = sent.call_args[0]
    assert "Linked!" in text

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.telegram_chat_id == 444
        assert user.telegram_link_code is None


def test_link_rejects_expired_code():
    app = _app()
    user_id = _make_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_link_code = "STALE1"
        user.telegram_link_code_expires = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    client = app.test_client()
    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/link STALE1", chat_id=555)
    _, text = sent.call_args[0]
    assert "invalid or expired" in text


def _linked_client(app, chat_id):
    user_id = _make_user(app, username=f"wineuser-{uuid.uuid4().hex[:8]}")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.telegram_chat_id = chat_id
        db.session.commit()
    return app.test_client(), user_id


def test_add_command_creates_wine():
    app = _app()
    client, user_id = _linked_client(app, chat_id=666)

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/add TG Opus One | Telegram Winery | 2018 | red | 2", chat_id=666)
    _, text = sent.call_args[0]
    assert "Added #" in text
    assert "TG Opus One" in text

    with app.app_context():
        wine = Wine.query.filter_by(user_id=user_id, name="TG Opus One").one()
        assert wine.producer == "Telegram Winery"
        assert wine.vintage == 2018
        assert wine.wine_type == "red"
        assert wine.quantity == 2


def test_add_command_with_only_a_name():
    app = _app()
    client, user_id = _linked_client(app, chat_id=667)

    with patch("app.telegram_bot._send_message"):
        _post_update(client, "/add Mystery Bottle", chat_id=667)

    with app.app_context():
        wine = Wine.query.filter_by(user_id=user_id, name="Mystery Bottle").one()
        assert wine.quantity == 1
        assert wine.producer is None


def test_window_command_lists_only_wines_in_range():
    app = _app()
    client, user_id = _linked_client(app, chat_id=777)
    year = datetime.utcnow().year

    with app.app_context():
        db.session.add_all([
            Wine(user_id=user_id, name="In Window", quantity=1, drink_from=year - 1, drink_by=year + 1),
            Wine(user_id=user_id, name="Too Young", quantity=1, drink_from=year + 5, drink_by=year + 10),
            Wine(user_id=user_id, name="No Window Set", quantity=1),
        ])
        db.session.commit()

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/window", chat_id=777)
    _, text = sent.call_args[0]
    assert "In Window" in text
    assert "Too Young" not in text
    assert "No Window Set" not in text


def test_notes_and_log_commands():
    app = _app()
    client, user_id = _linked_client(app, chat_id=888)

    with app.app_context():
        wine = Wine(user_id=user_id, name="TG Sancerre", quantity=3, rating=90)
        db.session.add(wine)
        db.session.commit()
        wine_id = wine.id

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/notes TG Sancerre", chat_id=888)
    _, text = sent.call_args[0]
    assert "90/100" in text

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/log TG Sancerre | 88 | Great with oysters", chat_id=888)
    _, text = sent.call_args[0]
    assert "88/100" in text

    with app.app_context():
        wine = db.session.get(Wine, wine_id)
        assert wine.quantity == 2  # decremented
        tasting = TastingNote.query.filter_by(wine_id=wine_id).one()
        assert tasting.score == 88
        assert tasting.notes == "Great with oysters"


def test_ambiguous_query_lists_candidates_with_ids():
    app = _app()
    client, user_id = _linked_client(app, chat_id=999)

    with app.app_context():
        db.session.add_all([
            Wine(user_id=user_id, name="Cabernet A", quantity=1),
            Wine(user_id=user_id, name="Cabernet B", quantity=1),
        ])
        db.session.commit()

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client, "/notes Cabernet", chat_id=999)
    _, text = sent.call_args[0]
    assert "Multiple matches" in text
    assert "Cabernet A" in text and "Cabernet B" in text


def test_add_command_cannot_touch_another_users_cellar():
    app = _app()
    client_a, user_a = _linked_client(app, chat_id=1001)
    client_b, user_b = _linked_client(app, chat_id=1002)

    with patch("app.telegram_bot._send_message"):
        _post_update(client_a, "/add TG Private Bottle", chat_id=1001)

    with app.app_context():
        wine = Wine.query.filter_by(name="TG Private Bottle").one()
        assert wine.user_id == user_a
        assert wine.user_id != user_b

    with patch("app.telegram_bot._send_message") as sent:
        _post_update(client_b, "/notes TG Private Bottle", chat_id=1002)
    _, text = sent.call_args[0]
    assert "No wine found" in text
