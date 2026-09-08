from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .gemini import ask_gemini, ask_gemini_json, gemini_enabled
from .models import TastingNote, Wine

wines_bp = Blueprint("wines", __name__, url_prefix="/wines")

WINE_TYPES = ["red", "white", "rosé", "sparkling", "dessert", "fortified"]

# No background job queue here, so a bulk research run has to fit inside one
# HTTP request/gunicorn worker timeout - cap how many wines it does per click.
RESEARCH_BATCH_LIMIT = 15

RESEARCH_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "rating": {"type": "INTEGER", "description": "Critic-style quality score, 1-100"},
        "estimated_price": {"type": "NUMBER", "description": "Current typical retail price in USD"},
        "drink_from": {"type": "INTEGER", "description": "Earliest recommended drinking year"},
        "drink_by": {"type": "INTEGER", "description": "Latest recommended drinking year"},
        "tasting_notes": {"type": "STRING", "description": "2-3 sentences: aroma, palate, food pairings"},
    },
    "required": ["rating", "estimated_price", "drink_from", "drink_by", "tasting_notes"],
}


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
    return render_template("wines/list.html", wines=wines, ai_enabled=gemini_enabled())


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


def _research_prompt(wine: Wine) -> str:
    details = [wine.name]
    details.append(f"producer: {wine.producer}" if wine.producer else "producer: unknown")
    details.append(f"vintage: {wine.vintage}" if wine.vintage else "non-vintage")
    if wine.wine_type:
        details.append(f"type: {wine.wine_type}")
    if wine.varietal:
        details.append(f"varietal: {wine.varietal}")
    if wine.region:
        details.append(f"region: {wine.region}")
    if wine.country:
        details.append(f"country: {wine.country}")

    return (
        "You are a wine expert helping research a bottle for a home cellar "
        "tracker. Give your best-informed estimate for every field below, "
        "even if you don't have exact data on this specific wine - never "
        "leave a field blank, use your general knowledge of the producer/"
        "region/varietal/vintage to make a reasonable estimate instead.\n\n"
        f"Wine: {', '.join(details)}"
    )


def _validate_research_data(data: dict) -> dict:
    """Cleans a raw {rating, estimated_price, drink_from, drink_by,
    tasting_notes} dict - from Gemini's JSON, or from the review page's
    hidden form fields (so the same validation runs whether the values just
    came out of the model or are being re-submitted for real). Any field
    that's missing or out of range comes back as None rather than raising,
    so one bad field doesn't sink the rest."""
    cleaned = {"rating": None, "estimated_price": None, "drink_from": None, "drink_by": None, "tasting_notes": None}

    try:
        rating = int(data.get("rating"))
        if 1 <= rating <= 100:
            cleaned["rating"] = rating
    except (TypeError, ValueError):
        pass

    try:
        price = float(data.get("estimated_price"))
        if price >= 0:
            cleaned["estimated_price"] = Decimal(str(round(price, 2)))
    except (TypeError, ValueError):
        pass

    try:
        drink_from = int(data.get("drink_from"))
        drink_by = int(data.get("drink_by"))
        if drink_from <= drink_by:
            cleaned["drink_from"] = drink_from
            cleaned["drink_by"] = drink_by
    except (TypeError, ValueError):
        pass

    notes = data.get("tasting_notes")
    if isinstance(notes, str) and notes.strip():
        cleaned["tasting_notes"] = notes.strip()

    return cleaned


def _apply_validated_research(wine: Wine, cleaned: dict) -> None:
    if cleaned["rating"] is not None:
        wine.rating = cleaned["rating"]
    if cleaned["estimated_price"] is not None:
        wine.estimated_price = cleaned["estimated_price"]
    if cleaned["drink_from"] is not None:
        wine.drink_from = cleaned["drink_from"]
        wine.drink_by = cleaned["drink_by"]
    if cleaned["tasting_notes"] is not None:
        wine.tasting_profile = cleaned["tasting_notes"]
    wine.researched_at = datetime.utcnow()


@wines_bp.route("/research/preview", methods=["POST"])
@login_required
def research_preview():
    if not gemini_enabled():
        flash("AI research isn't configured yet.")
        return redirect(url_for("wines.list_wines"))

    wine_ids = request.form.getlist("wine_ids[]")
    if not wine_ids:
        flash("Select at least one wine to research.")
        return redirect(url_for("wines.list_wines"))

    candidates = (
        Wine.query.filter(Wine.id.in_(wine_ids), Wine.user_id == current_user.id)
        .order_by(Wine.id)
        .all()
    )
    if not candidates:
        flash("Select at least one wine to research.")
        return redirect(url_for("wines.list_wines"))

    more_remaining = len(candidates) > RESEARCH_BATCH_LIMIT
    batch = candidates[:RESEARCH_BATCH_LIMIT]

    proposals = []
    failed = 0
    for wine in batch:
        try:
            data = ask_gemini_json(_research_prompt(wine), RESEARCH_SCHEMA)
        except RuntimeError:
            failed += 1
            continue
        cleaned = _validate_research_data(data)
        if not any(cleaned.values()):
            failed += 1
            continue
        proposals.append({"wine": wine, "new": cleaned})

    if not proposals:
        flash(f"Couldn't get usable research for any of the selected wines ({failed} failed).")
        return redirect(url_for("wines.list_wines"))

    return render_template(
        "wines/research_review.html", proposals=proposals, failed=failed, more_remaining=more_remaining,
    )


@wines_bp.route("/research/apply", methods=["POST"])
@login_required
def research_apply():
    accepted_ids = request.form.getlist("accept_wine_ids[]")
    if not accepted_ids:
        flash("No changes applied - nothing was checked.")
        return redirect(url_for("wines.list_wines"))

    updated = 0
    for wine_id in accepted_ids:
        wine = db.session.get(Wine, int(wine_id))
        if wine is None or wine.user_id != current_user.id:
            continue
        cleaned = _validate_research_data(
            {
                "rating": request.form.get(f"rating_{wine_id}"),
                "estimated_price": request.form.get(f"price_{wine_id}"),
                "drink_from": request.form.get(f"drink_from_{wine_id}"),
                "drink_by": request.form.get(f"drink_by_{wine_id}"),
                "tasting_notes": request.form.get(f"notes_{wine_id}"),
            }
        )
        _apply_validated_research(wine, cleaned)
        updated += 1

    db.session.commit()
    flash(f"Updated {updated} wine{'s' if updated != 1 else ''}." if updated else "No changes applied.")
    return redirect(url_for("wines.list_wines"))


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
