from app.extensions import db
from app.models import Dashboard, Invite, User
from unittest.mock import patch
import smtplib

from app.helpers.invite_tokens import load_invite_token
from app.helpers.time import utc_now
from tests.conftest import CSRF_TOKEN, invite_url_token, login, mail_outbox

JSON_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def create_invite_path(dashboard):
    return f"/dashboards/{dashboard.id}/invites/create"


def settings_path(dashboard):
    return f"/dashboards/{dashboard.id}/{dashboard.slug}/settings"


def login_with_invites_token(client, user):
    login(client, user)
    with client.session_transaction() as session:
        session["invites_csrf_token"] = CSRF_TOKEN


def invites_for(dashboard):
    return db.session.scalars(
        db.select(Invite).where(Invite.dashboard_id == dashboard.id)
    ).all()


def test_create_invite_requires_login(client, dashboard):
    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["test@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert invites_for(dashboard) == []


def test_create_invite_returns_404_for_missing_dashboard(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        "/dashboards/999/invites/create",
        data={"invite_emails": ["test@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404


def test_create_invite_returns_404_for_another_users_dashboard(
    client, user, other_user
):
    other_user_dashboard = Dashboard(
        name="Secret", owner_id=other_user.id, is_default=False
    )
    db.session.add(other_user_dashboard)
    db.session.commit()
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(other_user_dashboard),
        data={"invite_emails": ["test@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404
    assert invites_for(other_user_dashboard) == []


def test_create_invite_returns_403_for_default_dashboard(
    client, user, default_dashboard
):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(default_dashboard),
        data={"invite_emails": ["test@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 403
    assert invites_for(default_dashboard) == []


def test_create_invite_rejects_invalid_csrf(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["test@example.com"], "csrf_token": "wrong-token"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert invites_for(dashboard) == []
    with client.session_transaction() as session:
        errors = session["invite_form_errors"]["create"]
        assert errors["form"] == ["Invalid form submission."]


def test_create_invite_adds_invites_and_redirects_to_settings(
    client, user, other_user, dashboard
):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={
            "invite_emails": ["Other@example.com", "new@example.com"],
            "csrf_token": CSRF_TOKEN,
        },
    )

    invites_by_email = {invite.email: invite for invite in invites_for(dashboard)}
    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert set(invites_by_email) == {"other@example.com", "new@example.com"}
    assert invites_by_email["other@example.com"].user_id == other_user.id
    assert invites_by_email["new@example.com"].user_id is None
    assert all(invite.status == "pending" for invite in invites_by_email.values())
    with client.session_transaction() as session:
        assert "invites_csrf_token" not in session
        assert ("success", "Collaborators added.") in session.get("_flashes", [])


def test_create_invite_json(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["new@example.com"], "csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["redirect_url"].endswith(settings_path(dashboard))


def test_create_invite_skips_existing_invites(client, user, other_user, dashboard):
    existing = Invite(
        dashboard_id=dashboard.id,
        email="other@example.com",
        user_id=other_user.id,
        status="pending",
    )
    db.session.add(existing)
    db.session.commit()
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={
            "invite_emails": ["other@example.com", "fresh@example.com"],
            "csrf_token": CSRF_TOKEN,
        },
    )

    invites = invites_for(dashboard)
    assert response.status_code == 302
    assert {invite.email for invite in invites} == {
        "other@example.com",
        "fresh@example.com",
    }
    assert [invite.id for invite in invites if invite.email == "other@example.com"] == [
        existing.id
    ]


def test_create_invite_sends_email_per_new_invite(app, client, user, dashboard):
    db.session.add(Invite(dashboard_id=dashboard.id, email="old@example.com"))
    db.session.commit()
    login_with_invites_token(client, user)

    client.post(
        create_invite_path(dashboard),
        data={
            "invite_emails": ["old@example.com", "new@example.com"],
            "csrf_token": CSRF_TOKEN,
        },
    )

    outbox = mail_outbox(app)
    assert len(outbox) == 1
    assert outbox[0].to == ["new@example.com"]
    assert "this link expires in 7 days" in outbox[0].body
    invite = next(i for i in invites_for(dashboard) if i.email == "new@example.com")
    assert load_invite_token(invite_url_token(outbox[0])) == {
        "invite_id": invite.id,
        "email": "new@example.com",
    }


def test_create_invite_warns_when_email_fails(app, client, user, dashboard):
    login_with_invites_token(client, user)

    with patch(
        "app.helpers.invites.EmailMessage.send",
        side_effect=smtplib.SMTPException("down"),
    ):
        response = client.post(
            create_invite_path(dashboard),
            data={"invite_emails": ["new@example.com"], "csrf_token": CSRF_TOKEN},
        )

    assert response.status_code == 302
    assert [invite.email for invite in invites_for(dashboard)] == ["new@example.com"]
    with client.session_transaction() as session:
        assert (
            "warning",
            "Collaborators added, but we could not email: new@example.com.",
        ) in session.get("_flashes", [])


def test_create_invite_reports_when_all_already_invited(
    client, user, other_user, dashboard
):
    db.session.add(Invite(dashboard_id=dashboard.id, email="other@example.com"))
    db.session.commit()
    login_with_invites_token(client, user)

    client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["other@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert len(invites_for(dashboard)) == 1
    with client.session_transaction() as session:
        assert ("info", "Those collaborators are already invited.") in session.get(
            "_flashes", []
        )


def test_create_invite_requires_at_least_one_email(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["  "], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert invites_for(dashboard) == []
    with client.session_transaction() as session:
        errors = session["invite_form_errors"]["create"]
        assert errors["invite_emails"] == ["Add at least one email address."]


def test_create_invite_rejects_invalid_email_and_keeps_values(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={
            "invite_emails": ["good@example.com", "not-an-email"],
            "csrf_token": CSRF_TOKEN,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert invites_for(dashboard) == []
    with client.session_transaction() as session:
        assert session["invite_form_errors"]["create"]["invite_emails"] == [
            "Enter a valid email address."
        ]
        assert session["invite_form_values"]["create"]["invite_emails"] == [
            "good@example.com",
            "not-an-email",
        ]


def test_create_invite_rejects_inviting_self(client, user, dashboard):
    login_with_invites_token(client, user)

    client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["elisa@example.com"], "csrf_token": CSRF_TOKEN},
    )

    assert invites_for(dashboard) == []
    with client.session_transaction() as session:
        assert session["invite_form_errors"]["create"]["invite_emails"] == [
            "You cannot invite yourself."
        ]


def test_settings_page_shows_invite_errors_and_values(client, user, dashboard):
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["not-an-email"], "csrf_token": CSRF_TOKEN},
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Enter a valid email address." in html
    assert 'name="invite_emails" value="not-an-email"' in html


def revoke_path(dashboard, invite):
    return f"/dashboards/{dashboard.id}/invites/{invite.id}/revoke"


def resend_path(dashboard, invite):
    return f"/dashboards/{dashboard.id}/invites/{invite.id}/resend"


def add_invite(dashboard, email="other@example.com", status="pending", user=None, deleted=False):
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


def test_revoke_requires_login(client, dashboard):
    invite = add_invite(dashboard)

    response = client.post(revoke_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(Invite, invite.id).deleted_at is None


def test_revoke_returns_404_for_another_users_dashboard(client, user, other_user):
    other_dashboard = Dashboard(name="Secret", owner_id=other_user.id, is_default=False)
    db.session.add(other_dashboard)
    db.session.commit()
    invite = add_invite(other_dashboard, email="someone@example.com")
    login_with_invites_token(client, user)

    response = client.post(revoke_path(other_dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 404
    assert db.session.get(Invite, invite.id).deleted_at is None


def test_revoke_returns_403_for_default_dashboard(client, user, default_dashboard):
    invite = add_invite(default_dashboard)
    login_with_invites_token(client, user)

    response = client.post(revoke_path(default_dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 403


def test_revoke_returns_404_for_invite_on_another_dashboard(client, user, dashboard):
    other_dashboard = Dashboard(name="Other", owner_id=user.id, is_default=False)
    db.session.add(other_dashboard)
    db.session.commit()
    invite = add_invite(other_dashboard)
    login_with_invites_token(client, user)

    response = client.post(revoke_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 404
    assert db.session.get(Invite, invite.id).deleted_at is None


def test_revoke_returns_404_for_missing_or_revoked_invite(client, user, dashboard):
    revoked = add_invite(dashboard, deleted=True)
    login_with_invites_token(client, user)

    missing = client.post(
        f"/dashboards/{dashboard.id}/invites/999/revoke", data={"csrf_token": CSRF_TOKEN}
    )
    already = client.post(revoke_path(dashboard, revoked), data={"csrf_token": CSRF_TOKEN})

    assert missing.status_code == 404
    assert already.status_code == 404


def test_revoke_rejects_invalid_csrf(client, user, dashboard):
    invite = add_invite(dashboard)
    login_with_invites_token(client, user)

    response = client.post(revoke_path(dashboard, invite), data={"csrf_token": "wrong"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert db.session.get(Invite, invite.id).deleted_at is None
    with client.session_transaction() as session:
        assert session["invite_form_errors"]["revoke"]["form"] == ["Invalid form submission."]


def test_revoke_soft_deletes_invite(client, user, dashboard):
    invite = add_invite(dashboard)
    login_with_invites_token(client, user)

    response = client.post(revoke_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert db.session.get(Invite, invite.id).deleted_at is not None
    with client.session_transaction() as session:
        assert ("success", "Access revoked.") in session.get("_flashes", [])


def test_revoke_json(client, user, dashboard):
    invite = add_invite(dashboard)
    login_with_invites_token(client, user)

    response = client.post(
        revoke_path(dashboard, invite),
        data={"csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["redirect_url"].endswith(settings_path(dashboard))


def test_revoked_collaborator_loses_access(client, user, other_user, dashboard):
    invite = add_invite(dashboard, status="accepted", user=other_user)
    login_with_invites_token(client, user)
    client.post(revoke_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    login(client, other_user)
    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    assert response.status_code == 404


def test_revoked_invite_disappears_from_settings(client, user, dashboard):
    add_invite(dashboard, email="gone@example.com", deleted=True)
    login_with_invites_token(client, user)

    html = client.get(settings_path(dashboard)).get_data(as_text=True)

    assert "gone@example.com" not in html


def test_reinvite_after_revoke_revives_invite(app, client, user, other_user, dashboard):
    invite = add_invite(dashboard, status="accepted", user=other_user, deleted=True)
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": ["other@example.com"], "csrf_token": CSRF_TOKEN},
    )

    invites = invites_for(dashboard)
    assert response.status_code == 302
    assert [i.id for i in invites] == [invite.id]
    assert invites[0].deleted_at is None
    assert invites[0].status == "pending"
    assert len(mail_outbox(app)) == 1


def test_resend_requires_login(client, dashboard):
    invite = add_invite(dashboard, status="rejected")

    response = client.post(resend_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(Invite, invite.id).status == "rejected"


def test_resend_returns_404_for_another_users_dashboard(client, user, other_user):
    other_dashboard = Dashboard(name="Secret", owner_id=other_user.id, is_default=False)
    db.session.add(other_dashboard)
    db.session.commit()
    invite = add_invite(other_dashboard, email="someone@example.com")
    login_with_invites_token(client, user)

    response = client.post(resend_path(other_dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 404


def test_resend_returns_404_for_accepted_invite(app, client, user, other_user, dashboard):
    invite = add_invite(dashboard, status="accepted", user=other_user)
    login_with_invites_token(client, user)

    response = client.post(resend_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    assert response.status_code == 404
    assert mail_outbox(app) == []


def test_resend_rejects_invalid_csrf(app, client, user, dashboard):
    invite = add_invite(dashboard, status="rejected")
    login_with_invites_token(client, user)

    response = client.post(resend_path(dashboard, invite), data={"csrf_token": "wrong"})

    assert response.status_code == 302
    assert db.session.get(Invite, invite.id).status == "rejected"
    assert mail_outbox(app) == []


def test_resend_resets_rejected_invite_and_sends_email(app, client, user, other_user, dashboard):
    invite = add_invite(dashboard, status="rejected")
    login_with_invites_token(client, user)

    response = client.post(resend_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    refreshed = db.session.get(Invite, invite.id)
    outbox = mail_outbox(app)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))
    assert refreshed.status == "pending"
    assert refreshed.user_id == other_user.id
    assert len(outbox) == 1
    assert outbox[0].to == ["other@example.com"]
    assert load_invite_token(invite_url_token(outbox[0])) == {
        "invite_id": invite.id,
        "email": "other@example.com",
    }
    with client.session_transaction() as session:
        assert (
            "success",
            "Invitation sent again to other@example.com.",
        ) in session.get("_flashes", [])


def test_resend_warns_when_email_fails(client, user, dashboard):
    invite = add_invite(dashboard)
    login_with_invites_token(client, user)

    with patch(
        "app.helpers.invites.EmailMessage.send",
        side_effect=smtplib.SMTPException("down"),
    ):
        client.post(resend_path(dashboard, invite), data={"csrf_token": CSRF_TOKEN})

    with client.session_transaction() as session:
        assert (
            "warning",
            "We could not email other@example.com. Please try again.",
        ) in session.get("_flashes", [])


def test_settings_page_shows_row_actions_by_status(client, user, dashboard):
    pending = add_invite(dashboard, email="pending@example.com")
    rejected = add_invite(dashboard, email="rejected@example.com", status="rejected")
    accepted = add_invite(dashboard, email="accepted@example.com", status="accepted")
    login_with_invites_token(client, user)

    html = client.get(settings_path(dashboard)).get_data(as_text=True)

    for invite in (pending, rejected, accepted):
        assert f'data-form-action="{revoke_path(dashboard, invite)}"' in html
        assert f'aria-label="Revoke access for {invite.email}"' in html
    assert f'action="{resend_path(dashboard, pending)}"' in html
    assert f'action="{resend_path(dashboard, rejected)}"' in html
    assert resend_path(dashboard, accepted) not in html
    assert 'id="revokeCollaboratorModal"' in html


PROFILE_CSRF = "test-profile-csrf-token"
NEW_EMAIL = "renamed@example.com"


def change_email_via_profile(client, person, email=NEW_EMAIL):
    login(client, person)
    with client.session_transaction() as session:
        session["profile_csrf_token"] = PROFILE_CSRF
    response = client.post(
        f"/profile/{person.id}/update-email",
        data={"email": email, "csrf_token": PROFILE_CSRF},
    )
    assert response.status_code == 302
    assert db.session.get(User, person.id).email == email


def invite_emails_sent(app):
    return [message for message in mail_outbox(app) if "/invitations/" in message.body]


def test_accepted_collaborator_keeps_access_after_email_change(
    client, other_user, dashboard
):
    add_invite(dashboard, status="accepted", user=other_user)

    change_email_via_profile(client, other_user)
    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    assert response.status_code == 200


def test_inviting_accepted_collaborators_new_email_is_skipped(
    app, client, user, other_user, dashboard
):
    existing = add_invite(dashboard, status="accepted", user=other_user)
    change_email_via_profile(client, other_user)
    login_with_invites_token(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"invite_emails": [NEW_EMAIL], "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert [invite.id for invite in invites_for(dashboard)] == [existing.id]
    assert invite_emails_sent(app) == []
    with client.session_transaction() as session:
        assert ("info", "Those collaborators are already invited.") in session.get(
            "_flashes", []
        )


def test_inviting_pending_collaborators_new_email_is_skipped(
    app, client, user, other_user, dashboard
):
    existing = add_invite(dashboard, user=other_user)
    change_email_via_profile(client, other_user)
    login_with_invites_token(client, user)

    client.post(
        create_invite_path(dashboard),
        data={"invite_emails": [NEW_EMAIL], "csrf_token": CSRF_TOKEN},
    )

    assert [invite.id for invite in invites_for(dashboard)] == [existing.id]
    assert invite_emails_sent(app) == []


def test_inviting_revoked_collaborators_new_email_revives_row(
    app, client, user, other_user, dashboard
):
    revoked = add_invite(dashboard, status="accepted", user=other_user, deleted=True)
    change_email_via_profile(client, other_user)
    login_with_invites_token(client, user)

    client.post(
        create_invite_path(dashboard),
        data={"invite_emails": [NEW_EMAIL], "csrf_token": CSRF_TOKEN},
    )

    invites = invites_for(dashboard)
    sent = invite_emails_sent(app)
    assert [(i.id, i.email, i.status, i.deleted_at) for i in invites] == [
        (revoked.id, NEW_EMAIL, "pending", None)
    ]
    assert len(sent) == 1
    assert sent[0].to == [NEW_EMAIL]
    assert load_invite_token(invite_url_token(sent[0])) == {
        "invite_id": revoked.id,
        "email": NEW_EMAIL,
    }
