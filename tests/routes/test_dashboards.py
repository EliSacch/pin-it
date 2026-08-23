from app.extensions import db
from app.models import Dashboard, Invite
from tests.conftest import CSRF_TOKEN, login

JSON_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def create_path():
    return "/dashboards/create"


def update_path(dashboard):
    return f"/dashboards/{dashboard.id}/update"


def invites_for(dashboard):
    return db.session.scalars(
        db.select(Invite).where(Invite.dashboard_id == dashboard.id)
    ).all()


def test_create_requires_login(client):
    response = client.post(
        create_path(),
        data={"name": "Ideas", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Ideas")) is None


def test_create_dashboard_without_invite_emails(client, user):
    login(client, user)

    response = client.post(
        create_path(),
        data={"name": "Ideas", "csrf_token": CSRF_TOKEN},
    )

    created = db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Ideas"))
    assert response.status_code == 302
    assert created is not None
    assert created.owner_id == user.id
    assert invites_for(created) == []
    assert response.headers["Location"].endswith(f"/dashboards/{created.id}/ideas")


def test_create_dashboard_with_invite_emails(client, user, other_user):
    login(client, user)

    response = client.post(
        create_path(),
        data={
            "name": "Shared",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["other@example.com", "new@example.com"],
        },
        headers=JSON_HEADERS,
    )

    created = db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Shared"))
    payload = response.get_json()
    invites = invites_for(created)
    invites_by_email = {invite.email: invite for invite in invites}

    assert response.status_code == 200
    assert payload["ok"] is True
    assert created is not None
    assert set(invites_by_email) == {"other@example.com", "new@example.com"}
    assert invites_by_email["other@example.com"].user_id == other_user.id
    assert invites_by_email["other@example.com"].status == "pending"
    assert invites_by_email["new@example.com"].user_id is None
    assert invites_by_email["new@example.com"].status == "pending"


def test_create_rejects_invalid_invite_email_and_does_not_persist_dashboard(
    client, user
):
    login(client, user)

    response = client.post(
        create_path(),
        data={
            "name": "Broken",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["not-an-email"],
        },
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["errors"]["invite_emails"] == ["Enter a valid email address."]
    assert db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Broken")) is None


def test_create_rejects_inviting_self(client, user):
    login(client, user)

    response = client.post(
        create_path(),
        data={
            "name": "Mine",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["elisa@example.com"],
        },
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["errors"]["invite_emails"] == ["You cannot invite yourself."]
    assert db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Mine")) is None


def test_create_rejects_duplicate_invite_emails(client, user):
    login(client, user)

    response = client.post(
        create_path(),
        data={
            "name": "Dupes",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["a@example.com", "A@example.com"],
        },
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["errors"]["invite_emails"] == ["Remove duplicate email addresses."]
    assert db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Dupes")) is None


def test_update_requires_login(client, dashboard):
    response = client.post(
        update_path(dashboard),
        data={"name": "Renamed", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(Dashboard, dashboard.id).name == "Work"


def test_update_get_redirects_to_dashboard(client, user, dashboard):
    login(client, user)

    response = client.get(update_path(dashboard))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/dashboards/{dashboard.id}/work")


def test_update_returns_404_for_missing_dashboard(client, user):
    login(client, user)

    response = client.post(
        "/dashboards/999/update",
        data={"name": "Renamed", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404


def test_update_returns_404_for_another_users_dashboard(
    client, user, other_user
):
    other_dashboard = Dashboard(
        name="Secret", owner_id=other_user.id, is_default=False
    )
    db.session.add(other_dashboard)
    db.session.commit()
    login(client, user)

    response = client.post(
        update_path(other_dashboard),
        data={"name": "Stolen", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404
    assert db.session.get(Dashboard, other_dashboard.id).name == "Secret"


def test_update_rejects_renaming_default_dashboard(
    client, user, default_dashboard
):
    login(client, user)

    response = client.post(
        update_path(default_dashboard),
        data={"name": "Not Home", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert db.session.get(Dashboard, default_dashboard.id).name == "Home"
    with client.session_transaction() as session:
        errors = session["dashboard_form_errors"]["update"]
        assert errors["form"] == ["You cannot rename the default dashboard."]


def test_update_rejects_renaming_default_dashboard_json(
    client, user, default_dashboard
):
    login(client, user)

    response = client.post(
        update_path(default_dashboard),
        data={"name": "Not Home", "csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["retryable"] is False
    assert payload["errors"]["form"] == ["You cannot rename the default dashboard."]
    assert db.session.get(Dashboard, default_dashboard.id).name == "Home"


def test_update_rejects_invalid_csrf(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "Renamed", "csrf_token": "wrong-token"},
    )

    assert response.status_code == 302
    assert db.session.get(Dashboard, dashboard.id).name == "Work"
    with client.session_transaction() as session:
        errors = session["dashboard_form_errors"]["update"]
        assert errors["form"] == ["Invalid form submission."]


def test_update_requires_name(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "   ", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert db.session.get(Dashboard, dashboard.id).name == "Work"
    with client.session_transaction() as session:
        errors = session["dashboard_form_errors"]["update"]
        assert errors["name"] == ["Name is required."]
        assert session["dashboard_form_values"]["update"]["name"] == "   "


def test_update_rejects_name_longer_than_50_characters(client, user, dashboard):
    login(client, user)
    too_long = "a" * 51

    response = client.post(
        update_path(dashboard),
        data={"name": too_long, "csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["errors"]["name"] == ["Name must be less than 50 characters."]
    assert db.session.get(Dashboard, dashboard.id).name == "Work"


def test_update_rejects_duplicate_name_for_same_owner(client, user, dashboard):
    other = Dashboard(name="Personal", owner_id=user.id, is_default=False)
    db.session.add(other)
    db.session.commit()
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "Personal", "csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["errors"]["name"] == ["You already have a dashboard with this name."]
    assert db.session.get(Dashboard, dashboard.id).name == "Work"


def test_update_renames_dashboard_and_redirects(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "My Board", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/dashboards/{dashboard.id}/my-board"
    )
    updated = db.session.get(Dashboard, dashboard.id)
    assert updated.name == "My Board"
    with client.session_transaction() as session:
        assert "dashboards_csrf_token" not in session
        flashes = session.get("_flashes", [])
        assert ("success", "Dashboard updated successfully.") in flashes


def test_update_renames_dashboard_json(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "Ideas", "csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["redirect_url"].endswith(f"/dashboards/{dashboard.id}/ideas")
    assert db.session.get(Dashboard, dashboard.id).name == "Ideas"


def test_update_adds_invite_emails(client, user, other_user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={
            "name": "Work",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["other@example.com", "new@example.com"],
        },
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    invites = invites_for(dashboard)
    invites_by_email = {invite.email: invite for invite in invites}

    assert response.status_code == 200
    assert payload["ok"] is True
    assert set(invites_by_email) == {"other@example.com", "new@example.com"}
    assert invites_by_email["other@example.com"].user_id == other_user.id
    assert invites_by_email["new@example.com"].user_id is None


def test_update_skips_existing_invite_emails(client, user, other_user, dashboard):
    existing = Invite(
        dashboard_id=dashboard.id,
        email="other@example.com",
        user_id=other_user.id,
        status="pending",
    )
    db.session.add(existing)
    db.session.commit()
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={
            "name": "Renamed",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["other@example.com", "fresh@example.com"],
        },
        headers=JSON_HEADERS,
    )

    invites = invites_for(dashboard)
    assert response.status_code == 200
    assert db.session.get(Dashboard, dashboard.id).name == "Renamed"
    assert {invite.email for invite in invites} == {
        "other@example.com",
        "fresh@example.com",
    }
    assert {invite.id for invite in invites if invite.email == "other@example.com"} == {
        existing.id
    }


def test_update_rejects_invalid_invite_email_and_does_not_rename(
    client, user, dashboard
):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={
            "name": "Renamed",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["not-an-email"],
        },
        headers=JSON_HEADERS,
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["errors"]["invite_emails"] == ["Enter a valid email address."]
    assert db.session.get(Dashboard, dashboard.id).name == "Work"
    assert invites_for(dashboard) == []

