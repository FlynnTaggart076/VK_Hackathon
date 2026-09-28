"""Separate voluntary MAX chat LLM consent from receipt processing notice.

Revision ID: e4_chat_llm_consent
Revises: e3_max_keyboard
"""

from alembic import op
import sqlalchemy as sa


revision = "e4_chat_llm_consent"
down_revision = "e3_max_keyboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("chat_llm_consent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
