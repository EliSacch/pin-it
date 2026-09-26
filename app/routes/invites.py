import hmac
import secrets

from flask import Blueprint, abort, flash, jsonify, redirect, request, session, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.helpers.invites import (
    collect_invite_email_errors,
    create_invites,
    normalized_invite_emails,
    prepare_invite_resend,
    revoke_invite,
    send_invite_emails,
    submitted_invite_emails,
)
from app.models import Dashboard, Invite

invites_bp = Blueprint("invites", __name__, url_prefix="/dashboards/<int:dashboard_id>/invites")
_INVITE_FORM_ERRORS_KEY = "invite_form_errors"
_INVITE_FORM_VALUES_KEY = "invite_form_values"


def _invites_csrf_token():
    csrf_token = session.get("invites_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["invites_csrf_token"] = csrf_token
    return csrf_token


def _has_valid_invites_csrf_token():
    submitted_token = request.form.get("csrf_token", "")
    stored_token = session.get("invites_csrf_token", "")
    return (
        isinstance(submitted_token, str)
        and isinstance(stored_token, str)
        and hmac.compare_digest(submitted_token, stored_token)
    )


def _wants_json():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best_match(["application/json", "text/html"])
        == "application/json"
    )


def _settings_url(dashboard):
    return url_for(
        "dashboards.settings",
        dashboard_id=dashboard.id,
        slug=dashboard.slug,
    )


def _submitted_invite_values():
    return {
        "invite_emails": submitted_invite_emails(request.form),
    }


def _redirect_with_form_errors(form_key, errors, values=None, redirect_url=None):
    form_key = str(form_key)
    session[_INVITE_FORM_ERRORS_KEY] = {form_key: errors}
    if values is not None:
        session[_INVITE_FORM_VALUES_KEY] = {form_key: values}
    return redirect(redirect_url or url_for("main.index"))


def _create_error_response(
    errors,
    values=None,
    form_key="create",
    retryable=True,
    redirect_url=None,
):
    if _wants_json():
        return jsonify({
            "ok": False,
            "errors": errors,
            "values": values or {},
            "retryable": retryable,
        }), 400
    return _redirect_with_form_errors(form_key, errors, values, redirect_url)


def _owned_dashboard_or_abort(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.owner_id != current_user.id:
        abort(404)
    if dashboard.is_default:
        abort(403)
    return dashboard


def _live_invite_or_404(dashboard, invite_id):
    invite = db.session.get(Invite, invite_id)
    if (
        invite is None
        or invite.dashboard_id != dashboard.id
        or invite.deleted_at is not None
    ):
        abort(404)
    return invite


@invites_bp.route("/create", methods=["GET", "POST"])
@login_required
def create(dashboard_id):
    dashboard = _owned_dashboard_or_abort(dashboard_id)

    settings_url = _settings_url(dashboard)
    if request.method != "POST":
        return redirect(settings_url)

    errors = {}
    values = _submitted_invite_values()
    emails = normalized_invite_emails(values["invite_emails"])

    if not _has_valid_invites_csrf_token():
        errors.setdefault("form", []).append("Invalid form submission.")
    if not emails:
        errors.setdefault("invite_emails", []).append("Add at least one email address.")
    else:
        email_errors = collect_invite_email_errors(
            values["invite_emails"],
            owner_email=current_user.email,
        )
        if email_errors:
            errors.setdefault("invite_emails", []).extend(email_errors)
    if errors:
        return _create_error_response(
            errors,
            values,
            redirect_url=settings_url,
        )

    created = create_invites(dashboard, emails)
    try:
        db.session.commit()
        session.pop("invites_csrf_token", None)
    except SQLAlchemyError:
        db.session.rollback()
        return _create_error_response(
            {"form": ["There was an error submitting this request. Please try again."]},
            values,
            redirect_url=settings_url,
        )

    failed = send_invite_emails(created)
    if failed:
        flash(
            "Collaborators added, but we could not email: "
            + ", ".join(invite.email for invite in failed)
            + ".",
            "warning",
        )
    elif created:
        flash("Collaborators added.", "success")
    else:
        flash("Those collaborators are already invited.", "info")
    if _wants_json():
        return jsonify({"ok": True, "redirect_url": settings_url})
    return redirect(settings_url)


@invites_bp.route("/<int:invite_id>/revoke", methods=["POST"])
@login_required
def revoke(dashboard_id, invite_id):
    dashboard = _owned_dashboard_or_abort(dashboard_id)
    invite = _live_invite_or_404(dashboard, invite_id)
    settings_url = _settings_url(dashboard)

    if not _has_valid_invites_csrf_token():
        return _create_error_response(
            {"form": ["Invalid form submission."]},
            form_key="revoke",
            redirect_url=settings_url,
        )

    revoke_invite(invite)
    try:
        db.session.commit()
        session.pop("invites_csrf_token", None)
    except SQLAlchemyError:
        db.session.rollback()
        return _create_error_response(
            {"form": ["There was an error submitting this request. Please try again."]},
            form_key="revoke",
            redirect_url=settings_url,
        )

    flash("Access revoked.", "success")
    if _wants_json():
        return jsonify({"ok": True, "redirect_url": settings_url})
    return redirect(settings_url)


@invites_bp.route("/<int:invite_id>/resend", methods=["POST"])
@login_required
def resend(dashboard_id, invite_id):
    dashboard = _owned_dashboard_or_abort(dashboard_id)
    invite = _live_invite_or_404(dashboard, invite_id)
    if invite.status not in ("pending", "rejected"):
        abort(404)
    settings_url = _settings_url(dashboard)

    if not _has_valid_invites_csrf_token():
        flash("Your form has expired. Please try again.", "warning")
        return redirect(settings_url)

    prepare_invite_resend(invite)
    try:
        db.session.commit()
        session.pop("invites_csrf_token", None)
    except SQLAlchemyError:
        db.session.rollback()
        flash("There was an error submitting this request. Please try again.", "warning")
        return redirect(settings_url)

    if send_invite_emails([invite]):
        flash(f"We could not email {invite.email}. Please try again.", "warning")
    else:
        flash(f"Invitation sent again to {invite.email}.", "success")
    return redirect(settings_url)
