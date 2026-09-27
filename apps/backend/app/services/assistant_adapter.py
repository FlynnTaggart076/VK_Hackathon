"""Translate owner-checked snapshots to C's public question and draft DTOs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from housing_engine import BillData, DraftRequest, QuestionRequest, answer_question, compose_draft
from housing_engine.dto import ExplainRequest, QuestionContext, ReceiptRef


def _confirmed(snapshot: dict, territory_id: str | None) -> ExplainRequest:
    return ExplainRequest(
        receipt_ref=ReceiptRef(id=snapshot["id"], revision=snapshot["revision"]),
        bill_data=BillData.model_validate_json(json.dumps(snapshot["bill_data"])),
        confirmed_at=snapshot["confirmed_at"], territory_id=territory_id,
        now=datetime.now(timezone.utc),
    )


def answer_json(question: str, context: dict, snapshots: list[dict],
                profile: dict, knowledge) -> dict:
    context = {**context, "territory_id": profile["territory_id"], "role": profile["role"]}
    context.pop("receipt_id", None)
    context.pop("receipt_revision", None)
    receipt = _confirmed(snapshots[0], profile["territory_id"]) if snapshots else None
    result = answer_question(QuestionRequest(
        question=question, context=QuestionContext(**context),
        receipt=receipt, now=datetime.now(timezone.utc),
    ), knowledge)
    return result.model_dump(mode="json")


def draft_json(body: dict, snapshots: list[dict], profile: dict, knowledge) -> dict:
    result = compose_draft(DraftRequest(
        topic_id=body["topic_id"], organization_id=body["organization_id"],
        territory_id=profile["territory_id"], role=profile["role"],
        receipts=[_confirmed(item, profile["territory_id"]) for item in snapshots],
        line_id=UUID(body["line_id"]) if body["line_id"] else None,
        user_question=body["user_question"],
        now=datetime.now(timezone.utc),
    ), knowledge)
    return result.model_dump(mode="json")
