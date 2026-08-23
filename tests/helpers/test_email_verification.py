from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer

from app.helpers.email_verification import generate_email_token, load_email_token


def test_token_roundtrip(app, user):
    token = generate_email_token(user)

    assert load_email_token(token) == {"user_id": user.id, "email": user.email}


def test_token_rejects_bad_signature(app, user):
    token = URLSafeTimedSerializer("test-secret", salt="other-purpose").dumps(
        {"user_id": user.id, "email": user.email}
    )

    assert load_email_token(token) is None
    assert load_email_token("not-a-token") is None


def test_token_expired(app, user):
    token = generate_email_token(user)

    with patch("app.helpers.email_verification.MAX_AGE_SECONDS", -1):
        assert load_email_token(token) == "expired"
