"""Store invite email and allow null user

Revision ID: b3e91c4a7d12
Revises: f8e6b2b2f9a7
Create Date: 2026-08-23 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b3e91c4a7d12"
down_revision = "f8e6b2b2f9a7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("Invites", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=100), nullable=False))
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_index(batch_op.f("ix_Invites_email"), ["email"], unique=False)
        batch_op.create_unique_constraint(
            "uq_invites_dashboard_id_email", ["dashboard_id", "email"]
        )


def downgrade():
    with op.batch_alter_table("Invites", schema=None) as batch_op:
        batch_op.drop_constraint("uq_invites_dashboard_id_email", type_="unique")
        batch_op.drop_index(batch_op.f("ix_Invites_email"))
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column("email")
