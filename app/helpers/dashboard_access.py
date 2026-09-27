from flask import abort
from flask_login import current_user

from app.extensions import db
from app.models import Dashboard, Invite


def _accepted_invite_filter(user):
    return (
        Invite.user_id == user.id,
        Invite.status == "accepted",
        Invite.deleted_at.is_(None),
    )


def is_dashboard_member(dashboard, user):
    if dashboard is None or user is None or not user.is_authenticated:
        return False
    if dashboard.owner_id == user.id:
        return True
    return (
        db.session.scalar(
            db.select(Invite.id).where(
                Invite.dashboard_id == dashboard.id,
                *_accepted_invite_filter(user),
            )
        )
        is not None
    )


def accepted_invite_for(dashboard, user):
    return db.session.scalar(
        db.select(Invite).where(
            Invite.dashboard_id == dashboard.id,
            *_accepted_invite_filter(user),
        )
    )


def get_member_dashboard_or_404(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not is_dashboard_member(dashboard, current_user):
        abort(404)
    return dashboard


def can_manage_note(note, dashboard, user):
    return note.owner_id == user.id or dashboard.owner_id == user.id


def member_dashboards(user):
    shared_ids = db.select(Invite.dashboard_id).where(*_accepted_invite_filter(user))
    return db.session.scalars(
        db.select(Dashboard)
        .where((Dashboard.owner_id == user.id) | Dashboard.id.in_(shared_ids))
        .order_by(Dashboard.created_at.asc())
    ).all()
