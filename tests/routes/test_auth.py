import smtplib
from unittest.mock import patch

from app.extensions import db
from app.helpers.email_verification import generate_email_token, load_email_token
from app.models import User
from tests.conftest import confirm_url_token, login, mail_outbox

PASSWORD = "ValidPass123!"
RESEND_CSRF = "test-resend-csrf-token"


def register_csrf(client):
    client.get("/register")
    with client.session_transaction() as sess:
        return sess["register_csrf_token"]


def login_with_resend_csrf(client, user):
    login(client, user)
    with client.session_transaction() as sess:
        sess["resend_verification_csrf_token"] = RESEND_CSRF


def test_register_sends_verification_email(client, app):
    csrf_token = register_csrf(client)

    response = client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "username": "newuser",
            "email": "new@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )

    created = db.session.scalar(
        db.select(User).where(User.email == "new@example.com")
    )
    outbox = mail_outbox(app)

    assert response.status_code == 302
    assert created is not None
    assert created.email_verified is False
    assert len(outbox) == 1
    assert outbox[0].to == ["new@example.com"]
    assert "Verify your PinIt email" in outbox[0].subject
    assert f"/verify-email/{confirm_url_token(outbox[0])}" in outbox[0].body


def test_register_keeps_account_if_send_fails(client, app):
    csrf_token = register_csrf(client)

    with patch(
        "app.routes.auth.send_verification_email",
        side_effect=smtplib.SMTPException("smtp down"),
    ):
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "username": "mailfail",
                "email": "mailfail@example.com",
                "password": PASSWORD,
                "confirm_password": PASSWORD,
            },
        )

    created = db.session.scalar(
        db.select(User).where(User.email == "mailfail@example.com")
    )

    assert response.status_code == 302
    assert created is not None
    assert created.email_verified is False
    assert mail_outbox(app) == []


def test_resend_requires_login(client, app):
    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert mail_outbox(app) == []


def test_resend_rejects_invalid_csrf(client, app, user):
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": "wrong-token"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert mail_outbox(app) == []
    assert db.session.get(User, user.id).email_verified is False


def test_resend_sends_verification_email(client, app, user):
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )
    outbox = mail_outbox(app)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert len(outbox) == 1
    assert outbox[0].to == [user.email]
    token = confirm_url_token(outbox[0])
    assert load_email_token(token)["user_id"] == user.id


def test_resend_skips_when_already_verified(client, app, user):
    user.email_verified = True
    db.session.commit()
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )

    assert response.status_code == 302
    assert mail_outbox(app) == []


def test_resend_handles_smtp_failure(client, app, user):
    login_with_resend_csrf(client, user)

    with patch(
        "app.routes.auth.send_verification_email",
        side_effect=smtplib.SMTPException("smtp down"),
    ):
        response = client.post(
            "/verify-email/resend",
            data={"csrf_token": RESEND_CSRF},
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is False
    assert mail_outbox(app) == []


def test_verify_email_confirms_valid_token(client, app, user):
    token = generate_email_token(user)

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is True
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(user.id)


def test_verify_email_rejects_invalid_token(client, app, user):
    response = client.get("/verify-email/not-a-valid-token")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_rejects_expired_token(client, app, user):
    token = generate_email_token(user)

    with patch("app.helpers.email_verification.MAX_AGE_SECONDS", -1):
        response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_rejects_token_after_email_change(client, app, user):
    token = generate_email_token(user)
    user.email = "changed@example.com"
    db.session.commit()

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_is_idempotent_when_already_verified(client, app, user):
    user.email_verified = True
    db.session.commit()
    token = generate_email_token(user)

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is True


def test_register_then_confirm_from_email(client, app):
    csrf_token = register_csrf(client)
    client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "username": "flowuser",
            "email": "flow@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    token = confirm_url_token(mail_outbox(app)[0])

    response = client.get(f"/verify-email/{token}")
    created = db.session.scalar(
        db.select(User).where(User.email == "flow@example.com")
    )

    assert response.status_code == 302
    assert created.email_verified is True
