import re

import pytest
from flask import g
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db, limiter
from app.models import Dashboard, User

CSRF_TOKEN = "test-dashboards-csrf-token"


@pytest.fixture()
def app():
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            },
            "MAIL_BACKEND": "locmem",
            "MAIL_DEFAULT_SENDER": "PinIt <noreply@example.com>",
        }
    )
    limiter.enabled = False
    with flask_app.app_context():
        # SQLite ignores ON DELETE rules unless foreign keys are enabled per connection.
        event.listen(
            db.engine,
            "connect",
            lambda dbapi_connection, _record: dbapi_connection.execute("PRAGMA foreign_keys=ON"),
        )
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()
    limiter.enabled = True


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    owner = User(
        username="elisa",
        email="elisa@example.com",
        password_hash=generate_password_hash("ValidPass123!"),
    )
    db.session.add(owner)
    db.session.commit()
    return owner


@pytest.fixture()
def other_user(app):
    owner = User(
        username="other",
        email="other@example.com",
        password_hash=generate_password_hash("ValidPass123!"),
    )
    db.session.add(owner)
    db.session.commit()
    return owner


@pytest.fixture()
def default_dashboard(user):
    dashboard = Dashboard(name="Home", owner_id=user.id, is_default=True)
    db.session.add(dashboard)
    db.session.commit()
    return dashboard


@pytest.fixture()
def dashboard(user):
    board = Dashboard(name="Work", owner_id=user.id, is_default=False)
    db.session.add(board)
    db.session.commit()
    return board


def login(client, user, csrf_token=CSRF_TOKEN):
    # The app fixture keeps one app context open, so Flask-Login's cached user
    # in `g` would otherwise survive into requests made as a different user.
    g.pop("_login_user", None)
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
        session["dashboards_csrf_token"] = csrf_token


def mail_outbox(app):
    return getattr(app.extensions["mailman"], "outbox", [])


def confirm_url_token(message):
    match = re.search(r"/verify-email/([^\s]+)", message.body)
    assert match is not None
    return match.group(1)


def invite_url_token(message):
    match = re.search(r"/invitations/([^\s]+)", message.body)
    assert match is not None
    return match.group(1)
