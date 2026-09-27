"""E3 public compare checkpoint with independently stated fixture expectations."""

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from housing_engine import (
    CompareRequest, DocumentInput, EngineError, ExtractionConfig, KnowledgeBundle,
    compare_receipts, extract_receipt,
)
from housing_engine.dto import BillData, ConfirmedBill, ReceiptRef


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "receipts"
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
KNOWLEDGE = KnowledgeBundle(version="synthetic-e3", manifest={}, sources=[], territories=[], organizations=[], topics=[], glossary={}, aliases={})


def confirmed(period, receipt_number):
    content = (FIXTURES / f"demo-bill-{period}.pdf").read_bytes()
    ref = ReceiptRef(id=UUID(f"30000000-0000-4000-8000-{receipt_number:012d}"), revision=1)
    result = extract_receipt(DocumentInput(receipt_id=ref.id, content=content, mime_type="application/pdf", sha256=hashlib.sha256(content).hexdigest()), ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"]))
    assert result.outcome == "recognized"
    return ConfirmedBill(receipt_ref=ref, bill_data=result.bill_data, confirmed_at=NOW)


def from_json(period, receipt_number):
    data = BillData.model_validate_json((FIXTURES / f"water-{period}.json").read_text(encoding="utf-8"))
    return ConfirmedBill(receipt_ref=ReceiptRef(id=UUID(f"40000000-0000-4000-8000-{receipt_number:012d}"), revision=1), bill_data=data, confirmed_at=NOW)


def request(left, right, acknowledged=False):
    return CompareRequest(left=left, right=right, identity_acknowledged=acknowledged, territory_id=None, now=NOW)


class CompareCheckpointTests(unittest.TestCase):
    def test_bytes_pdf_200_to_270_exact_public_result(self):
        older, newer = confirmed("2026-08", 1), confirmed("2026-09", 2)
        expected = json.loads((FIXTURES / "water-comparison.json").read_text(encoding="utf-8"))["expected"]
        result = compare_receipts(request(newer, older, True), KNOWLEDGE)
        self.assertEqual((result.older.period, result.newer.period), ("2026-08", "2026-09"))
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.delta_current_charges, expected["delta_current_charges"])
        self.assertEqual(result.delta_total_due, expected["delta_total_due"])
        self.assertEqual(result.unexplained_delta, "0.00")
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]
        self.assertEqual(line.match_status, "matched")
        self.assertEqual((line.delta, line.quantity_effect, line.tariff_effect, line.rounding_effect),
                         ("70.00", expected["quantity_effect"], expected["tariff_effect"], expected["rounding_effect"]))
        self.assertEqual(sum((Decimal(item.contribution) for item in result.settlement_deltas), Decimal(0)), Decimal(0))
        self.assertEqual(result.actions, [])

    def test_unknown_identity_requires_acknowledgement(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        data = old.bill_data.model_copy(update={"account_number": None})
        old = old.model_copy(update={"bill_data": data})
        result = compare_receipts(request(old, new), KNOWLEDGE)
        self.assertEqual(result.status, "needs_identity_confirmation")
        self.assertIn("IDENTITY_UNVERIFIED", [issue.code for issue in result.issues])
        self.assertEqual(compare_receipts(request(old, new, True), KNOWLEDGE).status, "complete")

    def test_mismatched_account_and_same_month_block(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        changed = new.model_copy(update={"bill_data": new.bill_data.model_copy(update={"account_number": "000124"})})
        with self.assertRaises(EngineError) as raised:
            compare_receipts(request(old, changed, True), KNOWLEDGE)
        self.assertEqual(raised.exception.code, "INCOMPARABLE_RECEIPTS")
        with self.assertRaises(EngineError) as raised:
            compare_receipts(request(old, old, True), KNOWLEDGE)
        self.assertEqual(raised.exception.code, "INCOMPARABLE_RECEIPTS")


if __name__ == "__main__":
    unittest.main()
