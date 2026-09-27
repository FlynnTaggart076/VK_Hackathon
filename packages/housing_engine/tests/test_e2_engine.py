"""Public E2 checkpoint: bytes extraction -> confirmed arithmetic explanation."""

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from housing_engine import (
    DocumentInput, EngineError, ExplainRequest, ExtractionConfig, KnowledgeBundle,
    explain_receipt, extract_receipt,
)
from housing_engine.dto import ReceiptRef


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "receipts"
RECEIPT_ID = UUID("10000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
KNOWLEDGE = KnowledgeBundle(version="0.0.0-e0-contract-only", manifest={}, sources=[], territories=[], organizations=[], topics=[], glossary={}, aliases={})


def document(name):
    payload = (FIXTURES / name).read_bytes()
    return DocumentInput(receipt_id=RECEIPT_ID, content=payload, mime_type="application/pdf", sha256=hashlib.sha256(payload).hexdigest())


def explain(bill):
    return explain_receipt(ExplainRequest(
        receipt_ref=ReceiptRef(id=RECEIPT_ID, revision=1), bill_data=bill,
        confirmed_at=NOW, territory_id=None, now=NOW,
    ), KNOWLEDGE)


class E2CheckpointTests(unittest.TestCase):
    def test_two_text_pdfs_from_bytes_to_exact_explanation(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        for period, due in (("2026-08", "200.00"), ("2026-09", "270.00")):
            with self.subTest(period=period):
                result = extract_receipt(document(f"demo-bill-{period}.pdf"), config)
                self.assertEqual(result.outcome, "recognized")
                self.assertEqual(result.bill_data.period, period)
                self.assertTrue(any(item.path == "/document_total_due" and item.source == "pdf_text" for item in result.field_evidence))
                explained = explain(result.bill_data)
                self.assertEqual(explained.current_charges, due)
                self.assertEqual(explained.calculated_total_due, due)
                self.assertEqual(explained.document_total_due, due)
                self.assertEqual(explained.reconciliation_status, "matched")
                self.assertEqual(explained.lines[0].calculated_amount, due)
                self.assertEqual(explained.unexplained_difference, "0.00")
                self.assertEqual(explained.sources, [])
                self.assertIn("ARITHMETIC_ONLY", [issue.code for issue in explained.issues])

    def test_unconfirmed_bill_is_rejected(self):
        data = json.loads((FIXTURES / "water-2026-08.json").read_text(encoding="utf-8"))
        data["services"][0]["charge_amount"] = None
        from housing_engine import BillData
        with self.assertRaises(EngineError) as raised:
            explain(BillData.model_validate_json(json.dumps(data)))
        self.assertEqual(raised.exception.code, "INVALID_BILL")


if __name__ == "__main__":
    unittest.main()
