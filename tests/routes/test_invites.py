from app.extensions import db
from app.models import Dashboard,Invite
from tests.conftest import CSRF_TOKEN, login

JSON_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

def create_invite_path(dashboard):
    return f"/dashboards/{dashboard.id}/invites/create"


def test_create_invite_requires_login(client, dashboard):
    response = client.post(
        create_invite_path(dashboard),
        data={"email": "test@example.com", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert not db.session.query(Invite).filter_by(dashboard_id=dashboard.id).all()


def test_create_invite_returns_404_for_missing_dashboard(client, user, dashboard):
    login(client, user)

    response = client.post(
        "/dashboards/999/invites/create",
        data={"email": "test@example.com", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404

def test_create_invite_returns_404_for_another_users_dashboard(
    client, user, other_user):
    other_user_dashboard = Dashboard(
        name="Secret", owner_id=other_user.id, is_default=False
    )
    db.session.add(other_user_dashboard)
    db.session.commit()
    login(client, user)

    response = client.post(
        create_invite_path(other_user_dashboard),
        data={"email": "test@example.com", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404
    assert not db.session.query(Invite).filter_by(dashboard_id=other_user_dashboard.id).all()

def test_create_invite_returns_403_for_default_dashboard(
    client, user, default_dashboard):
    login(client, user)

    response = client.post(
        create_invite_path(default_dashboard),
        data={"email": "test@example.com", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 403
    assert not db.session.query(Invite).filter_by(dashboard_id=default_dashboard.id).all()

def test_create_invite_rejects_invalid_csrf(client, user, dashboard):
    login(client, user)

    response = client.post(
        create_invite_path(dashboard),
        data={"email": "test@example.com", "csrf_token": "wrong-token"},
    )

    assert response.status_code == 302
    assert not db.session.query(Invite).filter_by(dashboard_id=dashboard.id).all()
    with client.session_transaction() as session:
        errors = session["invite_form_errors"]["create"]
        assert errors["form"] == ["Invalid form submission."]