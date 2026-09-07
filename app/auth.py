import json
import os
import re
import time
from datetime import datetime, timedelta

from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt as jose_jwt
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .extensions import csrf, db
from .mail import mail_enabled, send_email
from .models import OAuthAccount, User

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
RESET_TOKEN_MAX_AGE = 1800  # 30 minutes


def _make_reset_token(user_id: int) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")
    return serializer.dumps({"user_id": user_id})


def _verify_reset_token(token: str):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")
    try:
        data = serializer.loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


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
        mail_enabled=mail_enabled(),
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not USERNAME_RE.match(username):
            flash("Username must be 3-80 characters: letters, numbers, _ . -")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.")
        elif password != confirm_password:
            flash("Passwords don't match.")
        elif User.query.filter_by(username=username).first() is not None:
            flash("That username is already taken.")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("main.index"))

        return render_template("register.html", username=username)

    return render_template("register.html", username="")


@auth_bp.route("/login/password", methods=["POST"])
def login_password():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = User.query.filter_by(username=username).first()

    if user is not None and user.locked_until and user.locked_until > datetime.utcnow():
        flash("Too many failed attempts. Try again in a few minutes.")
        return redirect(url_for("auth.login_page"))

    if user is None or not user.check_password(password):
        if user is not None:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.utcnow() + LOCKOUT_DURATION
            db.session.commit()
        flash("Incorrect username or password.")
        return redirect(url_for("auth.login_page"))

    user.failed_login_count = 0
    user.locked_until = None
    db.session.commit()
    login_user(user)
    return redirect(url_for("main.index"))


@auth_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_email":
            email = request.form.get("email", "").strip() or None
            if email and User.query.filter(User.email == email, User.id != current_user.id).first():
                flash("That email is already in use by another account.")
            else:
                current_user.email = email
                db.session.commit()
                flash("Email updated.")

        elif action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_new_password = request.form.get("confirm_new_password", "")
            # Needed if this account was created via Google/Apple and has no
            # username yet - can't sign in with a password without one.
            new_username = request.form.get("username", "").strip()

            if current_user.password_hash and not current_user.check_password(current_password):
                flash("Current password is incorrect.")
            elif not current_user.username and not USERNAME_RE.match(new_username):
                flash("Username must be 3-80 characters: letters, numbers, _ . -")
            elif (
                not current_user.username
                and User.query.filter_by(username=new_username).first() is not None
            ):
                flash("That username is already taken.")
            elif len(new_password) < 8:
                flash("New password must be at least 8 characters.")
            elif new_password != confirm_new_password:
                flash("New passwords don't match.")
            else:
                if not current_user.username:
                    current_user.username = new_username
                current_user.set_password(new_password)
                db.session.commit()
                flash("Password updated.")

        return redirect(url_for("auth.account"))

    return render_template("account.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if not mail_enabled():
        flash("Password reset by email isn't configured yet.")
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user = User.query.filter_by(email=email).first() if email else None
        if user is not None:
            token = _make_reset_token(user.id)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            try:
                send_email(
                    user.email,
                    "Reset your ZB Hub password",
                    "Click the link below to reset your password. This link "
                    f"expires in 30 minutes.\n\n{reset_url}",
                )
            except Exception:
                current_app.logger.exception("Failed to send password reset email")
        # Same message either way, so this can't be used to test which
        # emails have an account.
        flash("If that email is on file, a reset link has been sent.")
        return redirect(url_for("auth.login_page"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    user_id = _verify_reset_token(token)
    if user_id is None:
        flash("That reset link is invalid or has expired.")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.")
        elif password != confirm_password:
            flash("Passwords don't match.")
        else:
            user = db.session.get(User, user_id)
            user.set_password(password)
            user.failed_login_count = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            flash("Password updated.")
            return redirect(url_for("main.index"))

    return render_template("reset_password.html", token=token)


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

    try:
        token = client.authorize_access_token()
    except OAuthError:
        flash(f"{provider.title()} sign-in was cancelled or failed. Please try again.")
        return redirect(url_for("auth.login_page"))

    userinfo = token.get("userinfo")
    if userinfo is None:
        flash(f"{provider.title()} didn't return account info. Please try again.")
        return redirect(url_for("auth.login_page"))

    provider_user_id = userinfo["sub"]
    email = userinfo.get("email")
    name = userinfo.get("name")

    # Apple never puts a name in the id token - it's only sent, once, as a
    # separate form field on the very first authorization.
    if provider == "apple" and not name and request.form.get("user"):
        try:
            apple_name = json.loads(request.form["user"]).get("name", {})
        except (TypeError, ValueError):
            apple_name = {}
        name = " ".join(
            filter(None, [apple_name.get("firstName"), apple_name.get("lastName")])
        ) or None

    name = name or (email.split("@")[0] if email else None)

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
