from werkzeug.security import generate_password_hash

from app.extensions import db
from app.helpers.dashboard_access import (
    can_manage_note,
    is_dashboard_member,
    member_dashboards,
)
from app.helpers.time import utc_now
from app.models import Invite, Note, User


def add_invite(dashboard, user, status, deleted=False):
    invite = Invite(
        dashboard_id=dashboard.id,
        email=user.email,
        user_id=user.id,
        status=status,
        deleted_at=utc_now() if deleted else None,
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def test_owner_is_member(app, user, dashboard):
    assert is_dashboard_member(dashboard, user)


def test_accepted_invite_is_member(app, other_user, dashboard):
    add_invite(dashboard, other_user, "accepted")

    assert is_dashboard_member(dashboard, other_user)


def test_pending_rejected_and_deleted_invites_are_not_members(app, dashboard):
    for index, (status, deleted) in enumerate(
        [("pending", False), ("rejected", False), ("accepted", True)]
    ):
        person = User(
            username=f"person{index}",
            email=f"person{index}@example.com",
            password_hash=generate_password_hash("ValidPass123!"),
        )
        db.session.add(person)
        db.session.commit()
        add_invite(dashboard, person, status, deleted=deleted)

        assert not is_dashboard_member(dashboard, person)


def test_user_without_invite_is_not_member(app, other_user, dashboard):
    assert not is_dashboard_member(dashboard, other_user)


def test_can_manage_note(app, user, other_user, dashboard):
    owner_note = Note(title="Owner", owner_id=user.id, dashboard_id=dashboard.id)
    member_note = Note(title="Member", owner_id=other_user.id, dashboard_id=dashboard.id)

    assert can_manage_note(owner_note, dashboard, user)
    assert can_manage_note(member_note, dashboard, user)
    assert can_manage_note(member_note, dashboard, other_user)
    assert not can_manage_note(owner_note, dashboard, other_user)


def test_member_dashboards_includes_owned_and_accepted(app, user, other_user, dashboard):
    from app.models import Dashboard

    own = Dashboard(name="Mine", owner_id=other_user.id, is_default=False)
    pending_board = Dashboard(name="Pending", owner_id=user.id, is_default=False)
    db.session.add_all([own, pending_board])
    db.session.commit()
    add_invite(dashboard, other_user, "accepted")
    db.session.add(
        Invite(dashboard_id=pending_board.id, email=other_user.email, user_id=other_user.id)
    )
    db.session.commit()

    names = [board.name for board in member_dashboards(other_user)]

    assert sorted(names) == ["Mine", "Work"]
