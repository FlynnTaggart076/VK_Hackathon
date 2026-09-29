from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


JSONValue = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    max_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    demo_identity: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="other", nullable=False)
    territory_id: Mapped[str | None] = mapped_column(String(100))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    privacy_notice_version: Mapped[str | None] = mapped_column(String(50))
    privacy_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chat_llm_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chat_llm_opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggregate_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SessionToken(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dataset_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    extraction_outcome: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (Index("ix_receipts_user_created", "user_id", "created_at", "id"),)


class ReceiptRevision(Base):
    __tablename__ = "receipt_revisions"
    receipt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("receipts.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_data: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    extraction_meta: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    validation: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(String(100), nullable=False)


class ReceiptCohortLine(Base):
    """Derived metrics only; no address, account, provider, or source document."""
    __tablename__ = "receipt_cohort_lines"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    service_code: Mapped[str] = mapped_column(String(40), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("receipt_id", "line_id", "metric", name="uq_receipt_cohort_line_metric"),
        Index("ix_receipt_cohort_lookup", "city", "period", "service_code", "scope", "segment", "unit", "metric"),
        Index("ix_receipt_cohort_user", "user_id"),
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(80))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (Index("ix_jobs_claim", "state", "run_after", "lease_until"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    route: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("user_id", "route", "key", name="uq_idempotency_business_key"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    max_user_id: Mapped[int | None] = mapped_column(BigInteger)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(String(2000))
    attachment_kind: Mapped[str | None] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    max_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    attachments: Mapped[list] = mapped_column(JSONValue, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AssistantAnswer(Base):
    __tablename__ = "assistant_answers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    result: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    receipt_revision: Mapped[int | None] = mapped_column(Integer)
    dataset_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(5000), nullable=False)
    recipient: Mapped[dict | None] = mapped_column(JSONValue)
    actions: Mapped[list] = mapped_column(JSONValue, nullable=False)
    receipt_refs: Mapped[list] = mapped_column(JSONValue, nullable=False)
    knowledge_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class DialogState(Base):
    """One active assistant dialogue per user and channel; slots only, no raw documents."""
    __tablename__ = "dialog_states"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    state: Mapped[dict] = mapped_column(JSONValue, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ExternalUsage(Base):
    """Daily counters of paid or rate-limited external lookups shared by api and worker."""
    __tablename__ = "external_usage"
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
