from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import GroceryItem

grocery_bp = Blueprint("grocery", __name__, url_prefix="/grocery")


@grocery_bp.route("/")
@login_required
def list_items():
    items = GroceryItem.query.order_by(GroceryItem.created_at).all()
    return render_template("grocery/list.html", items=items)


@grocery_bp.route("/add", methods=["POST"])
@login_required
def add_item():
    name = request.form.get("name", "").strip()
    quantity = request.form.get("quantity", "").strip() or None
    if name:
        db.session.add(GroceryItem(name=name, quantity=quantity, added_by_id=current_user.id))
        db.session.commit()
    return redirect(url_for("grocery.list_items"))


@grocery_bp.route("/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    item = db.session.get(GroceryItem, item_id)
    if item is not None:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for("grocery.list_items"))


@grocery_bp.route("/clear", methods=["POST"])
@login_required
def clear_list():
    count = GroceryItem.query.delete()
    db.session.commit()
    if count:
        flash(f"Cleared {count} item(s) from the list.")
    return redirect(url_for("grocery.list_items"))
