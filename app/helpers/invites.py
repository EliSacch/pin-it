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


def existing_invite_emails(dashboard):
    if dashboard is None or dashboard.id is None:
        return set()
    return {
        email.lower()
        for email in db.session.scalars(
            db.select(Invite.email).where(
                Invite.dashboard_id == dashboard.id,
                Invite.deleted_at.is_(None),
            )
        )
        if email
    }


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
    emails_to_create = [
        email for email in emails if email not in existing_invite_emails(dashboard)
    ]
    if not emails_to_create:
        return []

    users = db.session.scalars(
        db.select(User).where(func.lower(User.email).in_(emails_to_create))
    ).all()
    user_by_email = {user.email.lower(): user for user in users}

    revoked_by_email = {}
    if dashboard.id is not None:
        revoked_by_email = {
            invite.email.lower(): invite
            for invite in db.session.scalars(
                db.select(Invite).where(
                    Invite.dashboard_id == dashboard.id,
                    Invite.deleted_at.is_not(None),
                    func.lower(Invite.email).in_(emails_to_create),
                )
            )
        }

    invites = []
    for email in emails_to_create:
        user = user_by_email.get(email)
        revoked = revoked_by_email.get(email)
        if revoked is not None:
            revoked.deleted_at = None
            revoked.status = "pending"
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


def accept_invite(invite, user):
    invite.status = "accepted"
    invite.user_id = user.id


def decline_invite(invite, user):
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
            f"{invite_tokens.MAX_AGE_SECONDS // 60} minutes):\n{invite_url}\n"
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
