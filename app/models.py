from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(512))
    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    oauth_accounts = db.relationship(
        "OAuthAccount", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    wines = db.relationship(
        "Wine", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    recipes = db.relationship(
        "Recipe", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return self.password_hash is not None and check_password_hash(
            self.password_hash, password
        )


class OAuthAccount(db.Model):
    __tablename__ = "oauth_account"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    provider_user_id = db.Column(db.String(255), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "provider", "provider_user_id", name="uq_provider_account"
        ),
    )


class Wine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    producer = db.Column(db.String(255))
    vintage = db.Column(db.Integer)  # null = non-vintage (NV)
    wine_type = db.Column(db.String(50))  # red / white / rosé / sparkling / dessert / fortified
    varietal = db.Column(db.String(255))
    region = db.Column(db.String(255))
    country = db.Column(db.String(255))

    quantity = db.Column(db.Integer, nullable=False, default=1)
    purchase_price = db.Column(db.Numeric(8, 2))
    rating = db.Column(db.Integer)  # 1-100
    drink_from = db.Column(db.Integer)  # earliest recommended drinking year
    drink_by = db.Column(db.Integer)  # latest recommended drinking year
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tastings = db.relationship(
        "TastingNote",
        backref="wine",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(TastingNote.tasted_on)",
    )


class TastingNote(db.Model):
    __tablename__ = "tasting_note"

    id = db.Column(db.Integer, primary_key=True)
    wine_id = db.Column(db.Integer, db.ForeignKey("wine.id"), nullable=False)

    tasted_on = db.Column(db.Date, nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 1-100, this tasting only (may differ from Wine.rating)
    occasion = db.Column(db.String(255))
    people = db.Column(db.String(255))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    servings = db.Column(db.Integer, nullable=False, default=4)  # base servings the ingredients below are for
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ingredients = db.relationship(
        "Ingredient",
        backref="recipe",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Ingredient.id",
    )
    steps = db.relationship(
        "RecipeStep",
        backref="recipe",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="RecipeStep.step_number",
    )
    comments = db.relationship(
        "RecipeComment",
        backref="recipe",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(RecipeComment.created_at)",
    )


class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10, 3))  # null = no set quantity, e.g. "salt to taste"
    unit = db.Column(db.String(50))  # e.g. "cup", "g", "tbsp"


class RecipeStep(db.Model):
    __tablename__ = "recipe_step"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)

    step_number = db.Column(db.Integer, nullable=False)
    instruction = db.Column(db.Text, nullable=False)


class RecipeComment(db.Model):
    __tablename__ = "recipe_comment"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)

    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GroceryItem(db.Model):
    """A single shared list - every logged-in user of the app sees and can
    edit the same list, so household members can shop off one list."""

    __tablename__ = "grocery_item"

    id = db.Column(db.Integer, primary_key=True)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    source_recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id", ondelete="SET NULL"), nullable=True)

    name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.String(100))  # freeform, e.g. "2 cups" or "1 dozen"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    added_by = db.relationship("User", lazy=True)
