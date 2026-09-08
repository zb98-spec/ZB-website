import os

from flask import Flask

from .extensions import csrf, db, login_manager, migrate


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .auth import auth_bp, configure_oauth, oauth
    from .grocery import grocery_bp
    from .main import main_bp
    from .models import User
    from .recipes import format_qty, recipes_bp
    from .telegram_bot import telegram_bp
    from .wines import wines_bp

    oauth.init_app(app)
    configure_oauth(app, oauth)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(wines_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(grocery_bp)
    app.register_blueprint(telegram_bp)

    app.jinja_env.filters["format_qty"] = format_qty

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    return app
