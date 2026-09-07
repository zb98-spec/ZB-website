from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import GroceryItem, Ingredient, Recipe, RecipeComment, RecipeStep

recipes_bp = Blueprint("recipes", __name__, url_prefix="/recipes")

# No JS on this site, so "add another ingredient/step" is done by rendering
# a generous number of blank rows up front rather than adding them dynamically.
BLANK_INGREDIENT_ROWS = 6
BLANK_STEP_ROWS = 4


def _get_owned_recipe(recipe_id: int) -> Recipe:
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None or recipe.user_id != current_user.id:
        abort(404)
    return recipe


def _parse_servings(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_quantity(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def format_qty(value) -> str:
    if value is None:
        return ""
    if value == value.to_integral_value():
        return str(value.to_integral_value())
    text = format(value, "f")
    return text.rstrip("0").rstrip(".")


def _save_ingredients_and_steps(recipe: Recipe, form) -> None:
    recipe.ingredients.clear()
    names = form.getlist("ingredient_name[]")
    quantities = form.getlist("ingredient_qty[]")
    units = form.getlist("ingredient_unit[]")
    for name, qty, unit in zip(names, quantities, units):
        name = name.strip()
        if not name:
            continue
        recipe.ingredients.append(
            Ingredient(name=name, quantity=_parse_quantity(qty), unit=unit.strip() or None)
        )

    recipe.steps.clear()
    step_number = 1
    for text in form.getlist("step[]"):
        text = text.strip()
        if not text:
            continue
        recipe.steps.append(RecipeStep(step_number=step_number, instruction=text))
        step_number += 1


@recipes_bp.route("/")
@login_required
def list_recipes():
    recipes = (
        Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.name).all()
    )
    return render_template("recipes/list.html", recipes=recipes)


@recipes_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_recipe():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        servings = _parse_servings(request.form.get("servings")) or 4
        if not name:
            flash("Recipe name is required.")
            return render_template(
                "recipes/form.html", recipe=None,
                ingredient_rows=range(BLANK_INGREDIENT_ROWS), step_rows=range(BLANK_STEP_ROWS),
            )

        recipe = Recipe(user_id=current_user.id, name=name, servings=servings)
        _save_ingredients_and_steps(recipe, request.form)
        db.session.add(recipe)
        db.session.commit()
        flash("Recipe saved.")
        return redirect(url_for("recipes.recipe_detail", recipe_id=recipe.id))

    return render_template(
        "recipes/form.html", recipe=None,
        ingredient_rows=range(BLANK_INGREDIENT_ROWS), step_rows=range(BLANK_STEP_ROWS),
    )


@recipes_bp.route("/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
def edit_recipe(recipe_id):
    recipe = _get_owned_recipe(recipe_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Recipe name is required.")
        else:
            recipe.name = name
            recipe.servings = _parse_servings(request.form.get("servings")) or recipe.servings
            _save_ingredients_and_steps(recipe, request.form)
            db.session.commit()
            flash("Recipe updated.")
            return redirect(url_for("recipes.recipe_detail", recipe_id=recipe.id))

    ingredient_rows = range(max(len(recipe.ingredients) + 3, BLANK_INGREDIENT_ROWS))
    step_rows = range(max(len(recipe.steps) + 3, BLANK_STEP_ROWS))
    return render_template(
        "recipes/form.html", recipe=recipe,
        ingredient_rows=ingredient_rows, step_rows=step_rows,
    )


@recipes_bp.route("/<int:recipe_id>/delete", methods=["POST"])
@login_required
def delete_recipe(recipe_id):
    recipe = _get_owned_recipe(recipe_id)
    db.session.delete(recipe)
    db.session.commit()
    flash("Recipe deleted.")
    return redirect(url_for("recipes.list_recipes"))


@recipes_bp.route("/<int:recipe_id>")
@login_required
def recipe_detail(recipe_id):
    recipe = _get_owned_recipe(recipe_id)
    requested_servings = _parse_servings(request.args.get("servings")) or recipe.servings

    scaled_ingredients = []
    for ingredient in recipe.ingredients:
        if ingredient.quantity is not None:
            scaled = ingredient.quantity * Decimal(requested_servings) / Decimal(recipe.servings)
            qty_display = format_qty(scaled)
        else:
            qty_display = ""
        scaled_ingredients.append((ingredient, qty_display))

    return render_template(
        "recipes/detail.html",
        recipe=recipe,
        scaled_ingredients=scaled_ingredients,
        requested_servings=requested_servings,
    )


@recipes_bp.route("/<int:recipe_id>/comments", methods=["POST"])
@login_required
def add_comment(recipe_id):
    recipe = _get_owned_recipe(recipe_id)
    body = request.form.get("body", "").strip()
    if body:
        db.session.add(RecipeComment(recipe_id=recipe.id, body=body))
        db.session.commit()
        flash("Comment added.")
    servings = request.form.get("servings")
    return redirect(url_for("recipes.recipe_detail", recipe_id=recipe.id, servings=servings))


@recipes_bp.route("/<int:recipe_id>/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(recipe_id, comment_id):
    recipe = _get_owned_recipe(recipe_id)
    comment = db.session.get(RecipeComment, comment_id)
    if comment is None or comment.recipe_id != recipe.id:
        abort(404)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for("recipes.recipe_detail", recipe_id=recipe.id))


@recipes_bp.route("/<int:recipe_id>/add-to-grocery-list", methods=["POST"])
@login_required
def add_to_grocery_list(recipe_id):
    recipe = _get_owned_recipe(recipe_id)
    requested_servings = _parse_servings(request.form.get("servings")) or recipe.servings

    added = 0
    for ingredient in recipe.ingredients:
        quantity_display = None
        if ingredient.quantity is not None:
            scaled = ingredient.quantity * Decimal(requested_servings) / Decimal(recipe.servings)
            quantity_display = format_qty(scaled)
            if ingredient.unit:
                quantity_display = f"{quantity_display} {ingredient.unit}"
        db.session.add(
            GroceryItem(
                name=ingredient.name,
                quantity=quantity_display,
                added_by_id=current_user.id,
                source_recipe_id=recipe.id,
            )
        )
        added += 1
    db.session.commit()
    flash(f"Added {added} ingredient(s) to the grocery list.")
    return redirect(url_for("recipes.recipe_detail", recipe_id=recipe.id, servings=requested_servings))
