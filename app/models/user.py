from flask_login import UserMixin

from app.extensions import db
from app.helpers.time import UTCDateTime, format_utc, utc_now


class User(UserMixin, db.Model):
    __tablename__ = "Users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email_verified = db.Column(
        db.Boolean, default=False, server_default=db.false(), nullable=False
    )
    password_hash = db.Column(db.String(255), nullable=False)
    # Notes on others' dashboards must be marked with owner_deleted_at before the
    # user is deleted; "all" stops the ORM from nulling owner_id on its own.
    notes = db.relationship("Note", back_populates="owner", passive_deletes="all")
    dashboards = db.relationship(
        "Dashboard", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    invites = db.relationship(
        "Invite", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    created_at = db.Column(UTCDateTime, default=utc_now)
    updated_at = db.Column(
        UTCDateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def formatted_updated_at(self):
        return format_utc(self.updated_at)

    @property
    def formatted_created_at(self):
        return format_utc(self.created_at)

    def __repr__(self):
        return f"<User {self.username}>"