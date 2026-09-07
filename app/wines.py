from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .gemini import ask_gemini, gemini_enabled
from .models import TastingNote, Wine

wines_bp = Blueprint("wines", __name__, url_prefix="/wines")

WINE_TYPES = ["red", "white", "rosé", "sparkling", "dessert", "fortified"]


def _get_owned_wine(wine_id: int) -> Wine:
    wine = db.session.get(Wine, wine_id)
    if wine is None or wine.user_id != current_user.id:
        abort(404)
    return wine


def _optional_int(form, key: str):
    value = form.get(key, "").strip()
    return int(value) if value else None


def _optional_decimal(form, key: str):
    value = form.get(key, "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _wine_fields_from_form(form) -> dict:
    return {
        "name": form["name"].strip(),
        "producer": form.get("producer", "").strip() or None,
        "vintage": _optional_int(form, "vintage"),
        "wine_type": form.get("wine_type") or None,
        "varietal": form.get("varietal", "").strip() or None,
        "region": form.get("region", "").strip() or None,
        "country": form.get("country", "").strip() or None,
        "quantity": _optional_int(form, "quantity") or 1,
        "purchase_price": _optional_decimal(form, "purchase_price"),
        "rating": _optional_int(form, "rating"),
        "drink_from": _optional_int(form, "drink_from"),
        "drink_by": _optional_int(form, "drink_by"),
        "notes": form.get("notes", "").strip() or None,
    }


@wines_bp.route("/")
@login_required
def list_wines():
    wines = (
        Wine.query.filter_by(user_id=current_user.id)
        .order_by(Wine.producer, Wine.vintage)
        .all()
    )
    return render_template("wines/list.html", wines=wines, chat_enabled=gemini_enabled())


@wines_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_wine():
    if request.method == "POST":
        wine = Wine(user_id=current_user.id, **_wine_fields_from_form(request.form))
        db.session.add(wine)
        db.session.commit()
        flash("Wine added to your cellar.")
        return redirect(url_for("wines.list_wines"))
    return render_template("wines/form.html", wine=None, wine_types=WINE_TYPES)


@wines_bp.route("/<int:wine_id>/edit", methods=["GET", "POST"])
@login_required
def edit_wine(wine_id):
    wine = _get_owned_wine(wine_id)
    if request.method == "POST":
        for key, value in _wine_fields_from_form(request.form).items():
            setattr(wine, key, value)
        db.session.commit()
        flash("Wine updated.")
        return redirect(url_for("wines.list_wines"))
    return render_template("wines/form.html", wine=wine, wine_types=WINE_TYPES)


@wines_bp.route("/<int:wine_id>/delete", methods=["POST"])
@login_required
def delete_wine(wine_id):
    wine = _get_owned_wine(wine_id)
    db.session.delete(wine)
    db.session.commit()
    flash("Wine removed from your cellar.")
    return redirect(url_for("wines.list_wines"))


@wines_bp.route("/<int:wine_id>")
@login_required
def wine_detail(wine_id):
    wine = _get_owned_wine(wine_id)
    return render_template("wines/detail.html", wine=wine)


@wines_bp.route("/<int:wine_id>/tastings/new")
@login_required
def new_tasting(wine_id):
    wine = _get_owned_wine(wine_id)
    return render_template("wines/tasting_form.html", wine=wine, today=date.today().isoformat())


@wines_bp.route("/<int:wine_id>/tastings", methods=["POST"])
@login_required
def add_tasting(wine_id):
    wine = _get_owned_wine(wine_id)

    score = _optional_int(request.form, "score")
    if score is None:
        flash("Score is required to log a tasting.")
        return redirect(url_for("wines.new_tasting", wine_id=wine.id))

    tasted_on_raw = request.form.get("tasted_on", "").strip()
    try:
        tasted_on = datetime.strptime(tasted_on_raw, "%Y-%m-%d").date()
    except ValueError:
        tasted_on = date.today()

    db.session.add(
        TastingNote(
            wine_id=wine.id,
            tasted_on=tasted_on,
            score=score,
            occasion=request.form.get("occasion", "").strip() or None,
            people=request.form.get("people", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
    )
    if request.form.get("decrement_quantity") and wine.quantity > 0:
        wine.quantity -= 1
    db.session.commit()
    flash("Tasting logged.")
    return redirect(url_for("wines.wine_detail", wine_id=wine.id))


@wines_bp.route("/<int:wine_id>/tastings/<int:tasting_id>/delete", methods=["POST"])
@login_required
def delete_tasting(wine_id, tasting_id):
    wine = _get_owned_wine(wine_id)
    tasting = db.session.get(TastingNote, tasting_id)
    if tasting is None or tasting.wine_id != wine.id:
        abort(404)
    db.session.delete(tasting)
    db.session.commit()
    flash("Tasting note removed.")
    return redirect(url_for("wines.wine_detail", wine_id=wine.id))


def _cellar_summary(user_id: int) -> str:
    wines = Wine.query.filter_by(user_id=user_id).order_by(Wine.producer, Wine.vintage).all()
    if not wines:
        return "The cellar is currently empty."
    lines = []
    for wine in wines:
        parts = [wine.name]
        if wine.producer:
            parts.append(wine.producer)
        parts.append(str(wine.vintage) if wine.vintage else "NV")
        if wine.wine_type:
            parts.append(wine.wine_type)
        if wine.region:
            parts.append(wine.region)
        lines.append(f"- {', '.join(parts)} (qty: {wine.quantity})")
    return "\n".join(lines)


@wines_bp.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if not gemini_enabled():
        flash("The wine chat bot isn't configured yet.")
        return redirect(url_for("wines.list_wines"))

    answer = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if not question:
            flash("Type a question first.")
        else:
            prompt = (
                "You are a friendly, knowledgeable wine assistant helping "
                "someone with their home wine cellar. Keep answers concise "
                "and practical.\n\nHere is their current cellar:\n"
                f"{_cellar_summary(current_user.id)}\n\n"
                f"Their question: {question}"
            )
            try:
                answer = ask_gemini(prompt)
            except RuntimeError as exc:
                flash(str(exc))

    return render_template("wines/chat.html", question=question, answer=answer)
