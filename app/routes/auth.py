import hmac
import secrets
import smtplib

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_user, login_required, current_user, logout_user
from flask_mailman import EmailMessage
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, login_manager, limiter
from app.helpers.account_deletion import delete_user_account
from app.helpers.email import collect_email_errors
from app.helpers.email_verification import generate_email_token, load_email_token
from app.helpers.invite_tokens import invite_token_from_next, invited_email_from_next
from app.helpers.invites import accept_invite, load_invite_for_user
from app.helpers.password import collect_password_errors
from app.helpers.redirects import submitted_redirect_target
from app.helpers.username import collect_username_errors
from app.models import Dashboard, User

auth_bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def _register_context(errors=None, username="", email=""):
    csrf_token = session.get("register_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["register_csrf_token"] = csrf_token

    next_url = submitted_redirect_target(request)
    invited_email = invited_email_from_next(next_url)

    return {
        "action": url_for("auth.register"),
        "csrf_token": csrf_token,
        "email": invited_email or email,
        "email_locked": invited_email is not None,
        "errors": errors or [],
        "next_url": next_url,
        "title": "Create your account",
        "username": username,
    }

def _login_context(errors=None, email=""):
    csrf_token = session.get("login_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["login_csrf_token"] = csrf_token

    next_url = submitted_redirect_target(request)

    return {
        "action": url_for("auth.login"),
        "csrf_token": csrf_token,
        "email": email or invited_email_from_next(next_url) or "",
        "errors": errors or [],
        "next_url": next_url,
        "title": "Login to your account",
    }

def _change_password_context(errors=None, current_password="", new_password="", confirm_password=""):
    csrf_token = session.get("change_password_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["change_password_csrf_token"] = csrf_token

    return {
        "action": url_for("auth.change_password"),
        "csrf_token": csrf_token,
        "current_password": current_password,
        "new_password": new_password,
        "confirm_password": confirm_password,
        "errors": errors or [],
        "title": "Change your password",
    }

def _delete_account_context(errors=None):
    csrf_token = session.get("delete_account_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["delete_account_csrf_token"] = csrf_token

    return {
        "action": url_for("auth.delete_account"),
        "csrf_token": csrf_token,
        "errors": errors or [],
        "title": "Delete your account",
    }

def send_verification_email(user):
    token = generate_email_token(user)
    confirm_url = url_for("auth.verify_email", token=token, _external=True)
    msg = EmailMessage(
        subject="Verify your PinIt email",
        body=f"Hi {user.username},\n\nConfirm your address:\n{confirm_url}\n",
        to=[user.email],
    )
    msg.send()


def resend_verification_csrf_token():
    csrf_token = session.get("resend_verification_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["resend_verification_csrf_token"] = csrf_token
    return csrf_token


def _auto_accept_invite(user, next_url):
    token = invite_token_from_next(next_url)
    if token is None:
        return None

    invite, error = load_invite_for_user(token, user)
    if error:
        flash(error, "warning")
        return redirect(url_for("main.index"))
    if invite.status != "pending":
        return None

    accept_invite(invite, user)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to auto-accept invite")
        return None

    flash(f"Welcome! You joined {invite.dashboard.name}.", "success")
    return redirect(
        url_for(
            "dashboards.get",
            dashboard_id=invite.dashboard.id,
            slug=invite.dashboard.slug,
        )
    )


def _verify_email_redirect():
    if current_user.is_authenticated:
        return redirect(url_for("profile.index"))
    return redirect(url_for("auth.login"))

@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def register():
    errors = {
        "form": [],
        "username": [],
        "email": [],
        "password": [],
        "confirm_password": [],
    }
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (
            invited_email_from_next(submitted_redirect_target(request))
            or (request.form.get("email") or "").strip().lower()
        )
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        submitted_token = request.form.get("csrf_token", "")
        stored_token = session.get("register_csrf_token", "")
        if not (
            isinstance(submitted_token, str)
            and isinstance(stored_token, str)
            and hmac.compare_digest(submitted_token, stored_token)
        ):
            errors["form"].append("Your form has expired. Please try again.")

        errors["username"].extend(collect_username_errors(username))
        errors["email"].extend(collect_email_errors(email))

        password_errors, confirm_password_errors = collect_password_errors(
            password,
            confirm_password,
            username=username,
            email=email,
        )
        errors["password"].extend(password_errors)
        errors["confirm_password"].extend(confirm_password_errors)

        if not any(errors.values()):
            username_exists = db.session.scalar(
                db.select(User.id).where(func.lower(User.username) == username.lower())
            )
            email_exists = db.session.scalar(
                db.select(User.id).where(func.lower(User.email) == email)
            )
            if username_exists or email_exists:
                errors["form"].append("Unable to create an account with those details.")
                if username_exists:
                    errors["username"].append("Username already exists.")
                else:
                    errors["email"].append("Email already exists.")

        if any(errors.values()):
            return render_template(
                "auth/register.html",
                **_register_context(errors, username, email),
            )

        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        new_user.dashboards.append(
            Dashboard(name="Home", is_default=True)
        )
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return render_template(
                "auth/register.html",
                **_register_context(
                    errors={"form": "Unable to create an account with those details."},
                    username=username,
                    email=email,
                ),
            )
        
        try:
            send_verification_email(new_user)
        except (OSError, smtplib.SMTPException):
            current_app.logger.exception("Failed to send verification email")
            flash(
                "Your account was created, but we could not send the verification email. "
                "You can resend it from your profile.",
                "warning",
            )
        else:
            flash("Please check your email for a verification link.", "info")

        session.pop("register_csrf_token", None)
        login_user(new_user)
        next_url = submitted_redirect_target(request)
        return _auto_accept_invite(new_user, next_url) or redirect(
            next_url or url_for("main.index")
        )
    return render_template("auth/register.html", **_register_context())

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def login():
    errors = {
        "form": [],
        "email": [],
        "password": [],
    }
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        submitted_token = request.form.get("csrf_token", "")
        stored_token = session.get("login_csrf_token", "")
        if not (
            isinstance(submitted_token, str)
            and isinstance(stored_token, str)
            and hmac.compare_digest(submitted_token, stored_token)
        ):
            errors["form"].append("Your form has expired. Please try again.")
        if not email:
            errors["email"].append("Email is required.")
        if not password:
            errors["password"].append("Password is required.")
        errors["email"].extend(collect_email_errors(email))
        if not any(errors.values()):
            user = db.session.scalar(
                db.select(User).where(func.lower(User.email) == email)
            )
            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=remember)
                flash(f"Welcome back, {user.username}!", "success")
                return redirect(submitted_redirect_target(request) or url_for("main.index"))
            else:
                errors["form"].append("Invalid email or password.")
        if any(errors.values()):
            return render_template("auth/login.html", **_login_context(errors, email))
    return render_template("auth/login.html", **_login_context())
    
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))

@auth_bp.route("/change-password", methods=["GET", "POST"])
@limiter.limit("50 per minute; 100 per hour", methods=["POST"])
@login_required
def change_password():
    errors = {
        "form": [],
        "current_password": [],
        "new_password": [],
        "confirm_password": [],
    }
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        submitted_token = request.form.get("csrf_token", "")
        stored_token = session.get("change_password_csrf_token", "")
        if not (
            isinstance(submitted_token, str)
            and isinstance(stored_token, str)
            and hmac.compare_digest(submitted_token, stored_token)
        ):
            errors["form"].append("Your form has expired. Please try again.")
        if not current_password:
            errors["current_password"].append("Current password is required.")
        password_errors, confirm_password_errors = collect_password_errors(
            new_password,
            confirm_password,
            username=current_user.username,
            email=current_user.email,
        )
        errors["new_password"].extend(password_errors)
        errors["confirm_password"].extend(confirm_password_errors)
        if not any(errors.values()):
            if check_password_hash(current_user.password_hash, current_password):
                current_user.password_hash = generate_password_hash(new_password)
                try:
                    db.session.commit()
                    flash("Your password has been changed.", "success")
                    return redirect(url_for("profile.index"))
                except IntegrityError:
                    db.session.rollback()
                    errors["form"].append("Unable to change password.")
            else:
                errors["current_password"].append("Invalid current password.")

        if any(errors.values()):
            return render_template(
                "auth/change_password.html",
                **_change_password_context(
                    errors, current_password, new_password, confirm_password
                ),
            )
    return render_template("auth/change_password.html", **_change_password_context())


@auth_bp.route("/delete-account", methods=["GET", "POST"])
@limiter.limit("50 per minute; 100 per hour", methods=["POST"])
@login_required
def delete_account():
    errors = {"form": [], "current_password": []}
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""

        submitted_token = request.form.get("csrf_token", "")
        stored_token = session.get("delete_account_csrf_token", "")
        if not (
            isinstance(submitted_token, str)
            and isinstance(stored_token, str)
            and hmac.compare_digest(submitted_token, stored_token)
        ):
            errors["form"].append("Your form has expired. Please try again.")
        if not current_password:
            errors["current_password"].append("Current password is required.")
        elif not errors["form"] and not check_password_hash(
            current_user.password_hash, current_password
        ):
            errors["current_password"].append("Invalid current password.")

        if not any(errors.values()):
            try:
                delete_user_account(current_user._get_current_object())
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                errors["form"].append("Unable to delete your account. Please try again.")
            else:
                logout_user()
                session.pop("delete_account_csrf_token", None)
                flash("Your account has been permanently deleted.", "success")
                return redirect(url_for("main.index"))

        return render_template("auth/delete_account.html", **_delete_account_context(errors))
    return render_template("auth/delete_account.html", **_delete_account_context())


@auth_bp.route("/verify-email/resend", methods=["POST"])
@limiter.limit("5 per minute; 10 per hour")
@login_required
def resend_verification_email():
    submitted_token = request.form.get("csrf_token", "")
    stored_token = session.get("resend_verification_csrf_token", "")
    if not (
        isinstance(submitted_token, str)
        and isinstance(stored_token, str)
        and hmac.compare_digest(submitted_token, stored_token)
    ):
        flash("Your form has expired. Please try again.", "warning")
        return redirect(url_for("profile.index"))

    session.pop("resend_verification_csrf_token", None)

    if current_user.email_verified:
        flash("Your email is already verified.", "info")
        return redirect(url_for("profile.index"))

    try:
        send_verification_email(current_user)
    except (OSError, smtplib.SMTPException) as e:
        print(e)
        current_app.logger.exception("Failed to resend verification email")
        flash(
            "We could not send the verification email. Please try again later.",
            "warning",
        )
    else:
        flash("Please check your email for a verification link.", "info")

    return redirect(url_for("profile.index"))


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    data = load_email_token(token)
    if data == "expired":
        flash(
            "This verification link has expired. Request a new one from your profile.",
            "warning",
        )
        return _verify_email_redirect()
    if not isinstance(data, dict):
        flash("This verification link is invalid.", "warning")
        return _verify_email_redirect()

    user = db.session.get(User, data.get("user_id"))
    if user is None or user.email != data.get("email"):
        flash("This verification link is invalid.", "warning")
        return _verify_email_redirect()

    if not user.email_verified:
        user.email_verified = True
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Unable to verify your email. Please try again.", "warning")
            return _verify_email_redirect()

    flash("Your email has been verified.", "success")
    login_user(user)
    return redirect(url_for("profile.index"))
