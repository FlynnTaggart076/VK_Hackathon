"""Explicit aggregate consent and derived private cohort values.

Revision ID: e4_city_cohort
Revises: e4_chat_llm_consent
"""

from alembic import op
import sqlalchemy as sa


revision = "e4_city_cohort"
down_revision = "e4_chat_llm_consent"
branch_labels = None
depends_on = None

uid = sa.Uuid(as_uuid=True)
utc = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("profiles", sa.Column("aggregate_opt_in", sa.Boolean(), nullable=False,
                                        server_default=sa.text("false")))
    op.create_table(
        "receipt_cohort_lines",
        sa.Column("id", uid, primary_key=True),
        sa.Column("receipt_id", uid, sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_id", uid, nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("service_code", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("segment", sa.String(64)),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(24), nullable=False),
        sa.Column("value", sa.String(24), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.UniqueConstraint("receipt_id", "line_id", "metric", name="uq_receipt_cohort_line_metric"),
    )
    op.create_index("ix_receipt_cohort_lookup", "receipt_cohort_lines",
                    ["city", "period", "service_code", "scope", "segment", "unit", "metric"])
    op.create_index("ix_receipt_cohort_user", "receipt_cohort_lines", ["user_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
