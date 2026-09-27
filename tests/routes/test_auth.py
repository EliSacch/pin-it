import smtplib
from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.helpers.dashboard_access import can_manage_note
from app.helpers.email_verification import generate_email_token, load_email_token
from app.models import Dashboard, Invite, Note, User
from tests.conftest import confirm_url_token, login, mail_outbox

PASSWORD = "ValidPass123!"
RESEND_CSRF = "test-resend-csrf-token"
DELETE_CSRF = "test-delete-account-csrf-token"


def register_csrf(client):
    client.get("/register")
    with client.session_transaction() as sess:
        return sess["register_csrf_token"]


def login_with_resend_csrf(client, user):
    login(client, user)
    with client.session_transaction() as sess:
        sess["resend_verification_csrf_token"] = RESEND_CSRF


def test_register_sends_verification_email(client, app):
    csrf_token = register_csrf(client)

    response = client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "username": "newuser",
            "email": "new@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )

    created = db.session.scalar(
        db.select(User).where(User.email == "new@example.com")
    )
    outbox = mail_outbox(app)

    assert response.status_code == 302
    assert created is not None
    assert created.email_verified is False
    assert len(outbox) == 1
    assert outbox[0].to == ["new@example.com"]
    assert "Verify your PinIt email" in outbox[0].subject
    assert f"/verify-email/{confirm_url_token(outbox[0])}" in outbox[0].body


def test_register_keeps_account_if_send_fails(client, app):
    csrf_token = register_csrf(client)

    with patch(
        "app.routes.auth.send_verification_email",
        side_effect=smtplib.SMTPException("smtp down"),
    ):
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "username": "mailfail",
                "email": "mailfail@example.com",
                "password": PASSWORD,
                "confirm_password": PASSWORD,
            },
        )

    created = db.session.scalar(
        db.select(User).where(User.email == "mailfail@example.com")
    )

    assert response.status_code == 302
    assert created is not None
    assert created.email_verified is False
    assert mail_outbox(app) == []


def test_resend_requires_login(client, app):
    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert mail_outbox(app) == []


def test_resend_rejects_invalid_csrf(client, app, user):
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": "wrong-token"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert mail_outbox(app) == []
    assert db.session.get(User, user.id).email_verified is False


def test_resend_sends_verification_email(client, app, user):
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )
    outbox = mail_outbox(app)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert len(outbox) == 1
    assert outbox[0].to == [user.email]
    token = confirm_url_token(outbox[0])
    assert load_email_token(token)["user_id"] == user.id


def test_resend_skips_when_already_verified(client, app, user):
    user.email_verified = True
    db.session.commit()
    login_with_resend_csrf(client, user)

    response = client.post(
        "/verify-email/resend",
        data={"csrf_token": RESEND_CSRF},
    )

    assert response.status_code == 302
    assert mail_outbox(app) == []


def test_resend_handles_smtp_failure(client, app, user):
    login_with_resend_csrf(client, user)

    with patch(
        "app.routes.auth.send_verification_email",
        side_effect=smtplib.SMTPException("smtp down"),
    ):
        response = client.post(
            "/verify-email/resend",
            data={"csrf_token": RESEND_CSRF},
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is False
    assert mail_outbox(app) == []


def test_verify_email_confirms_valid_token(client, app, user):
    token = generate_email_token(user)

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is True
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(user.id)


def test_verify_email_rejects_invalid_token(client, app, user):
    response = client.get("/verify-email/not-a-valid-token")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_rejects_expired_token(client, app, user):
    token = generate_email_token(user)

    with patch("app.helpers.email_verification.MAX_AGE_SECONDS", -1):
        response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_rejects_token_after_email_change(client, app, user):
    token = generate_email_token(user)
    user.email = "changed@example.com"
    db.session.commit()

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert db.session.get(User, user.id).email_verified is False


def test_verify_email_is_idempotent_when_already_verified(client, app, user):
    user.email_verified = True
    db.session.commit()
    token = generate_email_token(user)

    response = client.get(f"/verify-email/{token}")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/")
    assert db.session.get(User, user.id).email_verified is True


def test_register_then_confirm_from_email(client, app):
    csrf_token = register_csrf(client)
    client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "username": "flowuser",
            "email": "flow@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    token = confirm_url_token(mail_outbox(app)[0])

    response = client.get(f"/verify-email/{token}")
    created = db.session.scalar(
        db.select(User).where(User.email == "flow@example.com")
    )

    assert response.status_code == 302
    assert created.email_verified is True


def login_with_delete_csrf(client, user):
    login(client, user)
    with client.session_transaction() as sess:
        sess["delete_account_csrf_token"] = DELETE_CSRF


def post_delete_account(client, password=PASSWORD, csrf_token=DELETE_CSRF):
    return client.post(
        "/delete-account",
        data={"csrf_token": csrf_token, "current_password": password},
    )


def add_note(dashboard, author, title):
    note = Note(title=title, content_json="[]", owner_id=author.id, dashboard_id=dashboard.id)
    db.session.add(note)
    db.session.commit()
    return note


def add_member(dashboard, person):
    invite = Invite(
        dashboard_id=dashboard.id, email=person.email, user_id=person.id, status="accepted"
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def test_delete_account_requires_login(client, user):
    get_response = client.get("/delete-account")
    post_response = post_delete_account(client)

    assert "/login" in get_response.headers["Location"]
    assert "/login" in post_response.headers["Location"]
    assert db.session.get(User, user.id) is not None


def test_delete_account_page_renders_form(client, user):
    login(client, user)

    response = client.get("/delete-account")

    assert response.status_code == 200
    assert b'name="current_password"' in response.data
    assert b"cannot be undone" in response.data
    with client.session_transaction() as sess:
        assert sess["delete_account_csrf_token"]


def test_profile_links_to_delete_account(client, user):
    login(client, user)

    response = client.get("/profile/")

    assert b'href="/delete-account"' in response.data


def test_delete_account_rejects_invalid_csrf(client, user):
    login_with_delete_csrf(client, user)

    response = post_delete_account(client, csrf_token="wrong-token")

    assert response.status_code == 200
    assert b"Your form has expired" in response.data
    assert db.session.get(User, user.id) is not None


def test_delete_account_requires_password(client, user):
    login_with_delete_csrf(client, user)

    response = post_delete_account(client, password="")

    assert response.status_code == 200
    assert b"Current password is required." in response.data
    assert db.session.get(User, user.id) is not None


def test_delete_account_rejects_wrong_password(client, user):
    login_with_delete_csrf(client, user)

    response = post_delete_account(client, password="WrongPass123!")

    assert response.status_code == 200
    assert b"Invalid current password." in response.data
    assert db.session.get(User, user.id) is not None


def test_delete_account_rolls_back_on_database_error(client, user, other_user):
    board = Dashboard(name="Theirs", owner_id=other_user.id, is_default=False)
    db.session.add(board)
    db.session.commit()
    add_member(board, user)
    note = add_note(board, user, "Mine on theirs")
    login_with_delete_csrf(client, user)

    with patch.object(db.session, "commit", side_effect=SQLAlchemyError("db down")):
        response = post_delete_account(client)

    db.session.expire_all()
    kept = db.session.get(Note, note.id)
    assert response.status_code == 200
    assert b"Unable to delete your account" in response.data
    assert db.session.get(User, user.id) is not None
    assert kept.owner_id == user.id
    assert kept.owner_deleted_at is None
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(user.id)


def test_delete_account_logs_out_and_frees_username_and_email(client, user):
    user_id, username, email = user.id, user.username, user.email
    login_with_delete_csrf(client, user)

    response = post_delete_account(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert db.session.get(User, user_id) is None
    with client.session_transaction() as sess:
        assert "_user_id" not in sess
        assert "delete_account_csrf_token" not in sess

    csrf_token = register_csrf(client)
    client.post(
        "/register",
        data={
            "csrf_token": csrf_token,
            "username": username,
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert db.session.scalar(db.select(User).where(User.email == email)) is not None


def test_delete_account_removes_owned_content_and_keeps_notes_on_others_dashboards(
    client, user, other_user, default_dashboard, dashboard
):
    own_note = add_note(dashboard, user, "Own")
    collaborator_note = add_note(dashboard, other_user, "Collaborator on mine")
    home_note = add_note(default_dashboard, user, "Home")
    invite_to_mine = add_member(dashboard, other_user)

    theirs = Dashboard(name="Theirs", owner_id=other_user.id, is_default=False)
    db.session.add(theirs)
    db.session.commit()
    membership = add_member(theirs, user)
    note_on_theirs = add_note(theirs, user, "Mine on theirs")
    owner_note_on_theirs = add_note(theirs, other_user, "Theirs on theirs")

    ids = {
        "own_note": own_note.id,
        "collaborator_note": collaborator_note.id,
        "home_note": home_note.id,
        "invite_to_mine": invite_to_mine.id,
        "membership": membership.id,
        "dashboard": dashboard.id,
        "default_dashboard": default_dashboard.id,
        "user": user.id,
    }
    login_with_delete_csrf(client, user)

    response = post_delete_account(client)

    db.session.expire_all()
    assert response.status_code == 302
    assert db.session.get(User, ids["user"]) is None
    assert db.session.get(Dashboard, ids["dashboard"]) is None
    assert db.session.get(Dashboard, ids["default_dashboard"]) is None
    for key in ("own_note", "collaborator_note", "home_note"):
        assert db.session.get(Note, ids[key]) is None
    assert db.session.get(Invite, ids["invite_to_mine"]) is None
    assert db.session.get(Invite, ids["membership"]) is None

    kept = db.session.get(Note, note_on_theirs.id)
    assert kept.dashboard_id == theirs.id
    assert kept.owner_id is None
    assert kept.owner_deleted_at is not None
    assert db.session.get(Dashboard, theirs.id) is not None
    owner_note = db.session.get(Note, owner_note_on_theirs.id)
    assert owner_note.owner_id == other_user.id
    assert owner_note.owner_deleted_at is None
    assert can_manage_note(kept, theirs, other_user)
