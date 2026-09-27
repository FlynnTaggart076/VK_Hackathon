"""Public E2 checkpoint: bytes extraction -> confirmed arithmetic explanation."""

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
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
    mime = "application/pdf" if name.endswith(".pdf") else ("image/jpeg" if name.endswith(".jpg") else "image/png")
    return DocumentInput(receipt_id=RECEIPT_ID, content=payload, mime_type=mime, sha256=hashlib.sha256(payload).hexdigest())


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
                self.assertTrue(any(item.path == "/document_total_due" and item.page_number == 1 and item.bbox is not None for item in result.field_evidence))
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

    def test_adjustment_debt_payment_and_credit_are_separate(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        cases = (
            ("adjustment", "220.00", "220.00", "220.00"),
            ("debt-payment", "270.00", "290.00", "290.00"),
            ("credit", "270.00", "-30.00", "0.00"),
        )
        for kind, charges, closing, due in cases:
            with self.subTest(kind=kind):
                result = extract_receipt(document(f"demo-bill-2026-09-{kind}.pdf"), config)
                self.assertEqual(result.outcome, "recognized")
                explained = explain(result.bill_data)
                self.assertEqual(explained.current_charges, charges)
                self.assertEqual(explained.calculated_closing_balance, closing)
                self.assertEqual(explained.calculated_total_due, due)
                self.assertEqual(explained.reconciliation_status, "matched")
                self.assertEqual(explained.lines[0].calculated_amount, "270.00")
                if kind == "adjustment":
                    self.assertEqual(len(result.bill_data.adjustments), 1)
                    self.assertEqual(result.bill_data.adjustments[0].amount, "-50.00")
                    self.assertEqual(result.bill_data.adjustments[0].related_period, "2026-08")
                    self.assertEqual({item.code: item.amount for item in explained.balance_components}["service_charges"], "270.00")
                    self.assertEqual({item.code: item.amount for item in explained.balance_components}["adjustments"], "-50.00")
                    self.assertIn("ADJUSTMENT_APPLIED", [item.code for item in explained.issues])

    def test_unknown_service_is_preserved_with_review(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        result = extract_receipt(document("demo-bill-2026-09-unknown-service.pdf"), config)
        self.assertEqual(result.outcome, "partial")
        self.assertEqual(result.bill_data.services[0].service_code, "other")
        self.assertEqual(result.bill_data.services[0].raw_name, "Mystery service (m3)")
        self.assertTrue(any(item.path == "/services/0/service_code" and item.needs_review for item in result.field_evidence))

    def test_bad_ocr_cropped_unknown_and_corrupt_do_not_fabricate(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        cropped = extract_receipt(document("demo-bill-cropped.pdf"), config)
        self.assertEqual(cropped.outcome, "partial")
        self.assertIsNone(cropped.bill_data.document_total_due)
        unknown = extract_receipt(document("unknown-layout.pdf"), config)
        self.assertEqual(unknown.outcome, "manual_required")
        self.assertEqual(unknown.bill_data.services, [])
        with self.assertRaises(EngineError) as raised:
            extract_receipt(document("corrupt.pdf"), config)
        self.assertEqual(raised.exception.code, "CORRUPT_DOCUMENT")
        text = "\n".join(("DEMO-BILL-V1", "PERIOD: 2026-08", "SERVICE | QTY | TARIFF | CHARGE", "Cold water (m3) | 5.000000 | 40.000000 | 2O0.00", "TOTAL DUE: 200.00"))
        with patch("housing_engine.extraction._ocr", return_value=text):
            garbled = extract_receipt(document("demo-bill-2026-08.png"), config)
        self.assertEqual(garbled.outcome, "partial")
        self.assertEqual(garbled.bill_data.services, [])
        self.assertIsNone(garbled.bill_data.document_current_charges)
        with patch("housing_engine.extraction._ocr", return_value=""):
            unreadable = extract_receipt(document("demo-bill-unreadable.png"), config)
        self.assertEqual(unreadable.outcome, "manual_required")

    def test_printed_total_mismatch_remains_visible(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        result = extract_receipt(document("demo-bill-2026-09-mismatch.pdf"), config)
        self.assertEqual(result.outcome, "partial")
        self.assertEqual(result.bill_data.document_total_due, "271.00")
        explained = explain(result.bill_data)
        self.assertEqual(explained.calculated_total_due, "270.00")
        self.assertEqual(explained.unexplained_difference, "1.00")
        self.assertEqual(explained.reconciliation_status, "mismatch")

    def test_large_product_does_not_break_public_dto(self):
        data = json.loads((FIXTURES / "water-2026-08.json").read_text(encoding="utf-8"))
        data["services"][0]["quantity"] = "999999999.999999"
        data["services"][0]["tariff"] = "999999999.999999"
        from housing_engine import BillData
        result = explain(BillData.model_validate_json(json.dumps(data)))
        self.assertIsNone(result.lines[0].calculated_amount)
        self.assertIn("LINE_CALCULATION_OUT_OF_RANGE", [item.code for item in result.lines[0].issues])

    def test_aggregate_out_of_contract_range_is_safe_error(self):
        data = json.loads((FIXTURES / "water-2026-08.json").read_text(encoding="utf-8"))
        data["services"][0]["charge_amount"] = "999999999.99"
        second = dict(data["services"][0])
        second["line_id"] = "20000000-0000-4000-8000-000000000099"
        data["services"].append(second)
        from housing_engine import BillData
        with self.assertRaises(EngineError) as raised:
            explain(BillData.model_validate_json(json.dumps(data)))
        self.assertEqual(raised.exception.code, "INVALID_BILL")


if __name__ == "__main__":
    unittest.main()
