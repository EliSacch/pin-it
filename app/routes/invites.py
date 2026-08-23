from flask import Blueprint

invites_bp = Blueprint("invites", __name__, url_prefix="/dashboards/<int:dashboard_id>/invites")