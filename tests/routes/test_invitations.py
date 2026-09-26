from unittest.mock import patch
from urllib.parse import quote

from app.extensions import db
from app.helpers.invite_tokens import generate_invite_token
from app.models import Invite, User
from tests.conftest import CSRF_TOKEN, login


def invitation_path(token):
    return f"/invitations/{token}"


def dashboard_path(dashboard):
    return f"/dashboards/{dashboard.id}/{dashboard.slug}"


def make_invite(dashboard, email="other@example.com"):
    invite = Invite(dashboard_id=dashboard.id, email=email)
    db.session.add(invite)
    db.session.commit()
    return invite


def flashes(client):
    with client.session_transaction() as session:
        return session.get("_flashes", [])


def test_invitation_requires_login_and_keeps_next(client, dashboard):
    token = generate_invite_token(make_invite(dashboard))

    response = client.get(invitation_path(token))

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/login" in location
    assert quote(invitation_path(token), safe="") in location


def test_login_redirects_back_to_invitation(client, other_user, dashboard):
    token = generate_invite_token(make_invite(dashboard))
    client.get("/login")
    with client.session_transaction() as session:
        csrf_token = session["login_csrf_token"]

    response = client.post(
        "/login",
        data={
            "email": "other@example.com",
            "password": "ValidPass123!",
            "csrf_token": csrf_token,
            "next": invitation_path(token),
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(invitation_path(token))


def test_login_ignores_external_next(client, other_user):
    client.get("/login")
    with client.session_transaction() as session:
        csrf_token = session["login_csrf_token"]

    response = client.post(
        "/login",
        data={
            "email": "other@example.com",
            "password": "ValidPass123!",
            "csrf_token": csrf_token,
            "next": "//evil.example.com/",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_login_page_carries_next_into_form_and_register_link(client):
    response = client.get("/login?next=/invitations/abc")

    html = response.get_data(as_text=True)
    assert 'name="next" value="/invitations/abc"' in html
    assert "/register?next=/invitations/abc" in html


def test_login_page_prefills_invited_email_without_locking(client, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="friend@example.com"))

    response = client.get(f"/login?next={invitation_path(token)}")

    html = response.get_data(as_text=True)
    assert 'value="friend@example.com"' in html
    assert "readonly" not in html


def test_login_error_keeps_submitted_email_over_invited(client, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="friend@example.com"))
    client.get("/login")
    with client.session_transaction() as session:
        csrf_token = session["login_csrf_token"]

    response = client.post(
        "/login",
        data={
            "email": "someone-else@example.com",
            "password": "WrongPass123!",
            "csrf_token": csrf_token,
            "next": invitation_path(token),
        },
    )

    html = response.get_data(as_text=True)
    assert 'value="someone-else@example.com"' in html
    assert 'value="friend@example.com"' not in html


def test_register_page_prefills_and_locks_invited_email(client, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="friend@example.com"))

    response = client.get(f"/register?next={invitation_path(token)}")

    html = response.get_data(as_text=True)
    assert 'value="friend@example.com"' in html
    assert "readonly" in html
    assert "This is the address you were invited with." in html


def test_register_page_does_not_lock_email_for_expired_token(client, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="friend@example.com"))

    with patch("app.helpers.invite_tokens.MAX_AGE_SECONDS", -1):
        response = client.get(f"/register?next={invitation_path(token)}")

    html = response.get_data(as_text=True)
    assert "friend@example.com" not in html
    assert "readonly" not in html


def register_via_invite(client, token, email="friend@example.com"):
    client.get("/register")
    with client.session_transaction() as session:
        csrf_token = session["register_csrf_token"]
    return client.post(
        "/register",
        data={
            "username": "friend",
            "email": email,
            "password": "ValidPass123!",
            "confirm_password": "ValidPass123!",
            "csrf_token": csrf_token,
            "next": invitation_path(token),
        },
    )


def test_register_uses_invited_email_even_if_changed(client, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="friend@example.com"))

    response = register_via_invite(client, token, email="tampered@example.com")

    assert response.status_code == 302
    created = db.session.scalar(db.select(User).where(User.username == "friend"))
    assert created.email == "friend@example.com"


def test_register_via_invite_auto_accepts(client, dashboard):
    invite = make_invite(dashboard, email="friend@example.com")
    token = generate_invite_token(invite)

    response = register_via_invite(client, token)

    created = db.session.scalar(db.select(User).where(User.username == "friend"))
    db.session.refresh(invite)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(dashboard_path(dashboard))
    assert invite.status == "accepted"
    assert invite.user_id == created.id
    assert ("success", "Welcome! You joined Work.") in flashes(client)


def test_register_via_expired_invite_creates_account_without_joining(client, dashboard):
    invite = make_invite(dashboard, email="friend@example.com")
    token = generate_invite_token(invite)

    with patch("app.helpers.invite_tokens.MAX_AGE_SECONDS", -1):
        response = register_via_invite(client, token, email="friend@example.com")

    db.session.refresh(invite)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert db.session.scalar(db.select(User).where(User.username == "friend")) is not None
    assert invite.status == "pending"
    assert any("expired" in message for _, message in flashes(client))


def test_valid_invitation_renders_page(client, other_user, dashboard):
    token = generate_invite_token(make_invite(dashboard))
    login(client, other_user)

    response = client.get(invitation_path(token))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "You were invited." in html
    assert "<strong>Work</strong>" in html
    assert "<strong>elisa</strong>" in html
    assert f'action="{invitation_path(token)}/accept"' in html
    assert f'action="{invitation_path(token)}/decline"' in html


def login_with_invitations_token(client, user):
    login(client, user)
    with client.session_transaction() as session:
        session["invitations_csrf_token"] = CSRF_TOKEN


def test_accept_sets_status_and_redirects_to_dashboard(client, other_user, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)
    login_with_invitations_token(client, other_user)

    response = client.post(f"{invitation_path(token)}/accept", data={"csrf_token": CSRF_TOKEN})

    db.session.refresh(invite)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(dashboard_path(dashboard))
    assert invite.status == "accepted"
    assert invite.user_id == other_user.id
    assert ("success", "You joined Work.") in flashes(client)


def test_decline_sets_rejected_and_redirects_home(client, other_user, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)
    login_with_invitations_token(client, other_user)

    response = client.post(f"{invitation_path(token)}/decline", data={"csrf_token": CSRF_TOKEN})

    db.session.refresh(invite)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert invite.status == "rejected"
    assert ("info", "Invitation declined.") in flashes(client)


def test_accept_rejects_bad_csrf(client, other_user, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)
    login_with_invitations_token(client, other_user)

    response = client.post(f"{invitation_path(token)}/accept", data={"csrf_token": "wrong"})

    db.session.refresh(invite)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(invitation_path(token))
    assert invite.status == "pending"


def test_accept_rejects_mismatched_email(client, user, dashboard):
    invite = make_invite(dashboard, email="someone@example.com")
    token = generate_invite_token(invite)
    login_with_invitations_token(client, user)

    client.post(f"{invitation_path(token)}/accept", data={"csrf_token": CSRF_TOKEN})

    db.session.refresh(invite)
    assert invite.status == "pending"
    assert any("different email" in message for _, message in flashes(client))


def test_accept_rejects_already_declined_invite(client, other_user, dashboard):
    invite = make_invite(dashboard)
    invite.status = "rejected"
    db.session.commit()
    token = generate_invite_token(invite)
    login_with_invitations_token(client, other_user)

    response = client.post(f"{invitation_path(token)}/accept", data={"csrf_token": CSRF_TOKEN})

    db.session.refresh(invite)
    assert response.headers["Location"] == "/"
    assert invite.status == "rejected"
    assert ("info", "You already declined this invitation.") in flashes(client)


def test_expired_token_still_works_on_post(client, other_user, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)
    login_with_invitations_token(client, other_user)

    with patch("app.helpers.invite_tokens.MAX_AGE_SECONDS", -1):
        get_response = client.get(invitation_path(token))
        client.post(f"{invitation_path(token)}/accept", data={"csrf_token": CSRF_TOKEN})

    db.session.refresh(invite)
    assert get_response.status_code == 302
    assert get_response.headers["Location"] == "/"
    assert invite.status == "accepted"


def test_reopening_accepted_invite_redirects_to_dashboard(client, other_user, dashboard):
    invite = make_invite(dashboard)
    invite.status = "accepted"
    invite.user_id = other_user.id
    db.session.commit()
    token = generate_invite_token(invite)
    login(client, other_user)

    response = client.get(invitation_path(token))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(dashboard_path(dashboard))


def test_expired_invitation_redirects_with_warning(client, other_user, dashboard):
    token = generate_invite_token(make_invite(dashboard))
    login(client, other_user)

    with patch("app.helpers.invite_tokens.MAX_AGE_SECONDS", -1):
        response = client.get(invitation_path(token))

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert any("expired" in message for _, message in flashes(client))


def test_tampered_invitation_is_invalid(client, other_user, dashboard):
    token = generate_invite_token(make_invite(dashboard))
    login(client, other_user)

    response = client.get(invitation_path(token + "x"))

    assert response.status_code == 302
    assert ("warning", "This invitation link is invalid.") in flashes(client)


def test_deleted_invitation_is_invalid(client, other_user, dashboard):
    invite = make_invite(dashboard)
    token = generate_invite_token(invite)
    db.session.delete(invite)
    db.session.commit()
    login(client, other_user)

    response = client.get(invitation_path(token))

    assert response.status_code == 302
    assert ("warning", "This invitation link is invalid.") in flashes(client)


def test_invitation_for_different_email_is_rejected(client, user, dashboard):
    token = generate_invite_token(make_invite(dashboard, email="someone@example.com"))
    login(client, user)

    response = client.get(invitation_path(token))

    assert response.status_code == 302
    assert any("different email" in message for _, message in flashes(client))
