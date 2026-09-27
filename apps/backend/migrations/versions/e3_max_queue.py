"""Minimal MAX inbox/outbox with bounded retention.

Revision ID: e3_max_queue
Revises: e1_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "e3_max_queue"
down_revision = "e1_initial"
branch_labels = None
depends_on = None
uid = sa.Uuid(as_uuid=True)
utc = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "webhook_inbox",
        sa.Column("id", uid, primary_key=True),
        sa.Column("dedup_key", sa.String(64), unique=True, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("max_user_id", sa.BigInteger()),
        sa.Column("chat_id", sa.BigInteger()),
        sa.Column("text", sa.String(2000)),
        sa.Column("attachment_kind", sa.String(24)),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.CheckConstraint("state IN ('queued','done')", name="ck_webhook_inbox_state"),
    )
    op.create_index("ix_webhook_inbox_expires_at", "webhook_inbox", ["expires_at"])
    op.create_table(
        "outbox",
        sa.Column("id", uid, primary_key=True),
        sa.Column("business_key", sa.String(80), unique=True, nullable=False),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(4000), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("run_after", utc, nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.CheckConstraint("state IN ('queued','sending','sent','uncertain','failed')", name="ck_outbox_state"),
    )
    op.create_index("ix_outbox_expires_at", "outbox", ["expires_at"])
    op.create_index("ix_outbox_claim", "outbox", ["state", "run_after"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
