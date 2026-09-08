"""Regression tests for defects discovered while building out test coverage.

These intentionally exercise inputs that currently crash the application
with an unhandled exception (HTTP 500) instead of failing gracefully. Per
the testing task, no application code is modified to fix them - they are
left here, failing, as a record. See ERROR_LOG.md for details.
"""

import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://zbhub:zbhub@localhost:5432/zbhub"
)

from app import create_app  # noqa: E402
from app.auth import _make_reset_token  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


def _app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _logged_in_client(app):
    client = app.test_client()
    with app.app_context():
        user = User(email=f"pytest-{uuid.uuid4()}@example.com", name="Pytest")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


def test_non_numeric_vintage_should_not_crash_the_server():
    """app/wines.py:_optional_int has no try/except around int(value), unlike
    its sibling _optional_decimal (which catches InvalidOperation). Any
    non-numeric value in vintage/quantity/rating/drink_from/drink_by raises
    an unhandled ValueError -> HTTP 500, instead of a friendly validation
    message like the rest of the form uses."""
    app = _app()
    client = _logged_in_client(app)

    resp = client.post(
        "/wines/new",
        data={"name": "Bad Vintage Wine", "vintage": "not-a-year", "quantity": "1"},
    )
    assert resp.status_code != 500, (
        "Expected graceful handling of a non-numeric vintage, got a 500 "
        "(unhandled ValueError from _optional_int)"
    )


def test_reset_link_for_a_deleted_account_should_not_crash_the_server():
    """app/auth.py:reset_password loads the user with db.session.get(User,
    user_id) and immediately calls user.set_password(...) with no None
    check. A still-valid (unexpired) token whose account no longer exists
    (e.g. deleted between requesting and using the reset link) raises
    AttributeError: 'NoneType' object has no attribute 'set_password'."""
    app = _app()
    with app.app_context():
        user = User(email=f"ghost-{uuid.uuid4()}@example.com", name="Ghost")
        db.session.add(user)
        db.session.commit()
        token = _make_reset_token(user.id)
        db.session.delete(user)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        f"/reset-password/{token}",
        data={"password": "newpassword1", "confirm_password": "newpassword1"},
    )
    assert resp.status_code != 500, (
        "Expected a friendly 'invalid/expired link' response for a reset "
        "token whose account was deleted, got a 500 (unhandled "
        "AttributeError on a None user)"
    )
