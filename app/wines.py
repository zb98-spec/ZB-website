from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
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
    return render_template("wines/list.html", wines=wines)


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
    return render_template("wines/detail.html", wine=wine, today=date.today().isoformat())


@wines_bp.route("/<int:wine_id>/tastings", methods=["POST"])
@login_required
def add_tasting(wine_id):
    wine = _get_owned_wine(wine_id)

    tasted_on_raw = request.form.get("tasted_on", "").strip()
    try:
        tasted_on = datetime.strptime(tasted_on_raw, "%Y-%m-%d").date()
    except ValueError:
        tasted_on = date.today()

    db.session.add(
        TastingNote(
            wine_id=wine.id,
            tasted_on=tasted_on,
            rating=_optional_int(request.form, "rating"),
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
