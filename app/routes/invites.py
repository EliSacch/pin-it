import hmac
import secrets

from flask import Blueprint, abort, jsonify, redirect, request, session, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Dashboard

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


def _dashboard_url(dashboard):
    return url_for(
        "dashboards.get",
        dashboard_id=dashboard.id,
        slug=dashboard.slug,
    )


def _submitted_invite_values():
    return {
        "email": request.form.get("email", ""),
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


@invites_bp.route("/create", methods=["GET", "POST"])
@login_required
def create(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.owner_id != current_user.id:
        abort(404)
    if dashboard.is_default:
        abort(403)

    error_redirect = _dashboard_url(dashboard)
    if request.method != "POST":
        return redirect(error_redirect)

    errors = {}
    values = _submitted_invite_values()
    email = values.get("email", "").strip()

    if not _has_valid_invites_csrf_token():
        errors.setdefault("form", []).append("Invalid form submission.")
    if not email:
        errors.setdefault("email", []).append("Email is required.")
    if errors:
        return _create_error_response(
            errors,
            values,
            redirect_url=error_redirect,
        )

    return redirect(error_redirect)
