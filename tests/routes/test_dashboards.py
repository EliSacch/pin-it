from app.extensions import db
from app.models import Dashboard, Invite
from tests.conftest import CSRF_TOKEN, invite_url_token, login, mail_outbox

JSON_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def create_path():
    return "/dashboards/create"


def update_path(dashboard):
    return f"/dashboards/{dashboard.id}/update"


def settings_path(dashboard):
    return f"/dashboards/{dashboard.id}/{dashboard.slug}/settings"


def invites_for(dashboard):
    return db.session.scalars(
        db.select(Invite).where(Invite.dashboard_id == dashboard.id)
    ).all()


def add_collaborator(dashboard, person):
    db.session.add(
        Invite(
            dashboard_id=dashboard.id,
            email=person.email,
            user_id=person.id,
            status="accepted",
        )
    )
    db.session.commit()


def test_collaborator_can_view_shared_dashboard_and_sees_it_in_nav(
    client, user, other_user, dashboard
):
    add_collaborator(dashboard, other_user)
    login(client, other_user)

    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'href="/dashboards/{dashboard.id}/{dashboard.slug}"' in html
    assert 'class="dashboard-nav-owner"' in html
    assert '<span class="visually-hidden">shared </span>by elisa' in html
    assert 'aria-label="Dashboard settings"' not in html


def test_owner_nav_has_no_owner_line(client, user, other_user, dashboard):
    add_collaborator(dashboard, other_user)
    login(client, user)

    html = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}").get_data(as_text=True)

    assert 'class="dashboard-nav-name">Work</span>' in html
    assert 'class="dashboard-nav-owner"' not in html


def test_pending_invitee_cannot_view_dashboard(client, other_user, dashboard):
    db.session.add(
        Invite(dashboard_id=dashboard.id, email=other_user.email, user_id=other_user.id)
    )
    db.session.commit()
    login(client, other_user)

    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    assert response.status_code == 404


def test_collaborator_cannot_manage_dashboard(client, other_user, dashboard):
    add_collaborator(dashboard, other_user)
    login(client, other_user)

    settings_response = client.get(settings_path(dashboard))
    update_response = client.post(
        update_path(dashboard), data={"name": "Taken", "csrf_token": CSRF_TOKEN}
    )
    delete_response = client.post(
        f"/dashboards/{dashboard.id}/delete",
        data={"csrf_token": CSRF_TOKEN},
        headers=JSON_HEADERS,
    )

    db.session.refresh(dashboard)
    assert settings_response.status_code == 404
    assert update_response.status_code == 404
    assert delete_response.status_code == 400
    assert dashboard.name == "Work"


def test_owner_sees_settings_gear(client, user, dashboard):
    login(client, user)

    html = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}").get_data(as_text=True)

    assert 'aria-label="Dashboard settings"' in html


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


def test_create_dashboard_sends_invite_emails(app, client, user):
    login(client, user)

    client.post(
        create_path(),
        data={
            "name": "Shared",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["a@example.com", "b@example.com"],
        },
        headers=JSON_HEADERS,
    )

    outbox = mail_outbox(app)
    assert sorted(message.to[0] for message in outbox) == ["a@example.com", "b@example.com"]
    assert all(invite_url_token(message) for message in outbox)


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


def test_create_error_redirect_preserves_invite_emails_in_form(client, user):
    login(client, user)

    response = client.post(
        create_path(),
        data={
            "name": "Shared",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["friend@example.com", "not-an-email"],
        },
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="invite_emails" value="friend@example.com"' in html
    assert 'name="invite_emails" value="not-an-email"' in html
    assert "Enter a valid email address." in html
    assert 'id="addDashboardForm-invite-emails"' in html
    assert db.session.scalar(db.select(Dashboard).where(Dashboard.name == "Shared")) is None


def test_dashboard_page_links_edit_to_settings(client, user, dashboard):
    login(client, user)

    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'href="{settings_path(dashboard)}"' in html
    assert "editDashboardModal" not in html
    assert html.count('type="hidden" name="invite_emails"') == html.count(
        'class="list-input-chip-template"'
    )


def test_settings_requires_login(client, dashboard):
    response = client.get(settings_path(dashboard))

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_settings_returns_404_for_another_users_dashboard(client, user, other_user):
    other_dashboard = Dashboard(name="Secret", owner_id=other_user.id, is_default=False)
    db.session.add(other_dashboard)
    db.session.commit()
    login(client, user)

    response = client.get(settings_path(other_dashboard))

    assert response.status_code == 404


def test_settings_returns_403_for_default_dashboard(client, user, default_dashboard):
    login(client, user)

    response = client.get(settings_path(default_dashboard))

    assert response.status_code == 403


def test_settings_redirects_stale_slug(client, user, dashboard):
    login(client, user)

    response = client.get(f"/dashboards/{dashboard.id}/old-name/settings")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))


def test_settings_renders_name_and_invites(client, user, other_user, dashboard):
    db.session.add_all([
        Invite(dashboard_id=dashboard.id, email="other@example.com",
               user_id=other_user.id, status="accepted"),
        Invite(dashboard_id=dashboard.id, email="new@example.com", status="pending"),
    ])
    db.session.commit()
    login(client, user)

    response = client.get(settings_path(dashboard))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'value="Work"' in html
    assert "other@example.com" in html
    assert "Accepted" in html
    assert "new@example.com" in html
    assert "Pending" in html
    assert f'action="/dashboards/{dashboard.id}/invites/create"' in html
    assert 'aria-label="Back to dashboard"' in html


def test_settings_renders_empty_collaborators(client, user, dashboard):
    login(client, user)

    response = client.get(settings_path(dashboard))

    assert "No collaborators yet." in response.get_data(as_text=True)


def test_update_requires_login(client, dashboard):
    response = client.post(
        update_path(dashboard),
        data={"name": "Renamed", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(Dashboard, dashboard.id).name == "Work"


def test_update_get_redirects_to_settings(client, user, dashboard):
    login(client, user)

    response = client.get(update_path(dashboard))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(settings_path(dashboard))


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
        f"/dashboards/{dashboard.id}/my-board/settings"
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
    assert payload["redirect_url"].endswith(f"/dashboards/{dashboard.id}/ideas/settings")
    assert db.session.get(Dashboard, dashboard.id).name == "Ideas"


def test_update_errors_render_on_settings_page(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={"name": "   ", "csrf_token": CSRF_TOKEN},
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Name is required." in html
    assert 'id="update-dashboard-name-form-name"' in html
    assert db.session.get(Dashboard, dashboard.id).name == "Work"


def test_update_ignores_invite_emails(client, user, dashboard):
    login(client, user)

    response = client.post(
        update_path(dashboard),
        data={
            "name": "Work",
            "csrf_token": CSRF_TOKEN,
            "invite_emails": ["new@example.com"],
        },
    )

    assert response.status_code == 302
    assert invites_for(dashboard) == []
