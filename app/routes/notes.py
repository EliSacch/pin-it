import hmac
import html
import secrets
import json
import re

from flask import Blueprint, flash, jsonify, redirect, request, session, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.helpers.dashboard_access import can_manage_note, get_member_dashboard_or_404
from app.models import Note

notes_bp = Blueprint("notes", __name__, url_prefix="/dashboards/<int:dashboard_id>/notes")
_NOTE_FORM_ERRORS_KEY = "note_form_errors"
_NOTE_FORM_VALUES_KEY = "note_form_values"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MAX_CONTENT_CHARS = 1000


def _notes_csrf_token():
    csrf_token = session.get("notes_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["notes_csrf_token"] = csrf_token
    return csrf_token

def _has_valid_notes_csrf_token():
    submitted_token = request.form.get("csrf_token", "")
    stored_token = session.get("notes_csrf_token", "")
    return (
        isinstance(submitted_token, str)
        and isinstance(stored_token, str)
        and hmac.compare_digest(submitted_token, stored_token)
    )


def _dashboard_url(dashboard):
    return url_for(
        "dashboards.get",
        dashboard_id=dashboard.id,
        slug=dashboard.slug,
    )


def _redirect_to_dashboard(dashboard):
    return redirect(_dashboard_url(dashboard))


def _redirect_to_dashboard_with_errors(dashboard, form_key, errors, values=None):
    form_key = str(form_key)
    session[_NOTE_FORM_ERRORS_KEY] = {form_key: errors}
    if values is not None:
        session[_NOTE_FORM_VALUES_KEY] = {form_key: values}
    return _redirect_to_dashboard(dashboard)


def _submitted_note_values(blocks):
    return {
        "title": request.form.get("title", ""),
        "content": json.dumps(blocks or []),
    }


def _strip_html(value):
    """Return plain text; output paths must escape it before rendering as HTML."""
    if not isinstance(value, str):
        return ""
    text = _HTML_TAG_RE.sub("", value)
    return html.unescape(text).replace("\xa0", " ").strip()


def _flatten_checklist_items(items):
    flattened = []
    if not isinstance(items, list):
        return flattened
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _strip_html(item.get("content") or item.get("text") or "")
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        checked = bool(meta.get("checked", item.get("checked", False)))
        flattened.append(
            {
                "type": "todo",
                "text": text,
                "isChecked": checked,
            }
        )
        flattened.extend(_flatten_checklist_items(item.get("items") or []))
    return flattened


def _editor_data_to_content_blocks(raw_content):
    """Map Editor.js save() JSON to storage blocks. Returns (blocks, error_message)."""
    if not raw_content or not str(raw_content).strip():
        return [], None

    try:
        payload = json.loads(raw_content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "Invalid note content."

    if isinstance(payload, dict):
        editor_blocks = payload.get("blocks", [])
    elif isinstance(payload, list):
        editor_blocks = payload
    else:
        return None, "Invalid note content."

    if not isinstance(editor_blocks, list):
        return None, "Invalid note content."

    blocks = []
    for editor_block in editor_blocks:
        if not isinstance(editor_block, dict):
            continue
        block_type = editor_block.get("type")
        data = editor_block.get("data") if isinstance(editor_block.get("data"), dict) else {}

        if block_type == "paragraph":
            text = _strip_html(data.get("text", ""))
            blocks.append({"type": "paragraph", "text": text})
        elif block_type == "list" and data.get("style") == "checklist":
            blocks.extend(_flatten_checklist_items(data.get("items") or []))
        elif block_type == "checklist":
            # Legacy @editorjs/checklist shape
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                blocks.append(
                    {
                        "type": "todo",
                        "text": _strip_html(item.get("text", "")),
                        "isChecked": bool(item.get("checked", False)),
                    }
                )

    return blocks, None


def _content_blocks_plain_text_length(blocks):
    total = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        total += len(block.get("text") or "")
    return total


def _can_manage(note, dashboard):
    return (
        note is not None
        and note.dashboard_id == dashboard.id
        and can_manage_note(note, dashboard, current_user)
    )


@notes_bp.route("/create", methods=["GET", "POST"])
@login_required
def create(dashboard_id):
    dashboard = get_member_dashboard_or_404(dashboard_id)
    if request.method == "POST":
        if not _has_valid_notes_csrf_token():
            return _redirect_to_dashboard_with_errors(
                dashboard, "create", ["Invalid form submission."]
            )

        errors = []
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        if len(title) > 50:
            errors.append("Title must be less than 50 characters.")

        blocks, content_error = _editor_data_to_content_blocks(content)
        if content_error:
            errors.append(content_error)
        elif blocks is not None and _content_blocks_plain_text_length(blocks) > _MAX_CONTENT_CHARS:
            errors.append("Content must be less than 1000 characters.")

        if errors:
            return _redirect_to_dashboard_with_errors(
                dashboard,
                "create",
                errors,
                _submitted_note_values(blocks),
            )

        new_note = Note(
            title=title,
            content_json=json.dumps(blocks),
            owner_id=current_user.id,
            dashboard_id=dashboard.id,
        )
        db.session.add(new_note)
        try:
            db.session.commit()
            session.pop("notes_csrf_token", None)
        except SQLAlchemyError:
            db.session.rollback()
            return _redirect_to_dashboard_with_errors(
                dashboard,
                "create",
                ["There was an error submitting this request. Please try again."],
                _submitted_note_values(blocks),
            )
        return _redirect_to_dashboard(dashboard)
    return _redirect_to_dashboard(dashboard)


@notes_bp.route("/<int:note_id>/update", methods=["GET", "POST"])
@login_required
def update(dashboard_id, note_id):
    dashboard = get_member_dashboard_or_404(dashboard_id)
    note = db.session.get(Note, note_id)
    if not _can_manage(note, dashboard):
        flash("You are not authorized to edit this note.", "error")
        return _redirect_to_dashboard(dashboard)
    if request.method == "POST":
        if not _has_valid_notes_csrf_token():
            return _redirect_to_dashboard_with_errors(
                dashboard, note.id, ["Invalid form submission."]
            )

        errors = []
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        if len(title) > 50:
            errors.append("Title must be less than 50 characters.")

        blocks, content_error = _editor_data_to_content_blocks(content)
        if content_error:
            errors.append(content_error)
        elif blocks is not None and _content_blocks_plain_text_length(blocks) > _MAX_CONTENT_CHARS:
            errors.append("Content must be less than 1000 characters.")

        if errors:
            return _redirect_to_dashboard_with_errors(
                dashboard,
                note.id,
                errors,
                _submitted_note_values(blocks),
            )
        note.title = title
        note.content_json = json.dumps(blocks)
        try:
            db.session.commit()
            session.pop("notes_csrf_token", None)
            return _redirect_to_dashboard(dashboard)
        except SQLAlchemyError:
            db.session.rollback()
            return _redirect_to_dashboard_with_errors(
                dashboard,
                note.id,
                ["There was an error submitting this request. Please try again."],
                _submitted_note_values(blocks),
            )
    return _redirect_to_dashboard(dashboard)


def _wants_json():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best_match(["application/json", "text/html"])
        == "application/json"
    )


@notes_bp.route("/<int:note_id>/todos/<int:block_index>/toggle", methods=["POST"])
@login_required
def toggle_todo(dashboard_id, note_id, block_index):
    dashboard = get_member_dashboard_or_404(dashboard_id)
    note = db.session.get(Note, note_id)
    if not _can_manage(note, dashboard):
        if _wants_json():
            return jsonify({"ok": False, "errors": {"form": ["You are not authorized to update this note."]}}), 403
        flash("You are not authorized to update this note.", "error")
        return _redirect_to_dashboard(dashboard)

    if not _has_valid_notes_csrf_token():
        if _wants_json():
            return jsonify({"ok": False, "errors": {"form": ["Invalid form submission."]}}), 400
        flash("Invalid form submission.", "error")
        return _redirect_to_dashboard(dashboard)

    blocks = list(note.content_blocks)
    if block_index < 0 or block_index >= len(blocks):
        if _wants_json():
            return jsonify({"ok": False, "errors": {"form": ["Todo item not found."]}}), 404
        flash("Todo item not found.", "error")
        return _redirect_to_dashboard(dashboard)

    block = blocks[block_index]
    if not isinstance(block, dict) or block.get("type") != "todo":
        if _wants_json():
            return jsonify({"ok": False, "errors": {"form": ["Not a todo item."]}}), 400
        flash("Not a todo item.", "error")
        return _redirect_to_dashboard(dashboard)

    block = dict(block)
    block["isChecked"] = not bool(block.get("isChecked", False))
    blocks[block_index] = block
    note.content_json = json.dumps(blocks)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        if _wants_json():
            return jsonify(
                {
                    "ok": False,
                    "errors": {
                        "form": ["There was an error submitting this request. Please try again."]
                    },
                }
            ), 500
        flash("There was an error submitting this request. Please try again.", "error")
        return _redirect_to_dashboard(dashboard)

    if _wants_json():
        return jsonify({"ok": True, "isChecked": block["isChecked"], "block_index": block_index})
    return _redirect_to_dashboard(dashboard)


@notes_bp.route("/<int:note_id>/delete", methods=["GET", "POST"])
@login_required
def delete(dashboard_id, note_id):
    dashboard = get_member_dashboard_or_404(dashboard_id)
    note = db.session.get(Note, note_id)
    if not _can_manage(note, dashboard):
        flash("You are not authorized to delete this note.", "error")
        if _wants_json():
            return jsonify({
                "ok": False,
                "retryable": False,
                "errors": {"form": ["You are not authorized to delete this note."]},
            }), 403
        return _redirect_to_dashboard(dashboard)
    if request.method == "POST":
        if not _has_valid_notes_csrf_token():
            flash("Invalid form submission.", "error")
            if _wants_json():
                return jsonify({"ok": False, "errors": {"form": ["Invalid form submission."]}}), 400
            return _redirect_to_dashboard(dashboard)

        db.session.delete(note)
        try:
            db.session.commit()
            session.pop("notes_csrf_token", None)
        except SQLAlchemyError:
            db.session.rollback()
            flash("There was an error submitting this request. Please try again.", "error")
            if _wants_json():
                return jsonify(
                    {
                        "ok": False,
                        "errors": {
                            "form": ["There was an error submitting this request. Please try again."]
                        },
                    }
                ), 500
            return _redirect_to_dashboard(dashboard)

        redirect_url = _dashboard_url(dashboard)
        if _wants_json():
            return jsonify({"ok": True, "redirect_url": redirect_url})
        return redirect(redirect_url)
    return _redirect_to_dashboard(dashboard)
