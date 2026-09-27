import json

from app.extensions import db
from app.models import Note
from tests.conftest import CSRF_TOKEN, login

IMG_PAYLOAD = "<img src=x onerror=alert(1)>"


def editor_content(text):
    return json.dumps({"blocks": [{"type": "paragraph", "data": {"text": text}}]})


def login_with_notes_token(client, user):
    login(client, user)
    with client.session_transaction() as session:
        session["notes_csrf_token"] = CSRF_TOKEN


def create_note(client, dashboard, title, content, csrf_token=CSRF_TOKEN):
    return client.post(
        f"/dashboards/{dashboard.id}/notes/create",
        data={"title": title, "content": content, "csrf_token": csrf_token},
    )


def dashboard_page(client, dashboard):
    return client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}").get_data(as_text=True)


def test_error_path_echoes_sanitized_storage_blocks(client, user, dashboard):
    login_with_notes_token(client, user)

    create_note(client, dashboard, "x" * 60, editor_content(IMG_PAYLOAD))

    with client.session_transaction() as session:
        echoed = session["note_form_values"]["create"]["content"]
    assert json.loads(echoed) == [{"type": "paragraph", "text": ""}]
    assert "onerror" not in echoed


def test_error_path_with_invalid_json_echoes_empty_blocks(client, user, dashboard):
    login_with_notes_token(client, user)

    create_note(client, dashboard, "x" * 60, "not json" + IMG_PAYLOAD)

    with client.session_transaction() as session:
        echoed = session["note_form_values"]["create"]["content"]
    assert json.loads(echoed) == []


def test_escaped_markup_is_stored_as_plain_text_and_rendered_escaped_once(
    client, user, dashboard
):
    login_with_notes_token(client, user)

    create_note(client, dashboard, "Markup", editor_content("&lt;b&gt;hi&lt;/b&gt; &amp; more"))

    note = db.session.scalar(db.select(Note).where(Note.title == "Markup"))
    assert note.content_blocks == [{"type": "paragraph", "text": "<b>hi</b> & more"}]

    page = dashboard_page(client, dashboard)
    assert "&lt;b&gt;hi&lt;/b&gt; &amp; more" in page
    assert "&amp;lt;b" not in page
    assert "<b>hi</b>" not in page


def test_invalid_csrf_does_not_persist_submitted_values(client, user, dashboard):
    login_with_notes_token(client, user)

    create_note(client, dashboard, "Title", editor_content(IMG_PAYLOAD), csrf_token="wrong")

    with client.session_transaction() as session:
        assert session["note_form_errors"] == {"create": ["Invalid form submission."]}
        assert "note_form_values" not in session
    assert db.session.scalar(db.select(Note)) is None


def test_unterminated_tag_is_never_rendered_as_markup(client, user, dashboard):
    login_with_notes_token(client, user)
    payload = "<img src=x onerror=alert(1)"

    create_note(client, dashboard, "Unterminated", editor_content(payload))

    note = db.session.scalar(db.select(Note).where(Note.title == "Unterminated"))
    assert note.content_blocks == [{"type": "paragraph", "text": payload}]

    page = dashboard_page(client, dashboard)
    assert payload not in page
    assert "&lt;img src=x onerror=alert(1)" in page


def test_responses_carry_csp_without_inline_scripts(client, user, dashboard):
    login(client, user)

    response = client.get(f"/dashboards/{dashboard.id}/{dashboard.slug}")

    policy = response.headers["Content-Security-Policy"]
    script_src = next(d for d in policy.split("; ") if d.startswith("script-src "))
    assert "'unsafe-inline'" not in script_src
    assert "script-src-attr 'none'" in policy
    assert response.headers["X-Content-Type-Options"] == "nosniff"
