"""Server-side assistant dialogue slots and external lookup quotas.

Revision ID: e5_dialog_state
Revises: e4_city_cohort
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e5_dialog_state"
down_revision = "e4_city_cohort"
branch_labels = None
depends_on = None
uid = sa.Uuid(as_uuid=True)
utc = sa.DateTime(timezone=True)
json_value = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dialog_states",
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("channel", sa.String(16), primary_key=True),
        sa.Column("state", json_value, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.CheckConstraint("channel IN ('max_chat', 'web')", name="ck_dialog_states_channel"),
        sa.CheckConstraint("version >= 1", name="ck_dialog_states_version"),
    )
    op.create_index("ix_dialog_states_expires_at", "dialog_states", ["expires_at"])
    op.create_table(
        "external_usage",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
