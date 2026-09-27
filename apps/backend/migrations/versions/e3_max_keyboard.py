"""Persist MAX inline keyboard attachments with queued replies.

Revision ID: e3_max_keyboard
Revises: e3_assistant
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e3_max_keyboard"
down_revision = "e3_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    value = sa.JSON().with_variant(JSONB(), "postgresql")
    op.add_column("outbox", sa.Column("attachments", value, nullable=False,
                                       server_default=sa.text("'[]'")))


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
