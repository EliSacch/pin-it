import json

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Invite, Note, User
from tests.conftest import CSRF_TOKEN, login

TODO_CONTENT = json.dumps(
    {"blocks": [{"type": "checklist", "data": {"items": [{"text": "Do it", "checked": False}]}}]}
)


@pytest.fixture()
def member(other_user, dashboard):
    db.session.add(
        Invite(
            dashboard_id=dashboard.id,
            email=other_user.email,
            user_id=other_user.id,
            status="accepted",
        )
    )
    db.session.commit()
    return other_user


@pytest.fixture()
def second_member(dashboard):
    person = User(
        username="third",
        email="third@example.com",
        password_hash=generate_password_hash("ValidPass123!"),
    )
    db.session.add(person)
    db.session.commit()
    db.session.add(
        Invite(dashboard_id=dashboard.id, email=person.email, user_id=person.id, status="accepted")
    )
    db.session.commit()
    return person


def make_note(dashboard, author, title="Note"):
    note = Note(
        title=title,
        owner_id=author.id,
        dashboard_id=dashboard.id,
        content_json=json.dumps([{"type": "todo", "text": "Do it", "isChecked": False}]),
    )
    db.session.add(note)
    db.session.commit()
    return note


def login_with_notes_token(client, user):
    login(client, user)
    with client.session_transaction() as session:
        session["notes_csrf_token"] = CSRF_TOKEN


def notes_path(dashboard, suffix=""):
    return f"/dashboards/{dashboard.id}/notes{suffix}"


def seed_notes_token(client):
    with client.session_transaction() as session:
        session["notes_csrf_token"] = CSRF_TOKEN


def update_note(client, dashboard, note, title):
    seed_notes_token(client)
    return client.post(
        notes_path(dashboard, f"/{note.id}/update"),
        data={"title": title, "content": TODO_CONTENT, "csrf_token": CSRF_TOKEN},
    )


def toggle_note(client, dashboard, note):
    seed_notes_token(client)
    return client.post(
        notes_path(dashboard, f"/{note.id}/todos/0/toggle"),
        data={"csrf_token": CSRF_TOKEN},
    )


def delete_note(client, dashboard, note):
    seed_notes_token(client)
    return client.post(
        notes_path(dashboard, f"/{note.id}/delete"),
        data={"csrf_token": CSRF_TOKEN},
    )


def test_non_member_cannot_create_note(client, other_user, dashboard):
    login_with_notes_token(client, other_user)

    response = client.post(
        notes_path(dashboard, "/create"),
        data={"title": "Nope", "content": "", "csrf_token": CSRF_TOKEN},
    )

    assert response.status_code == 404


def test_member_can_create_note(client, member, dashboard):
    login_with_notes_token(client, member)

    client.post(
        notes_path(dashboard, "/create"),
        data={"title": "Hello", "content": TODO_CONTENT, "csrf_token": CSRF_TOKEN},
    )

    note = db.session.scalar(db.select(Note).where(Note.title == "Hello"))
    assert note is not None
    assert note.owner_id == member.id
    assert note.dashboard_id == dashboard.id


def test_member_can_edit_toggle_and_delete_own_note(client, member, dashboard):
    note = make_note(dashboard, member)
    note_id = note.id
    login_with_notes_token(client, member)

    update_note(client, dashboard, note, "Edited")
    toggle_note(client, dashboard, note)
    db.session.refresh(note)
    assert note.title == "Edited"
    assert note.content_blocks[0]["isChecked"] is True

    delete_note(client, dashboard, note)
    db.session.expire_all()
    assert db.session.get(Note, note_id) is None


@pytest.mark.parametrize("author_fixture", ["user", "second_member"])
def test_member_cannot_manage_others_notes(
    request, client, member, dashboard, author_fixture
):
    author = request.getfixturevalue(author_fixture)
    note = make_note(dashboard, author, title="Theirs")
    login_with_notes_token(client, member)

    update_note(client, dashboard, note, "Hijacked")
    toggle_note(client, dashboard, note)
    delete_note(client, dashboard, note)

    db.session.expire_all()
    note = db.session.get(Note, note.id)
    assert note is not None
    assert note.title == "Theirs"
    assert note.content_blocks[0]["isChecked"] is False


def test_owner_can_manage_member_notes(client, user, member, dashboard):
    note = make_note(dashboard, member)
    note_id = note.id
    login_with_notes_token(client, user)

    update_note(client, dashboard, note, "By owner")
    toggle_note(client, dashboard, note)
    db.session.refresh(note)
    assert note.title == "By owner"
    assert note.content_blocks[0]["isChecked"] is True

    delete_note(client, dashboard, note)
    db.session.expire_all()
    assert db.session.get(Note, note_id) is None


def test_controls_hidden_for_notes_member_cannot_manage(client, user, member, dashboard):
    make_note(dashboard, user, title="Owner note")
    own = make_note(dashboard, member, title="Member note")
    login(client, member)

    html = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}").get_data(as_text=True)

    assert html.count('aria-label="Delete note"') == 1
    assert html.count('aria-label="Edit note"') == 1
    assert f"/notes/{own.id}/delete" in html
    assert html.count("data-toggle-url=") == 1
    assert "disabled" in html
