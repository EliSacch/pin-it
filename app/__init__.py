import os
from datetime import timedelta
from flask import Flask, flash, redirect, request, url_for, render_template, request
from flask_limiter.errors import RateLimitExceeded

from app.extensions import db, mail, migrate, login_manager, limiter


def create_app(config_overrides=None):
    app = Flask(
        __name__,
        template_folder="./templates",
        static_folder="../static",
        
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=7)

    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")
    app.config["MAIL_BACKEND"] = os.environ.get("MAIL_BACKEND")

    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    mail.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from app import models  # noqa: F401
    from app.helpers.alerts import alert_icon
    from app.routes import (
        auth_bp,
        dashboards_bp,
        invitations_bp,
        invites_bp,
        main_bp,
        notes_bp,
        profile_bp,
    )

    app.jinja_env.globals["alert_icon"] = alert_icon

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(invites_bp)
    app.register_blueprint(invitations_bp)
    
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(error):
        flash("Too many attempts. Please wait a moment and try again.", "warning")
        return redirect(request.referrer or url_for("auth.login"))
    
    @app.errorhandler(404)
    def handle_page_not_found(error):
        return render_template('404.html'), 404

    return app
