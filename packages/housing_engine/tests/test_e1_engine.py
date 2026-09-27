import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
from pypdf import PdfReader

from housing_engine import BillData, DocumentInput, EngineError, ExtractionConfig, extract_receipt, validate_bill
from housing_engine.receipts import calculate_bill


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "receipts"
RECEIPT_ID = UUID("10000000-0000-4000-8000-000000000001")


def bill(name="water-2026-08.json", change=None):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if change:
        change(data)
    return BillData.model_validate_json(json.dumps(data, ensure_ascii=False))


def document(payload, mime_type):
    return DocumentInput(receipt_id=RECEIPT_ID, content=payload, mime_type=mime_type, sha256=hashlib.sha256(payload).hexdigest())


class ArithmeticTests(unittest.TestCase):
    def test_canonical_bills_are_exact_and_confirmable(self):
        for name, expected in (("water-2026-08.json", "200.00"), ("water-2026-09.json", "270.00")):
            with self.subTest(name=name):
                item = bill(name)
                result = validate_bill(item)
                arithmetic = calculate_bill(item)
                self.assertTrue(result.can_confirm)
                self.assertEqual(result.reconciliation_status, "matched")
                self.assertEqual(arithmetic.current_charges, expected)
                self.assertEqual(arithmetic.calculated_total_due, expected)

    def test_adjustment_is_counted_once(self):
        def change(data):
            data["adjustments"] = [{
                "adjustment_id": "30000000-0000-4000-8000-000000000001",
                "label": "Synthetic adjustment", "amount": "-50.00",
                "service_line_id": data["services"][0]["line_id"], "related_period": "2026-08",
            }]
            data["document_current_charges"] = "220.00"
            data["settlement"]["document_closing_balance"] = "220.00"
            data["document_total_due"] = "220.00"
        item = bill("water-2026-09.json", change)
        self.assertEqual(calculate_bill(item).current_charges, "220.00")
        self.assertEqual(validate_bill(item).reconciliation_status, "matched")

    def test_debt_payment_and_credit_clamp(self):
        def debt(data):
            data["settlement"]["opening_balance"] = "100.00"
            data["settlement"]["payments_credited"] = "80.00"
            data["settlement"]["document_closing_balance"] = "290.00"
            data["document_total_due"] = "290.00"
        debt_bill = bill("water-2026-09.json", debt)
        self.assertEqual(calculate_bill(debt_bill).calculated_total_due, "290.00")
        self.assertEqual(validate_bill(debt_bill).reconciliation_status, "matched")

        def credit(data):
            data["settlement"]["opening_balance"] = "-300.00"
            data["settlement"]["document_closing_balance"] = "-30.00"
            data["document_total_due"] = "0.00"
        credit_bill = bill("water-2026-09.json", credit)
        result = calculate_bill(credit_bill)
        self.assertEqual(result.calculated_closing_balance, "-30.00")
        self.assertEqual(result.calculated_total_due, "0.00")
        self.assertEqual(validate_bill(credit_bill).reconciliation_status, "matched")

    def test_missing_operand_and_unsupported_formula_do_not_guess(self):
        def missing(data):
            data["settlement"]["payments_credited"] = None
        result = calculate_bill(bill(change=missing))
        self.assertIsNone(result.calculated_closing_balance)
        self.assertIsNone(result.calculated_total_due)
        self.assertEqual(result.reconciliation_status, "incomplete")

        def unsupported(data):
            data["settlement"]["formula_kind"] = "unsupported"
        result = calculate_bill(bill(change=unsupported))
        self.assertIsNone(result.calculated_total_due)
        self.assertEqual(result.reconciliation_status, "unsupported")

    def test_mismatch_warns_but_can_confirm(self):
        def change(data):
            data["document_current_charges"] = "230.00"
        result = validate_bill(bill(change=change))
        self.assertTrue(result.can_confirm)
        self.assertEqual(result.reconciliation_status, "mismatch")
        self.assertIn("/document_current_charges", [warning.path for warning in result.warnings])

    def test_missing_charge_blocks_confirmation(self):
        def change(data):
            data["services"][0]["charge_amount"] = None
        result = validate_bill(bill(change=change))
        self.assertFalse(result.can_confirm)
        self.assertIn("CHARGE_REQUIRED", [error.code for error in result.errors])

    def test_whitespace_only_service_name_blocks_confirmation(self):
        def change(data):
            data["services"][0]["raw_name"] = "   "
        result = validate_bill(bill(change=change))
        self.assertFalse(result.can_confirm)
        self.assertIn("SERVICE_NAME_REQUIRED", [error.code for error in result.errors])

    def test_line_formula_uses_decimal_and_warns_over_one_kopeck(self):
        def rounded(data):
            line = data["services"][0]
            line["quantity"] = "1.005000"
            line["tariff"] = "1.000000"
            line["charge_amount"] = "1.01"
            data["document_current_charges"] = "1.01"
            data["settlement"]["document_closing_balance"] = "1.01"
            data["document_total_due"] = "1.01"
        self.assertEqual(validate_bill(bill(change=rounded)).reconciliation_status, "matched")

        def wrong(data):
            data["services"][0]["charge_amount"] = "200.02"
        result = validate_bill(bill(change=wrong))
        self.assertTrue(result.can_confirm)
        self.assertIn("LINE_AMOUNT_MISMATCH", [warning.code for warning in result.warnings])

    def test_orphan_adjustment_blocks_confirmation(self):
        def change(data):
            data["adjustments"] = [{
                "adjustment_id": "30000000-0000-4000-8000-000000000001",
                "label": "Synthetic adjustment", "amount": "-50.00",
                "service_line_id": "20000000-0000-4000-8000-000000000099", "related_period": None,
            }]
        result = validate_bill(bill(change=change))
        self.assertFalse(result.can_confirm)
        self.assertIn("ADJUSTMENT_LINE_UNKNOWN", [error.code for error in result.errors])


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])

    def test_text_pdf_reads_bytes_and_evidence(self):
        payload = (FIXTURES / "demo-bill-2026-08.pdf").read_bytes()
        result = extract_receipt(document(payload, "application/pdf"), self.config)
        self.assertEqual(result.outcome, "recognized")
        self.assertEqual(result.bill_data.period, "2026-08")
        self.assertEqual(result.bill_data.services[0].quantity, "5.000000")
        self.assertEqual(result.bill_data.services[0].tariff, "40.000000")
        self.assertEqual(result.bill_data.services[0].charge_amount, "200.00")
        self.assertEqual(result.bill_data.document_total_due, "200.00")
        self.assertTrue(any(item.path == "/services/0/charge_amount" and item.source == "pdf_text" for item in result.field_evidence))

    def test_unknown_template_requires_manual_input(self):
        payload = (FIXTURES / "demo-bill-2026-08.pdf").read_bytes().replace(b"DEMO-BILL-V1", b"OTHER-BILL-V1")
        result = extract_receipt(document(payload, "application/pdf"), self.config)
        self.assertEqual(result.outcome, "manual_required")
        self.assertEqual(result.bill_data.services, [])

    def test_corrupt_document_is_not_recognized(self):
        with self.assertRaises(EngineError) as raised:
            extract_receipt(document(b"%PDF-not-a-document", "application/pdf"), self.config)
        self.assertEqual(raised.exception.code, "CORRUPT_DOCUMENT")

    def test_image_path_reports_missing_system_tesseract(self):
        payload = (FIXTURES / "demo-bill-2026-08.png").read_bytes()
        with patch("housing_engine.extraction.shutil.which", return_value=None):
            with self.assertRaises(EngineError) as raised:
                extract_receipt(document(payload, "image/png"), self.config)
        self.assertEqual(raised.exception.code, "INTERNAL_ENGINE_ERROR")
        self.assertIn("Tesseract", raised.exception.message)

    def test_scanned_pdf_reaches_ocr_boundary(self):
        payload = (FIXTURES / "demo-bill-2026-08-scan.pdf").read_bytes()
        with patch("housing_engine.extraction.shutil.which", return_value=None):
            with self.assertRaises(EngineError) as raised:
                extract_receipt(document(payload, "application/pdf"), self.config)
        self.assertEqual(raised.exception.code, "INTERNAL_ENGINE_ERROR")

    def test_image_adapter_invokes_tesseract_without_shell(self):
        payload = (FIXTURES / "demo-bill-2026-08.png").read_bytes()
        text = PdfReader(FIXTURES / "demo-bill-2026-08.pdf").pages[0].extract_text()
        with patch("housing_engine.extraction.shutil.which", return_value="tesseract"):
            with patch("housing_engine.extraction.subprocess.run", return_value=subprocess.CompletedProcess([], 0, text, "")) as run:
                result = extract_receipt(document(payload, "image/png"), self.config)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[0], "tesseract")
        self.assertEqual(arguments[3:6], ["-l", "rus+eng", "--psm"])
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(result.bill_data.services[0].charge_amount, "200.00")
        self.assertTrue(any(item.source == "ocr" and item.needs_review for item in result.field_evidence))


if __name__ == "__main__":
    unittest.main()
