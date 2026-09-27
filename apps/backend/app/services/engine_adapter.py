"""The only backend boundary to housing_engine's public v1 functions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from housing_engine import (
    BillData, DocumentInput, ExplainRequest, ExtractionConfig, KnowledgeBundle,
    explain_receipt, extract_receipt, validate_bill,
)
from housing_engine.dto import ReceiptRef

from app.errors import ApiError


ARITHMETIC_KNOWLEDGE = KnowledgeBundle(
    version="0.0.0-e2-arithmetic-only", manifest={}, sources=[], territories=[],
    organizations=[], topics=[], glossary={}, aliases={},
)


def bill_from_client(payload: dict, previous: dict | None = None, *, manual: bool = False) -> BillData:
    """Reject malformed data and derive server-owned template/formula fields."""
    if not isinstance(payload, dict):
        raise ApiError(422, "VALIDATION_FAILED", "Укажите данные квитанции.")
    data = dict(payload)
    data["template_id"] = previous.get("template_id") if previous else ("manual-v1" if manual else None)
    data["template_version"] = previous.get("template_version") if previous else ("1.0" if manual else None)
    settlement = data.get("settlement")
    if isinstance(settlement, dict):
        data["settlement"] = dict(settlement, formula_kind=(
            previous.get("settlement", {}).get("formula_kind", "unsupported") if previous else "unsupported"))
    services = data.get("services")
    if isinstance(services, list):
        previous_kinds = {line["line_id"]: line["calculation_kind"]
                          for line in previous.get("services", [])} if previous else {}
        data["services"] = [dict(line, calculation_kind=previous_kinds.get(
            line.get("line_id"), "document_amount")) if isinstance(line, dict) else line
            for line in services]
    try:
        return BillData.model_validate_json(json.dumps(data, ensure_ascii=False))
    except ValidationError as exc:
        raise ApiError(422, "VALIDATION_FAILED", "Проверьте поля квитанции.",
                       details={"invalid_fields": ["/" + "/".join(map(str, item["loc"])) for item in exc.errors()]}) from None


def validation_json(bill: BillData) -> dict:
    return validate_bill(bill).model_dump(mode="json")


def extract_json(receipt_id: uuid.UUID, content: bytes, mime_type: str, workspace: str) -> dict:
    document = DocumentInput(receipt_id=receipt_id, content=content, mime_type=mime_type,
                             sha256=hashlib.sha256(content).hexdigest())
    config = ExtractionConfig(workspace=workspace, enabled_templates=["demo-bill-v1"])
    result = extract_receipt(document, config)
    return result.model_dump(mode="json")


def explain_json(receipt_id: uuid.UUID, revision: int, bill_data: dict,
                 confirmed_at: datetime, territory_id: str | None) -> dict:
    request = ExplainRequest(
        receipt_ref=ReceiptRef(id=receipt_id, revision=revision),
        bill_data=BillData.model_validate_json(json.dumps(bill_data, ensure_ascii=False)),
        confirmed_at=confirmed_at, territory_id=territory_id,
        now=datetime.now(timezone.utc),
    )
    return explain_receipt(request, ARITHMETIC_KNOWLEDGE).model_dump(mode="json")
