import os
import time

from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt as jose_jwt
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import csrf, db
from .models import OAuthAccount, User

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()


def _generate_apple_client_secret() -> str:
    """Apple has no static client secret - it's a JWT we sign ourselves,
    good for up to 6 months, using the private key from the Sign in with
    Apple key created in the Apple Developer portal."""
    private_key = os.environ["APPLE_PRIVATE_KEY"].replace("\\n", "\n")
    now = int(time.time())
    header = {"alg": "ES256", "kid": os.environ["APPLE_KEY_ID"]}
    payload = {
        "iss": os.environ["APPLE_TEAM_ID"],
        "iat": now,
        "exp": now + 60 * 60 * 24 * 180,
        "aud": "https://appleid.apple.com",
        "sub": os.environ["APPLE_CLIENT_ID"],
    }
    token = jose_jwt.encode(header, payload, private_key)
    return token.decode("utf-8")


def configure_oauth(app, oauth_client: OAuth) -> None:
    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        oauth_client.register(
            name="google",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    if all(
        os.environ.get(key)
        for key in ("APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY")
    ):
        oauth_client.register(
            name="apple",
            client_id=os.environ["APPLE_CLIENT_ID"],
            client_secret=_generate_apple_client_secret(),
            server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
            client_kwargs={"scope": "name email", "response_mode": "form_post"},
        )


@auth_bp.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    return render_template(
        "login.html",
        google_enabled=oauth.create_client("google") is not None,
        apple_enabled=oauth.create_client("apple") is not None,
    )


@auth_bp.route("/login/<provider>")
def login_redirect(provider):
    client = oauth.create_client(provider)
    if client is None:
        flash(f"{provider.title()} sign-in isn't configured yet.")
        return redirect(url_for("auth.login_page"))

    redirect_uri = url_for("auth.callback", provider=provider, _external=True)
    kwargs = {"response_mode": "form_post"} if provider == "apple" else {}
    return client.authorize_redirect(redirect_uri, **kwargs)


@auth_bp.route("/login/<provider>/callback", methods=["GET", "POST"])
def callback(provider):
    client = oauth.create_client(provider)
    if client is None:
        abort(404)

    token = client.authorize_access_token()
    userinfo = token.get("userinfo")
    if userinfo is None:
        abort(400, "Provider did not return user info.")

    provider_user_id = userinfo["sub"]
    email = userinfo.get("email")
    name = userinfo.get("name") or (email.split("@")[0] if email else None)

    account = OAuthAccount.query.filter_by(
        provider=provider, provider_user_id=provider_user_id
    ).first()

    if account is not None:
        user = account.user
    else:
        user = User.query.filter_by(email=email).first() if email else None
        if user is None:
            user = User(email=email, name=name)
            db.session.add(user)
            db.session.flush()
        db.session.add(
            OAuthAccount(
                provider=provider, provider_user_id=provider_user_id, user_id=user.id
            )
        )

    db.session.commit()
    login_user(user)
    return redirect(url_for("main.index"))


csrf.exempt(callback)  # Apple posts the callback with no CSRF token of ours


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))
