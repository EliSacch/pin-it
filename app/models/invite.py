from app.extensions import db
from app.helpers.time import UTCDateTime, format_utc, utc_now


class Invite(db.Model):
    __tablename__ = "Invites"
    __table_args__ = (
        db.UniqueConstraint(
            "dashboard_id", "email", name="uq_invites_dashboard_id_email"
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    status = db.Column(
        db.Enum("pending", "accepted", "rejected", name="invite_status"),
        nullable=False,
        default="pending",
    )
    email = db.Column(db.String(100), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=True, index=True)
    user = db.relationship("User", back_populates="invites")
    dashboard_id = db.Column(db.Integer, db.ForeignKey("Dashboards.id"), nullable=False, index=True)
    dashboard = db.relationship("Dashboard", back_populates="invites")
    created_at = db.Column(UTCDateTime, default=utc_now, index=True)
    updated_at = db.Column(UTCDateTime, default=utc_now, onupdate=utc_now)
    deleted_at = db.Column(UTCDateTime, nullable=True)

    @property
    def formatted_updated_at(self):
        return format_utc(self.updated_at)

    @property
    def formatted_created_at(self):
        return format_utc(self.created_at)

    @property
    def formatted_deleted_at(self):
        return format_utc(self.deleted_at)

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "email": self.email,
            "user_id": self.user_id,
            "dashboard_id": self.dashboard_id,
            "created_at": self.formatted_created_at,
            "updated_at": self.formatted_updated_at,
            "deleted_at": self.formatted_deleted_at,
        }

    def __repr__(self):
        return f"<Invite {self.id}>"
