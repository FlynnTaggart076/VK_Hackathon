"""Version 1.0 engine DTO. No HTTP, database, MAX or OCR implementation here."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Money = Annotated[str, StringConstraints(pattern=r"^-?(?:0|[1-9][0-9]{0,8})\.[0-9]{2}$")]
NonNegativeMoney = Annotated[str, StringConstraints(pattern=r"^(?:0|[1-9][0-9]{0,8})\.[0-9]{2}$")]
DecimalValue = Annotated[str, StringConstraints(pattern=r"^-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")]
Period = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

ServiceCode = Literal["cold_water", "hot_water", "drainage", "electricity", "heating", "maintenance", "capital_repair", "waste", "other"]
Unit = Literal["m3", "kwh", "gcal", "m2", "month", "person", "other"]
Role = Literal["owner", "tenant", "other"]
ReconciliationStatus = Literal["matched", "mismatch", "incomplete", "unsupported"]


class ServiceLine(DTO):
    line_id: UUID
    raw_name: str = Field(min_length=1, max_length=200)
    service_code: ServiceCode
    scope: Literal["individual", "common_property", "unspecified"]
    unit: Unit | None
    unit_label: str | None = Field(max_length=200)
    quantity: DecimalValue | None
    tariff: DecimalValue | None
    charge_amount: Money | None
    supplier_key: str | None = Field(max_length=200)
    segment_key: str | None = Field(max_length=200)
    calculation_kind: Literal["simple_product", "document_amount"]


class Adjustment(DTO):
    adjustment_id: UUID
    label: str = Field(min_length=1, max_length=200)
    amount: Money | None
    service_line_id: UUID | None
    related_period: Period | None


class Settlement(DTO):
    formula_kind: Literal["signed_balance_v1", "unsupported"]
    opening_balance: Money | None
    payments_credited: NonNegativeMoney | None
    penalties: Money | None
    other_account_changes: Money | None
    document_closing_balance: Money | None


class BillData(DTO):
    schema_version: Literal["1.0"]
    period: Period | None
    currency: Literal["RUB"]
    issuer_name: str | None = Field(min_length=1, max_length=200)
    provider_id: str | None = Field(min_length=1, max_length=200)
    account_number: str | None = Field(min_length=1, max_length=64)
    address_text: str | None = Field(min_length=1, max_length=500)
    template_id: str | None = Field(min_length=1, max_length=200)
    template_version: str | None = Field(min_length=1, max_length=40)
    services: list[ServiceLine] = Field(max_length=100)
    adjustments: list[Adjustment] = Field(max_length=100)
    settlement: Settlement
    document_current_charges: Money | None
    document_total_due: Money | None


class FieldEvidence(DTO):
    path: str = Field(pattern=r"^/(?:[^~/]|~[01])+(?:/(?:[^~/]|~[01])+)*$")
    source: Literal["pdf_text", "ocr", "manual", "template_default"]
    page_number: int | None = Field(ge=1)
    bbox: tuple[float, float, float, float] | None
    source_text: str | None = Field(max_length=500)
    needs_review: bool
    reason: str | None = Field(max_length=500)

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value: tuple[float, float, float, float] | None):
        if value is not None and (any(not 0 <= n <= 1 for n in value) or value[0] > value[2] or value[1] > value[3]):
            raise ValueError("bbox must be ordered normalized coordinates")
        return value


class Issue(DTO):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    severity: Literal["info", "warning", "error"]
    path: str | None
    message: str = Field(min_length=1, max_length=500)


class ReceiptRef(DTO):
    id: UUID
    revision: int = Field(ge=1)


class DocumentInput(DTO):
    receipt_id: UUID
    content: bytes = Field(repr=False, description="In-memory bytes only; never a user JSON field")
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    sha256: Sha256


class ExtractionConfig(DTO):
    timeout_seconds: int = Field(default=90, ge=1, le=90)
    max_pages: int = Field(default=3, ge=1, le=3)
    max_pixels_per_page: int = Field(default=25_000_000, ge=1, le=25_000_000)
    workspace: str = Field(min_length=1)
    enabled_templates: list[str]


class ExtractionResult(DTO):
    outcome: Literal["recognized", "partial", "manual_required"]
    bill_data: BillData
    field_evidence: list[FieldEvidence]
    issues: list[Issue]
    template_id: str | None
    engine_version: str


class ValidationResult(DTO):
    can_confirm: bool
    errors: list[Issue]
    warnings: list[Issue]
    reconciliation_status: ReconciliationStatus


class ExplainRequest(DTO):
    receipt_ref: ReceiptRef
    bill_data: BillData
    confirmed_at: datetime
    territory_id: str | None
    now: datetime


class ReconciliationCheck(DTO):
    field: Literal["document_current_charges", "document_closing_balance", "document_total_due"]
    document_value: Money | None
    calculated_value: Money | None
    difference: Money | None
    status: ReconciliationStatus


class ExplanationLine(DTO):
    line_id: UUID
    title: str
    explanation: str
    formula_text: str | None
    calculated_amount: Money | None
    difference: Money | None
    issues: list[Issue]


class BalanceComponent(DTO):
    code: str
    label: str
    amount: Money | None


class SourceRef(DTO):
    id: str
    title: str
    url: str | None
    territory_id: str | None
    verified_at: datetime
    review_after: datetime
    content_version: str
    is_synthetic: bool


class NextAction(DTO):
    id: str
    type: Literal["open_link", "prepare_draft", "select_topic", "navigate"]
    label: str
    url: str | None
    topic_id: str | None
    organization_id: str | None
    source_id: str | None
    target: Literal["receipt_upload", "receipt_history", "receipt_detail", "comparison"] | None
    receipt_ref: ReceiptRef | None
    requires: list[str]


class ReceiptExplanation(DTO):
    receipt_ref: ReceiptRef
    engine_version: str
    knowledge_version: str
    summary: str
    current_charges: Money | None
    document_total_due: Money | None
    calculated_closing_balance: Money | None
    calculated_total_due: Money | None
    unexplained_difference: Money | None
    reconciliation_checks: list[ReconciliationCheck]
    reconciliation_status: ReconciliationStatus
    lines: list[ExplanationLine]
    balance_components: list[BalanceComponent]
    issues: list[Issue]
    sources: list[SourceRef]
    actions: list[NextAction]


class ConfirmedBill(DTO):
    receipt_ref: ReceiptRef
    bill_data: BillData
    confirmed_at: datetime


class CompareRequest(DTO):
    left: ConfirmedBill
    right: ConfirmedBill
    identity_acknowledged: bool
    territory_id: str | None
    now: datetime


class ComparedLine(DTO):
    older_line_id: UUID | None
    newer_line_id: UUID | None
    label: str
    match_status: Literal["matched", "added", "removed", "ambiguous", "incompatible"]
    older_amount: Money | None
    newer_amount: Money | None
    delta: Money | None
    quantity_effect: Money | None
    tariff_effect: Money | None
    rounding_effect: Money | None
    explanation: str


class PeriodReceiptRef(ReceiptRef):
    period: Period | None


class SettlementDelta(DTO):
    code: Literal["opening_balance", "payments_credited", "penalties", "other_account_changes", "credit_clamp"]
    label: str
    raw_delta: Money | None
    contribution: Money | None


class ComparisonResult(DTO):
    status: Literal["complete", "partial", "needs_identity_confirmation"]
    older: PeriodReceiptRef
    newer: PeriodReceiptRef
    engine_version: str
    knowledge_version: str
    delta_current_charges: Money | None
    delta_adjustments: Money | None
    delta_total_due: Money | None
    lines: list[ComparedLine]
    settlement_deltas: list[SettlementDelta]
    unexplained_delta: Money | None
    issues: list[Issue]
    actions: list[NextAction]


class QuestionContext(DTO):
    territory_id: str | None
    role: Role | None
    topic_id: str | None
    organization_id: str | None
    service_code: ServiceCode | None
    document_kind: str | None


class QuestionRequest(DTO):
    question: str = Field(min_length=1, max_length=2000)
    context: QuestionContext
    receipt: ExplainRequest | None
    now: datetime


class ClarificationOption(DTO):
    value: str
    label: str


class Clarification(DTO):
    field: Literal["topic_id", "territory_id", "role", "organization_id", "service_code", "document_kind"]
    prompt: str
    options: list[ClarificationOption]


class AnswerResult(DTO):
    status: Literal["answered", "needs_clarification", "unsupported"]
    text: str = Field(max_length=1500)
    topic_id: str | None
    steps: list[str] = Field(max_length=5)
    sources: list[SourceRef]
    actions: list[NextAction]
    clarification: Clarification | None
    limitations: list[str]
    knowledge_version: str
    receipt_ref: ReceiptRef | None


class DraftRequest(DTO):
    topic_id: str
    organization_id: str | None
    territory_id: str | None
    role: Role
    receipts: list[ExplainRequest] = Field(max_length=2)
    line_id: UUID | None
    user_question: str = Field(max_length=2000)
    now: datetime


class Recipient(DTO):
    id: str
    label: str


class DraftResult(DTO):
    text: str = Field(max_length=5000)
    recipient: Recipient | None
    actions: list[NextAction]
    receipt_refs: list[ReceiptRef]
    knowledge_version: str
    issues: list[Issue]


class KnowledgeBundle(DTO):
    version: str
    manifest: dict
    sources: list[dict]
    territories: list[dict]
    organizations: list[dict]
    topics: list[dict]
    glossary: dict
    aliases: dict
