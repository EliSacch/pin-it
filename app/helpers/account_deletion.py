from app.extensions import db
from app.helpers.time import utc_now
from app.models import Dashboard, Note


def delete_user_account(user):
    """Stage a permanent account deletion; the caller commits or rolls back.

    Owned dashboards (with all their notes and invites) and the user's invites
    are removed. Notes the user wrote on other people's dashboards are kept and
    marked as authored by a deleted account.
    """
    db.session.execute(
        db.update(Note)
        .where(
            Note.owner_id == user.id,
            Note.dashboard_id.in_(db.select(Dashboard.id).where(Dashboard.owner_id != user.id)),
        )
        .values(owner_id=None, owner_deleted_at=utc_now())
        .execution_options(synchronize_session="fetch")
    )
    # Owned dashboards go first: deleting the user directly would let
    # ON DELETE SET NULL reach their notes before the dashboard cascade does,
    # violating ck_notes_owner_or_owner_deleted_at.
    db.session.execute(
        db.delete(Dashboard)
        .where(Dashboard.owner_id == user.id)
        .execution_options(synchronize_session="fetch")
    )
    db.session.delete(user)
