import hmac
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, login_manager
from app.helpers.invites import (
    EXPIRED_INVITE_MESSAGE,
    accept_invite,
    decline_invite,
    load_invite,
    load_invite_for_user,
)

invitations_bp = Blueprint("invitations", __name__, url_prefix="/invitations")


def _invitations_csrf_token():
    csrf_token = session.get("invitations_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["invitations_csrf_token"] = csrf_token
    return csrf_token


def _has_valid_invitations_csrf_token():
    submitted_token = request.form.get("csrf_token", "")
    stored_token = session.get("invitations_csrf_token", "")
    return (
        isinstance(submitted_token, str)
        and isinstance(stored_token, str)
        and hmac.compare_digest(submitted_token, stored_token)
    )


def _dashboard_url(dashboard):
    return url_for("dashboards.get", dashboard_id=dashboard.id, slug=dashboard.slug)


def _redirect_home(message, category="warning"):
    flash(message, category)
    return redirect(url_for("main.index"))


def _already_answered_redirect(invite):
    if invite.status == "accepted":
        return redirect(_dashboard_url(invite.dashboard))
    return _redirect_home("You already declined this invitation.", "info")


@invitations_bp.route("/<token>")
def show(token):
    _, error = load_invite(token)
    if error:
        status = 410 if error == EXPIRED_INVITE_MESSAGE else 404
        return render_template("invites/unavailable.html", message=error), status
    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    invite, error = load_invite_for_user(token, current_user)
    if error:
        return _redirect_home(error)
    if invite.status != "pending":
        return _already_answered_redirect(invite)

    return render_template(
        "invites/show.html",
        invite=invite,
        invite_dashboard=invite.dashboard,
        owner_username=invite.dashboard.owner.username,
        token=token,
        csrf_token=_invitations_csrf_token(),
    )


def _respond(token, action):
    """Returns (invite, None) when the action was saved, or (None, response)."""
    if not _has_valid_invitations_csrf_token():
        flash("Your form has expired. Please try again.", "warning")
        return None, redirect(url_for("invitations.show", token=token))

    invite, error = load_invite_for_user(token, current_user, max_age=None)
    if error:
        return None, _redirect_home(error)
    if invite.status != "pending":
        return None, _already_answered_redirect(invite)

    action(invite, current_user)
    try:
        db.session.commit()
        session.pop("invitations_csrf_token", None)
    except SQLAlchemyError:
        db.session.rollback()
        return None, _redirect_home(
            "There was an error submitting this request. Please try again."
        )
    return invite, None


@invitations_bp.route("/<token>/accept", methods=["POST"])
@login_required
def accept(token):
    invite, response = _respond(token, accept_invite)
    if response is not None:
        return response
    flash(f"You joined {invite.dashboard.name}.", "success")
    return redirect(_dashboard_url(invite.dashboard))


@invitations_bp.route("/<token>/decline", methods=["POST"])
@login_required
def decline(token):
    _, response = _respond(token, decline_invite)
    if response is not None:
        return response
    return _redirect_home("Invitation declined.", "info")
