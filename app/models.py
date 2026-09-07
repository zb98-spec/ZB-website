from datetime import datetime

from flask_login import UserMixin

from .extensions import db


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    oauth_accounts = db.relationship(
        "OAuthAccount", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    wines = db.relationship(
        "Wine", backref="user", lazy=True, cascade="all, delete-orphan"
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
