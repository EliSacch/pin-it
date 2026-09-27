"""Add account deletion cascades and deleted note author marker

Revision ID: a4d7c9e2f615
Revises: b3e91c4a7d12
Create Date: 2026-09-27 12:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.helpers.time import UTCDateTime


revision = "a4d7c9e2f615"
down_revision = "b3e91c4a7d12"
branch_labels = None
depends_on = None


def _replace_fk(table, column, referent, ondelete):
    name = f"{table}_{column}_fkey"
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.drop_constraint(name, type_="foreignkey")
        batch_op.create_foreign_key(name, referent, [column], ["id"], ondelete=ondelete)


def upgrade():
    _replace_fk("Dashboards", "owner_id", "Users", "CASCADE")
    _replace_fk("Notes", "dashboard_id", "Dashboards", "CASCADE")
    _replace_fk("Notes", "owner_id", "Users", "SET NULL")
    _replace_fk("Invites", "dashboard_id", "Dashboards", "CASCADE")
    _replace_fk("Invites", "user_id", "Users", "CASCADE")

    with op.batch_alter_table("Notes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_deleted_at", UTCDateTime(), nullable=True))
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            "ck_notes_owner_or_owner_deleted_at",
            "(owner_id IS NULL) <> (owner_deleted_at IS NULL)",
        )


def downgrade():
    op.execute('DELETE FROM "Notes" WHERE owner_id IS NULL')
    with op.batch_alter_table("Notes", schema=None) as batch_op:
        batch_op.drop_constraint("ck_notes_owner_or_owner_deleted_at", type_="check")
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("owner_deleted_at")

    _replace_fk("Invites", "user_id", "Users", None)
    _replace_fk("Invites", "dashboard_id", "Dashboards", None)
    _replace_fk("Notes", "owner_id", "Users", None)
    _replace_fk("Notes", "dashboard_id", "Dashboards", None)
    _replace_fk("Dashboards", "owner_id", "Users", None)
