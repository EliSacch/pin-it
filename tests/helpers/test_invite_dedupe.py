import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.helpers.invites import accept_invite, create_invites, decline_invite
from app.helpers.time import utc_now
from app.models import Dashboard, Invite, User

NEW_EMAIL = "renamed@example.com"


def add_invite(dashboard, email, status="pending", user=None, deleted=False):
    invite = Invite(
        dashboard_id=dashboard.id,
        email=email,
        user_id=user.id if user else None,
        status=status,
        deleted_at=utc_now() if deleted else None,
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def change_email(user, email=NEW_EMAIL):
    user.email = email
    db.session.commit()


def live_invites(dashboard):
    return db.session.scalars(
        db.select(Invite).where(
            Invite.dashboard_id == dashboard.id,
            Invite.deleted_at.is_(None),
        )
    ).all()


@pytest.mark.parametrize("status", ["pending", "accepted", "rejected"])
def test_create_skips_account_with_live_invite_under_old_email(
    app, other_user, dashboard, status
):
    existing = add_invite(dashboard, other_user.email, status=status, user=other_user)
    change_email(other_user)

    created = create_invites(dashboard, [NEW_EMAIL])
    db.session.commit()

    assert created == []
    assert [invite.id for invite in live_invites(dashboard)] == [existing.id]


def test_create_still_invites_unregistered_and_uninvited_users(app, other_user, dashboard):
    created = create_invites(dashboard, ["other@example.com", "stranger@example.com"])
    db.session.commit()

    by_email = {invite.email: invite for invite in created}
    assert set(by_email) == {"other@example.com", "stranger@example.com"}
    assert by_email["other@example.com"].user_id == other_user.id
    assert by_email["stranger@example.com"].user_id is None


def test_create_revives_revoked_row_by_user_id_and_updates_email(app, other_user, dashboard):
    revoked = add_invite(
        dashboard, other_user.email, status="accepted", user=other_user, deleted=True
    )
    change_email(other_user)

    created = create_invites(dashboard, [NEW_EMAIL])
    db.session.commit()

    assert [invite.id for invite in created] == [revoked.id]
    refreshed = db.session.get(Invite, revoked.id)
    assert refreshed.deleted_at is None
    assert refreshed.status == "pending"
    assert refreshed.email == NEW_EMAIL
    assert refreshed.user_id == other_user.id


def test_create_prefers_revoked_row_matching_email(app, other_user, dashboard):
    by_user = add_invite(
        dashboard, "old@example.com", status="accepted", user=other_user, deleted=True
    )
    by_email = add_invite(dashboard, other_user.email, deleted=True)

    created = create_invites(dashboard, [other_user.email])
    db.session.commit()

    assert [invite.id for invite in created] == [by_email.id]
    assert db.session.get(Invite, by_user.id).deleted_at is not None


def test_accept_soft_deletes_other_live_invite_on_same_dashboard(
    app, user, other_user, dashboard
):
    old = add_invite(dashboard, other_user.email, status="accepted", user=other_user)
    other_dashboard = Dashboard(name="Other", owner_id=user.id, is_default=False)
    db.session.add(other_dashboard)
    db.session.commit()
    elsewhere = add_invite(
        other_dashboard, other_user.email, status="accepted", user=other_user
    )
    change_email(other_user)
    new = add_invite(dashboard, NEW_EMAIL)

    accept_invite(new, other_user)
    db.session.commit()

    assert db.session.get(Invite, old.id).deleted_at is not None
    assert db.session.get(Invite, elsewhere.id).deleted_at is None
    assert [(i.id, i.status, i.email) for i in live_invites(dashboard)] == [
        (new.id, "accepted", NEW_EMAIL)
    ]


def test_decline_while_already_member_drops_declined_invite(app, other_user, dashboard):
    old = add_invite(dashboard, other_user.email, status="accepted", user=other_user)
    change_email(other_user)
    new = add_invite(dashboard, NEW_EMAIL)

    decline_invite(new, other_user)
    db.session.commit()

    assert db.session.get(Invite, new.id).deleted_at is not None
    assert [(i.id, i.status) for i in live_invites(dashboard)] == [(old.id, "accepted")]


def test_decline_drops_other_non_accepted_invite(app, dashboard):
    person = User(
        username="third",
        email="third@example.com",
        password_hash=generate_password_hash("ValidPass123!"),
    )
    db.session.add(person)
    db.session.commit()
    old = add_invite(dashboard, person.email, user=person)
    change_email(person)
    new = add_invite(dashboard, NEW_EMAIL)

    decline_invite(new, person)
    db.session.commit()

    assert db.session.get(Invite, old.id).deleted_at is not None
    assert [(i.id, i.status, i.user_id) for i in live_invites(dashboard)] == [
        (new.id, "rejected", person.id)
    ]
