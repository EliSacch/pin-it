import hmac
import secrets

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.helpers.invites import (
    collect_invite_email_errors,
    create_invites,
    normalized_invite_emails,
    submitted_invite_emails,
)
from app.models import Dashboard, Note

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/dashboards")
_DASHBOARD_FORM_ERRORS_KEY = "dashboard_form_errors"
_DASHBOARD_FORM_VALUES_KEY = "dashboard_form_values"


def _dashboards_csrf_token():
    csrf_token = session.get("dashboards_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["dashboards_csrf_token"] = csrf_token
    return csrf_token


def _has_valid_dashboards_csrf_token():
    submitted_token = request.form.get("csrf_token", "")
    stored_token = session.get("dashboards_csrf_token", "")
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


def _redirect_with_form_errors(form_key, errors, values=None, redirect_url=None):
    form_key = str(form_key)
    session[_DASHBOARD_FORM_ERRORS_KEY] = {form_key: errors}
    if values is not None:
        session[_DASHBOARD_FORM_VALUES_KEY] = {form_key: values}
    return redirect(redirect_url or url_for("main.index"))


def _submitted_dashboard_values():
    """
    Returns the values submitted for a dashboard creation or update form.
    Used to return errors and values to the form after a submission error.
    """
    return {
        "name": request.form.get("name", ""),
        "invite_emails": submitted_invite_emails(request.form),
    }


def _apply_invite_email_errors(errors, values):
    invite_errors = collect_invite_email_errors(
        values.get("invite_emails"),
        owner_email=current_user.email,
    )
    if invite_errors:
        errors.setdefault("invite_emails", []).extend(invite_errors)
    return normalized_invite_emails(values.get("invite_emails"))


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


def dashboard_view_context(dashboard):
    from app.routes.notes import (
        _NOTE_FORM_ERRORS_KEY,
        _NOTE_FORM_VALUES_KEY,
        _notes_csrf_token,
    )

    dashboards = [
        item.to_dict()
        for item in db.session.scalars(
            db.select(Dashboard)
            .where(Dashboard.owner_id == current_user.id)
            .order_by(Dashboard.created_at.asc())
        )
    ]

    if dashboard is None:
        notes = []
    else:
        notes = [
            note.to_dict()
            for note in db.session.scalars(
                db.select(Note)
                .where(Note.dashboard_id == dashboard.id)
                .order_by(Note.created_at.asc())
            )
        ]

    return {
        "page_title": dashboard.name if dashboard else "Home",
        "dashboards": dashboards,
        "dashboard": dashboard.to_dict() if dashboard else None,
        "notes": notes,
        "csrf_token": _notes_csrf_token(),
        "dashboards_csrf_token": _dashboards_csrf_token(),
        "errors": session.pop(_NOTE_FORM_ERRORS_KEY, {}),
        "form_values": session.pop(_NOTE_FORM_VALUES_KEY, {}),
        "dashboard_errors": session.pop(_DASHBOARD_FORM_ERRORS_KEY, {}),
        "dashboard_form_values": session.pop(_DASHBOARD_FORM_VALUES_KEY, {}),
    }


@dashboards_bp.route("/<int:dashboard_id>/<slug>")
@login_required
def get(dashboard_id, slug):
    dashboard = db.session.get(Dashboard, dashboard_id)
    notes = db.session.scalars(
        db.select(Note)
        .where(Note.dashboard_id == dashboard_id)
        .order_by(Note.created_at.asc())
    )

    if not dashboard or dashboard.owner_id != current_user.id:
        abort(404)
    if dashboard.slug != slug:
        return redirect(
            url_for(
                "dashboards.get",
                dashboard_id=dashboard.id,
                slug=dashboard.slug,
                notes=notes,
            )
        )
    return render_template("index.html", **dashboard_view_context(dashboard))


@dashboards_bp.route("/list")
@login_required
def list():
    dashboards = db.session.scalars(
        db.select(Dashboard)
        .where(Dashboard.owner_id == current_user.id)
        .order_by(Dashboard.created_at.asc())
    )
    return jsonify([dashboard.to_dict() for dashboard in dashboards])


@dashboards_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        errors = {}
        values = _submitted_dashboard_values()
        name = values.get("name", "").strip()

        if not _has_valid_dashboards_csrf_token():
            errors.setdefault("form", []).append("Invalid form submission.")
        if not name:
            errors.setdefault("name", []).append("Name is required.")
        elif len(name) > 50:
            errors.setdefault("name", []).append("Name must be less than 50 characters.")
        invite_emails = _apply_invite_email_errors(errors, values)
        if errors:
            return _create_error_response(errors, values)

        new_dashboard = Dashboard(
            name=name,
            owner_id=current_user.id,
            is_default=False,
        )
        db.session.add(new_dashboard)
        create_invites(new_dashboard, invite_emails)
        try:
            db.session.commit()
            session.pop("dashboards_csrf_token", None)
        except IntegrityError:
            db.session.rollback()
            return _create_error_response(
                {"name": ["You already have a dashboard with this name."]},
                values,
            )
        except SQLAlchemyError:
            db.session.rollback()
            return _create_error_response(
                {"form": ["There was an error submitting this request. Please try again."]},
                values,
            )

        flash("Dashboard created successfully.", "success")
        redirect_url = url_for(
            "dashboards.get",
            dashboard_id=new_dashboard.id,
            slug=new_dashboard.slug,
        )
        if _wants_json():
            return jsonify({"ok": True, "redirect_url": redirect_url})
        return redirect(redirect_url)
    return redirect(url_for("main.index"))


@dashboards_bp.route("/<int:dashboard_id>/update", methods=["GET", "POST"])
@login_required
def update(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.owner_id != current_user.id:
        abort(404)
    if request.method != "POST":
        return redirect(_dashboard_url(dashboard))

    errors = {}
    values = _submitted_dashboard_values()
    name = values.get("name", "").strip()
    error_redirect = _dashboard_url(dashboard)

    if dashboard.is_default:
        return _create_error_response(
            {"form": ["You cannot rename the default dashboard."]},
            values,
            form_key="update",
            retryable=False,
            redirect_url=error_redirect,
        )
    if not _has_valid_dashboards_csrf_token():
        errors.setdefault("form", []).append("Invalid form submission.")
    if not name:
        errors.setdefault("name", []).append("Name is required.")
    elif len(name) > 50:
        errors.setdefault("name", []).append("Name must be less than 50 characters.")
    invite_emails = _apply_invite_email_errors(errors, values)
    if errors:
        return _create_error_response(
            errors,
            values,
            form_key="update",
            redirect_url=error_redirect,
        )

    dashboard.name = name
    create_invites(dashboard, invite_emails)
    try:
        db.session.commit()
        session.pop("dashboards_csrf_token", None)
    except IntegrityError:
        db.session.rollback()
        return _create_error_response(
            {"name": ["You already have a dashboard with this name."]},
            values,
            form_key="update",
            redirect_url=error_redirect,
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _create_error_response(
            {"form": ["There was an error submitting this request. Please try again."]},
            values,
            form_key="update",
            redirect_url=error_redirect,
        )

    flash("Dashboard updated successfully.", "success")
    redirect_url = _dashboard_url(dashboard)
    if _wants_json():
        return jsonify({"ok": True, "redirect_url": redirect_url})
    return redirect(redirect_url)


@dashboards_bp.route("/<int:dashboard_id>/delete", methods=["GET", "POST"])
@login_required
def delete(dashboard_id):
    errors = {}
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.owner_id != current_user.id:
        errors.setdefault("form", []).append("You are not authorized to delete this dashboard.")
        return _create_error_response(errors, form_key="delete", retryable=False)
    if dashboard.is_default:
        errors.setdefault("form", []).append("You cannot delete the default dashboard.")
        return _create_error_response(errors, form_key="delete", retryable=False)
    if request.method != "POST":
        return redirect(url_for("main.index"))
    if not _has_valid_dashboards_csrf_token():
        errors.setdefault("form", []).append("Invalid form submission.")
        return _create_error_response(errors, form_key="delete")

    db.session.delete(dashboard)
    try:
        db.session.commit()
        session.pop("dashboards_csrf_token", None)
    except SQLAlchemyError:
        db.session.rollback()
        errors.setdefault("form", []).append("There was an error submitting this request. Please try again.")
        return _create_error_response(errors, form_key="delete")

    redirect_url = url_for("main.index")
    if _wants_json():
        return jsonify({"ok": True, "redirect_url": redirect_url})
    return redirect(redirect_url)
