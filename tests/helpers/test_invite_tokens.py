from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer

from app.extensions import db
from app.helpers.invite_tokens import generate_invite_token, load_invite_token
from app.models import Invite


def make_invite(dashboard):
    invite = Invite(dashboard_id=dashboard.id, email="friend@example.com")
    db.session.add(invite)
    db.session.commit()
    return invite


def test_token_roundtrip(app, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)

    assert load_invite_token(token) == {"invite_id": invite.id, "email": invite.email}


def test_token_rejects_bad_signature(app, dashboard):
    invite = make_invite(dashboard)
    token = URLSafeTimedSerializer("test-secret", salt="email-verify").dumps(
        {"invite_id": invite.id, "email": invite.email}
    )

    assert load_invite_token(token) is None
    assert load_invite_token("not-a-token") is None


def test_token_expired(app, dashboard):
    token = generate_invite_token(make_invite(dashboard))

    with patch("app.helpers.invite_tokens.MAX_AGE_SECONDS", -1):
        assert load_invite_token(token) == "expired"
