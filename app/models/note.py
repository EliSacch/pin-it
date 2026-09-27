import json

from app.extensions import db
from app.helpers.time import UTCDateTime, format_utc, utc_now


class Note(db.Model):
    __tablename__ = "Notes"
    __table_args__ = (
        db.CheckConstraint(
            "(owner_id IS NULL) <> (owner_deleted_at IS NULL)",
            name="ck_notes_owner_or_owner_deleted_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(50), nullable=False)
    content_json = db.Column(db.Text, default='[]')
    owner_id = db.Column(
        db.Integer, db.ForeignKey("Users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner = db.relationship("User", back_populates="notes")
    owner_deleted_at = db.Column(UTCDateTime, nullable=True)
    dashboard_id = db.Column(
        db.Integer, db.ForeignKey("Dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dashboard = db.relationship("Dashboard", back_populates="notes")
    created_at = db.Column(UTCDateTime, default=utc_now, index=True)
    updated_at = db.Column(UTCDateTime, default=utc_now, onupdate=utc_now)

    @property
    def formatted_updated_at(self):
        return format_utc(self.updated_at)

    @property
    def formatted_created_at(self):
        return format_utc(self.created_at)

    @property
    def content_blocks(self):
        try:
            blocks = json.loads(self.content_json or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(blocks, list):
            return []
        return blocks

    @property
    def content_text(self):
        return "\n".join(
            block.get("text", "") if isinstance(block, dict) else ""
            for block in self.content_blocks
        )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content_json": self.content_json,
            "content_blocks": self.content_blocks,
            "content_text": self.content_text,
            "created_at": self.formatted_created_at,
            "updated_at": self.formatted_updated_at,
        }

    def __repr__(self):
        return f"<Note {self.id}>"
