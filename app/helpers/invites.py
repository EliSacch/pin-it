from sqlalchemy import func

from app.extensions import db
from app.helpers.email import collect_email_errors
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

    invites = []
    for email in emails_to_create:
        user = user_by_email.get(email)
        invite = Invite(
            dashboard=dashboard,
            email=email,
            user_id=user.id if user else None,
            status="pending",
        )
        db.session.add(invite)
        invites.append(invite)
    return invites
