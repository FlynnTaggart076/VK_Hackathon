"""Persist owner-scoped E3 answers and editable drafts.

Revision ID: e3_assistant
Revises: e3_max_queue
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e3_assistant"
down_revision = "e3_max_queue"
branch_labels = None
depends_on = None
uid = sa.Uuid(as_uuid=True)
utc = sa.DateTime(timezone=True)
json_value = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "assistant_answers",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column("result", json_value, nullable=False),
        sa.Column("receipt_id", uid),
        sa.Column("receipt_revision", sa.Integer()),
        sa.Column("dataset_kind", sa.String(24), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
    )
    op.create_index("ix_assistant_answers_user_id", "assistant_answers", ["user_id"])
    op.create_index("ix_assistant_answers_expires_at", "assistant_answers", ["expires_at"])
    op.create_table(
        "drafts",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(5000), nullable=False),
        sa.Column("recipient", json_value),
        sa.Column("actions", json_value, nullable=False),
        sa.Column("receipt_refs", json_value, nullable=False),
        sa.Column("knowledge_version", sa.String(128), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_drafts_revision"),
    )
    op.create_index("ix_drafts_user_id", "drafts", ["user_id"])
    op.create_index("ix_drafts_expires_at", "drafts", ["expires_at"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
