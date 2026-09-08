import os
from datetime import date, datetime

import requests
from flask import Blueprint, abort, current_app, request

from .extensions import csrf, db
from .models import TastingNote, User, Wine

telegram_bp = Blueprint("telegram", __name__, url_prefix="/telegram")

API_BASE = "https://api.telegram.org"
TIMEOUT = 10

HELP_TEXT = (
    "ZB Hub wine cellar bot\n\n"
    "/link <code> - connect this chat to your ZB Hub account "
    "(get a code from your Account page)\n"
    "/unlink - disconnect this chat\n"
    "/window - bottles currently in their drinking window\n"
    "/add <name> | <producer> | <vintage> | <type> | <qty> - add a "
    "bottle (only name is required, e.g. \"/add Opus One\")\n"
    "/notes <name or #id> - tasting notes and rating for a bottle\n"
    "/log <name or #id> | <score 1-100> | <notes> - log a tasting"
)


def telegram_enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_WEBHOOK_SECRET"))


def _send_message(chat_id, text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    try:
        requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        current_app.logger.exception("Failed to send Telegram message")


@telegram_bp.route("/webhook", methods=["POST"])
def webhook():
    if not telegram_enabled():
        abort(404)

    expected_secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != expected_secret:
        abort(403)

    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if chat_id is not None and text:
        try:
            reply = _dispatch(chat_id, text)
        except Exception:
            current_app.logger.exception("Telegram command failed: %r", text)
            reply = "Something went wrong handling that. Please try again."
        if reply:
            _send_message(chat_id, reply)

    return "", 200


csrf.exempt(webhook)  # external POST from Telegram, carries no CSRF token


def _dispatch(chat_id, text: str) -> str:
    command, _, rest = text.partition(" ")
    command = command.split("@")[0].lower()  # strip "@BotName" suffix Telegram adds in group chats
    rest = rest.strip()

    if command in ("/start", "/help"):
        return HELP_TEXT
    if command == "/link":
        return _cmd_link(chat_id, rest)
    if command == "/unlink":
        return _cmd_unlink(chat_id)

    user = User.query.filter_by(telegram_chat_id=chat_id).first()
    if user is None:
        return "This chat isn't linked yet. Send /link <code> - get a code from your ZB Hub Account page."

    if command == "/window":
        return _cmd_window(user)
    if command == "/add":
        return _cmd_add(user, rest)
    if command == "/notes":
        return _cmd_notes(user, rest)
    if command == "/log":
        return _cmd_log(user, rest)

    return "Unknown command. Send /help for the list of commands."


def _cmd_link(chat_id, code: str) -> str:
    code = code.strip().upper()
    if not code:
        return "Usage: /link <code> - get a code from your ZB Hub Account page."

    user = User.query.filter_by(telegram_link_code=code).first()
    if (
        user is None
        or user.telegram_link_code_expires is None
        or user.telegram_link_code_expires < datetime.utcnow()
    ):
        return "That code is invalid or expired. Generate a new one from your Account page."

    # in case this chat was previously linked to a different account
    previous = User.query.filter_by(telegram_chat_id=chat_id).first()
    if previous is not None and previous.id != user.id:
        previous.telegram_chat_id = None

    user.telegram_chat_id = chat_id
    user.telegram_link_code = None
    user.telegram_link_code_expires = None
    db.session.commit()
    return f"Linked! This chat is now connected to {user.username or user.name or 'your ZB Hub account'}."


def _cmd_unlink(chat_id) -> str:
    user = User.query.filter_by(telegram_chat_id=chat_id).first()
    if user is None:
        return "This chat isn't linked to anything."
    user.telegram_chat_id = None
    db.session.commit()
    return "Unlinked."


def _cmd_window(user: User) -> str:
    year = date.today().year
    wines = (
        Wine.query.filter(
            Wine.user_id == user.id,
            Wine.drink_from.isnot(None),
            Wine.drink_by.isnot(None),
            Wine.drink_from <= year,
            Wine.drink_by >= year,
        )
        .order_by(Wine.drink_by)
        .all()
    )
    if not wines:
        return f"Nothing in its drinking window right now ({year})."

    lines = [f"In their drinking window ({year}):"]
    for wine in wines:
        lines.append(
            f"#{wine.id} {wine.name} ({wine.vintage or 'NV'}) - qty {wine.quantity}, "
            f"window {wine.drink_from}–{wine.drink_by}"
        )
    return "\n".join(lines)


def _cmd_add(user: User, rest: str) -> str:
    if not rest:
        return "Usage: /add Name | Producer | Vintage | Type | Quantity (only Name is required)"

    fields = [f.strip() for f in rest.split("|")]
    name = fields[0]
    if not name:
        return "A wine name is required: /add Name | Producer | Vintage | Type | Quantity"

    producer = fields[1] if len(fields) > 1 and fields[1] else None

    vintage = None
    if len(fields) > 2 and fields[2]:
        try:
            vintage = int(fields[2])
        except ValueError:
            return f"Vintage must be a year, got '{fields[2]}'."

    wine_type = fields[3].lower() if len(fields) > 3 and fields[3] else None

    quantity = 1
    if len(fields) > 4 and fields[4]:
        try:
            quantity = int(fields[4])
        except ValueError:
            return f"Quantity must be a number, got '{fields[4]}'."

    wine = Wine(
        user_id=user.id, name=name, producer=producer, vintage=vintage,
        wine_type=wine_type, quantity=quantity,
    )
    db.session.add(wine)
    db.session.commit()
    return f"Added #{wine.id}: {wine.name}{f' ({vintage})' if vintage else ''}, qty {quantity}."


def _find_wine(user: User, query: str):
    """Returns (wine, matches) - exactly one of which is non-empty/non-None:
    a single matched Wine, or a list of ambiguous candidates to disambiguate."""
    query = query.strip().lstrip("#")
    if not query:
        return None, []

    if query.isdigit():
        wine = db.session.get(Wine, int(query))
        return (wine, []) if wine and wine.user_id == user.id else (None, [])

    matches = Wine.query.filter(
        Wine.user_id == user.id,
        db.or_(Wine.name.ilike(f"%{query}%"), Wine.producer.ilike(f"%{query}%")),
    ).all()
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _ambiguous_reply(query: str, matches: list) -> str:
    if not matches:
        return f"No wine found matching '{query}'."
    lines = [f"Multiple matches for '{query}' - try again with the #id:"]
    lines += [f"#{w.id} {w.name} ({w.vintage or 'NV'})" for w in matches[:10]]
    return "\n".join(lines)


def _cmd_notes(user: User, rest: str) -> str:
    if not rest:
        return "Usage: /notes <name or #id>"

    wine, matches = _find_wine(user, rest)
    if wine is None:
        return _ambiguous_reply(rest, matches)

    lines = [f"{wine.name} ({wine.vintage or 'NV'})"]
    if wine.rating:
        lines.append(f"Rating: {wine.rating}/100")
    if wine.tasting_profile:
        lines.append(f"AI notes: {wine.tasting_profile}")
    if wine.notes:
        lines.append(f"Your notes: {wine.notes}")
    if wine.tastings:
        lines.append("Past tastings:")
        for tasting in wine.tastings[:5]:
            entry = f"- {tasting.tasted_on}: {tasting.score}/100"
            if tasting.notes:
                entry += f" - {tasting.notes}"
            lines.append(entry)
    if len(lines) == 1:
        lines.append("No rating or notes recorded yet.")
    return "\n".join(lines)


def _cmd_log(user: User, rest: str) -> str:
    if not rest:
        return "Usage: /log <name or #id> | <score 1-100> | <notes optional>"

    fields = [f.strip() for f in rest.split("|")]
    if len(fields) < 2:
        return "Usage: /log <name or #id> | <score 1-100> | <notes optional>"

    query, score_raw = fields[0], fields[1]
    notes = fields[2] if len(fields) > 2 and fields[2] else None

    wine, matches = _find_wine(user, query)
    if wine is None:
        return _ambiguous_reply(query, matches)

    try:
        score = int(score_raw)
    except ValueError:
        return f"Score must be a number 1-100, got '{score_raw}'."
    if not (1 <= score <= 100):
        return "Score must be between 1 and 100."

    db.session.add(TastingNote(wine_id=wine.id, tasted_on=date.today(), score=score, notes=notes))
    if wine.quantity > 0:
        wine.quantity -= 1
    db.session.commit()
    return f"Logged: {wine.name} - {score}/100. Cellar quantity now {wine.quantity}."
