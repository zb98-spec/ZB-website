from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import Wine

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
