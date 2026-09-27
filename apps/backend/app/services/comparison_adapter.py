"""Owner-checked HTTP snapshots into the public housing_engine comparison API."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from housing_engine import BillData, CompareRequest, KnowledgeBundle, compare_receipts
from housing_engine.dto import ConfirmedBill, ReceiptRef


def compare_json(snapshots: list[dict], territory_id: str | None,
                 identity_acknowledged: bool) -> dict:
    bills = [ConfirmedBill(
        receipt_ref=ReceiptRef(id=item["id"], revision=item["revision"]),
        bill_data=BillData.model_validate_json(json.dumps(item["bill_data"])),
        confirmed_at=item["confirmed_at"],
    ) for item in snapshots]
    # C compare currently uses arithmetic only; C's E3 knowledge checkpoint
    # will replace this empty trusted bundle without changing HTTP shape.
    knowledge = KnowledgeBundle(version="0.0.0-e2-arithmetic-only", manifest={},
                                sources=[], territories=[], organizations=[],
                                topics=[], glossary={}, aliases={})
    result = compare_receipts(CompareRequest(
        left=bills[0], right=bills[1], identity_acknowledged=identity_acknowledged,
        territory_id=territory_id, now=datetime.now(timezone.utc),
    ), knowledge).model_dump(mode="json")
    result["dataset_kind"] = "synthetic" if any(
        item["dataset_kind"] == "synthetic" for item in snapshots) else "user_provided"
    return result
