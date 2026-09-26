import re

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app

SALT = "dashboard-invite"
MAX_AGE_SECONDS = 60 * 10  # 10 minutes
STRICT = object()
_INVITATION_PATH = re.compile(r"^/invitations/([^/?#]+)$")

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)

def generate_invite_token(invite):
    return _serializer().dumps({"invite_id": invite.id, "email": invite.email})

def load_invite_token(token, max_age=STRICT):
    """Pass max_age=None to check the signature only."""
    if max_age is STRICT:
        max_age = MAX_AGE_SECONDS
    try:
        return _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        return "expired"
    except BadSignature:
        return None

def invite_token_from_next(next_url):
    match = _INVITATION_PATH.match(next_url or "")
    return match.group(1) if match else None

def invited_email_from_next(next_url):
    token = invite_token_from_next(next_url)
    if token is None:
        return None
    data = load_invite_token(token)
    if not isinstance(data, dict) or not isinstance(data.get("email"), str):
        return None
    return data["email"].strip().lower()
