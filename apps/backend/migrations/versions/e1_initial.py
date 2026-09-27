"""E1 users, sessions, documents, receipts, jobs and idempotency.

Revision ID: e1_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e1_initial"
down_revision = None
branch_labels = None
depends_on = None
json_value = sa.JSON().with_variant(JSONB(), "postgresql")
uid = sa.Uuid(as_uuid=True)
utc = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", uid, primary_key=True),
        sa.Column("max_user_id", sa.BigInteger(), unique=True),
        sa.Column("demo_identity", sa.String(64), unique=True),
        sa.Column("created_at", utc, nullable=False),
        sa.CheckConstraint("(max_user_id IS NULL) <> (demo_identity IS NULL)", name="ck_users_one_identity"),
    )
    op.create_table(
        "profiles",
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("territory_id", sa.String(100)),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False),
        sa.Column("privacy_notice_version", sa.String(50)),
        sa.Column("privacy_acknowledged_at", utc),
        sa.CheckConstraint("role IN ('owner','tenant','other')", name="ck_profiles_role"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.Column("revoked_at", utc),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "documents",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(96), unique=True, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.Column("deleted_at", utc),
        sa.Column("created_at", utc, nullable=False),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_expires_at", "documents", ["expires_at"])
    op.create_table(
        "receipts",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", uid, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("dataset_kind", sa.String(24), nullable=False),
        sa.Column("extraction_outcome", sa.String(24)),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.CheckConstraint("status IN ('queued','processing','needs_review','confirmed','failed')", name="ck_receipts_status"),
        sa.CheckConstraint("dataset_kind IN ('synthetic','user_provided')", name="ck_receipts_dataset"),
        sa.CheckConstraint("current_revision >= 1", name="ck_receipts_revision"),
    )
    op.create_index("ix_receipts_user_created", "receipts", ["user_id", "created_at", "id"])
    op.create_table(
        "receipt_revisions",
        sa.Column("receipt_id", uid, sa.ForeignKey("receipts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("bill_data", json_value, nullable=False),
        sa.Column("extraction_meta", json_value, nullable=False),
        sa.Column("validation", json_value, nullable=False),
        sa.Column("confirmed_at", utc),
        sa.Column("engine_version", sa.String(100), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_receipt_revisions_positive"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("resource_id", uid, nullable=False),
        sa.Column("operation_key", sa.String(160), unique=True, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("stage", sa.String(80)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_token", uid),
        sa.Column("lease_until", utc),
        sa.Column("run_after", utc, nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.CheckConstraint("state IN ('queued','running','succeeded','failed')", name="ck_jobs_state"),
        sa.CheckConstraint("attempt >= 0", name="ck_jobs_attempt"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_claim", "jobs", ["state", "run_after", "lease_until"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("route", sa.String(100), nullable=False),
        sa.Column("key", uid, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", json_value, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.UniqueConstraint("user_id", "route", "key", name="uq_idempotency_business_key"),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])
    op.create_table(
        "worker_heartbeats",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("updated_at", utc, nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is intentionally unavailable; restore an isolated verified backup")
