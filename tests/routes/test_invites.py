from app.extensions import db
from app.models import Dashboard, Invite
from tests.conftest import CSRF_TOKEN, login

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
