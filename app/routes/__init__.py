from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.profile import profile_bp
from app.routes.dashboards import dashboards_bp
from app.routes.notes import notes_bp
from app.routes.invites import invites_bp

__all__ = ["auth_bp", "dashboards_bp", "main_bp", "notes_bp", "profile_bp", "invites_bp"]
