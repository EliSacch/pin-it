import smtplib

from flask import current_app, url_for
from flask_mailman import EmailMessage
from sqlalchemy import func

from app.extensions import db
from app.helpers.email import collect_email_errors
from app.helpers import invite_tokens
from app.helpers.invite_tokens import STRICT, generate_invite_token, load_invite_token
from app.helpers.time import utc_now
from app.models import Invite, User


def submitted_invite_emails(form):
    return list(form.getlist("invite_emails"))


def normalized_invite_emails(raw_emails):
    emails = []
    seen = set()
    for raw in raw_emails or []:
        email = (raw or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        emails.append(email)
    return emails


def _dashboard_invites(dashboard, *, revoked):
    if dashboard is None or dashboard.id is None:
        return []
    deleted_filter = (
        Invite.deleted_at.is_not(None) if revoked else Invite.deleted_at.is_(None)
    )
    return db.session.scalars(
        db.select(Invite).where(Invite.dashboard_id == dashboard.id, deleted_filter)
    ).all()


def collect_invite_email_errors(raw_emails, *, owner_email):
    errors = []
    seen = set()
    owner = (owner_email or "").strip().lower()

    for raw in raw_emails or []:
        email = (raw or "").strip().lower()
        if not email:
            continue

        format_errors = collect_email_errors(email)
        for message in format_errors:
            if message not in errors:
                errors.append(message)

        if email in seen:
            if "Remove duplicate email addresses." not in errors:
                errors.append("Remove duplicate email addresses.")
            continue
        seen.add(email)

        if email == owner:
            errors.append("You cannot invite yourself.")

    return errors


def create_invites(dashboard, emails):
    live = _dashboard_invites(dashboard, revoked=False)
    live_emails = {invite.email.lower() for invite in live}
    live_user_ids = {invite.user_id for invite in live if invite.user_id}

    candidates = [email for email in emails if email not in live_emails]
    if not candidates:
        return []

    users = db.session.scalars(
        db.select(User).where(func.lower(User.email).in_(candidates))
    ).all()
    user_by_email = {user.email.lower(): user for user in users}
    emails_to_create = [
        email
        for email in candidates
        if not (email in user_by_email and user_by_email[email].id in live_user_ids)
    ]
    if not emails_to_create:
        return []

    revoked_by_email = {}
    revoked_by_user_id = {}
    for invite in _dashboard_invites(dashboard, revoked=True):
        revoked_by_email[invite.email.lower()] = invite
        if invite.user_id:
            revoked_by_user_id.setdefault(invite.user_id, invite)

    invites = []
    for email in emails_to_create:
        user = user_by_email.get(email)
        revoked = revoked_by_email.get(email)
        if revoked is None and user is not None:
            revoked = revoked_by_user_id.get(user.id)
            if revoked is not None and revoked.email.lower() in emails_to_create:
                revoked = None
        if revoked is not None:
            revoked.deleted_at = None
            revoked.status = "pending"
            revoked.email = email
            revoked.user_id = user.id if user else None
            invites.append(revoked)
            continue
        invite = Invite(
            dashboard=dashboard,
            email=email,
            user_id=user.id if user else None,
            status="pending",
        )
        db.session.add(invite)
        invites.append(invite)
    return invites


INVALID_INVITE_MESSAGE = "This invitation link is invalid."
EXPIRED_INVITE_MESSAGE = (
    "This invitation link has expired. Ask the dashboard owner to invite you again."
)
MISMATCHED_INVITE_MESSAGE = (
    "This invitation was sent to a different email address. "
    "Log in with the invited account to open it."
)


def load_invite(token, max_age=STRICT):
    """Returns (invite, None) on success or (None, error_message)."""
    data = load_invite_token(token, max_age=max_age)
    if data == "expired":
        return None, EXPIRED_INVITE_MESSAGE
    if not isinstance(data, dict):
        return None, INVALID_INVITE_MESSAGE

    invite = db.session.get(Invite, data.get("invite_id"))
    if invite is None or invite.deleted_at is not None or invite.email != data.get("email"):
        return None, INVALID_INVITE_MESSAGE
    return invite, None


def load_invite_for_user(token, user, max_age=STRICT):
    """Returns (invite, None) on success or (None, error_message)."""
    invite, error = load_invite(token, max_age=max_age)
    if error:
        return None, error
    if invite.email.lower() != (user.email or "").lower():
        return None, MISMATCHED_INVITE_MESSAGE
    return invite, None


def _other_live_invite(invite, user):
    return db.session.scalar(
        db.select(Invite).where(
            Invite.dashboard_id == invite.dashboard_id,
            Invite.user_id == user.id,
            Invite.deleted_at.is_(None),
            Invite.id != invite.id,
        )
    )


def accept_invite(invite, user):
    other = _other_live_invite(invite, user)
    if other is not None:
        other.deleted_at = utc_now()
    invite.status = "accepted"
    invite.user_id = user.id


def decline_invite(invite, user):
    other = _other_live_invite(invite, user)
    if other is not None and other.status == "accepted":
        invite.deleted_at = utc_now()
        return
    if other is not None:
        other.deleted_at = utc_now()
    invite.status = "rejected"
    invite.user_id = user.id


def revoke_invite(invite):
    invite.deleted_at = utc_now()


def prepare_invite_resend(invite):
    invite.status = "pending"
    if invite.user_id is None:
        invite.user_id = db.session.scalar(
            db.select(User.id).where(func.lower(User.email) == invite.email.lower())
        )


def send_invite_email(invite):
    token = generate_invite_token(invite)
    invite_url = url_for("invitations.show", token=token, _external=True)
    msg = EmailMessage(
        subject="You were invited to a PinIt dashboard",
        body=(
            f"Hi,\n\nYou were invited to collaborate on the "
            f"\"{invite.dashboard.name}\" dashboard.\n\n"
            f"Open your invitation (this link expires in "
            f"{invite_tokens.MAX_AGE_SECONDS // 86400} days):\n{invite_url}\n"
        ),
        to=[invite.email],
    )
    msg.send()


def send_invite_emails(invites):
    failed = []
    for invite in invites:
        try:
            send_invite_email(invite)
        except (OSError, smtplib.SMTPException):
            current_app.logger.exception("Failed to send invite email")
            failed.append(invite)
    return failed
