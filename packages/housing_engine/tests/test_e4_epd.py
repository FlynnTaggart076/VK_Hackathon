"""Synthetic EPD layout, deterministic comparison and private-sample regression."""

import hashlib
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader

from housing_engine import CompareRequest, DocumentInput, ExtractionConfig, compare_receipts, extract_receipt
from housing_engine.dto import ConfirmedBill, KnowledgeBundle, ReceiptRef
from housing_engine.epd import EPD_TEMPLATE_ID, parse_epd_text, project_epd_table_candidates, project_receipt_facts


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "receipts"
NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
KNOWLEDGE = KnowledgeBundle(version="synthetic-e4", manifest={}, sources=[], territories=[], organizations=[], topics=[], glossary={}, aliases={})


def parsed(month: str):
    source = (FIXTURES / f"epd-synthetic-2026-{month}.txt").read_text(encoding="utf-8")
    receipt_id = UUID(f"60000000-0000-4000-8000-{int(month):012d}")
    return parse_epd_text(source, receipt_id), receipt_id


class EpdTests(unittest.TestCase):
    def test_synthetic_layout_omits_insurance_and_reference_meter(self):
        for month, charges, due, adjustment in (("08", "1660.00", "1660.00", "-10.00"),
                                                 ("09", "1765.00", "1765.00", "-5.00")):
            with self.subTest(month=month):
                result, _ = parsed(month)
                self.assertEqual(result.outcome, "partial")
                self.assertEqual(result.template_id, EPD_TEMPLATE_ID)
                self.assertEqual(len(result.bill_data.services), 4)
                self.assertEqual(len(result.bill_data.adjustments), 1)
                self.assertEqual(result.bill_data.adjustments[0].amount, adjustment)
                self.assertEqual(result.bill_data.document_current_charges, charges)
                self.assertEqual(result.bill_data.document_total_due, due)
                self.assertEqual(result.bill_data.services[0].scope, "common_property")
                self.assertEqual(result.bill_data.services[-1].service_code, "electricity")
                self.assertNotIn("EPD_CHARGE_SUM_MISMATCH", [item.code for item in result.issues])
                self.assertNotIn("EPD_ADJUSTMENT_SUM_MISMATCH", [item.code for item in result.issues])
                self.assertTrue(all("СТРАХОВАНИЕ" not in item.raw_name for item in result.bill_data.services))
                self.assertTrue(all(item.source == "pdf_text" for item in result.field_evidence))
                self.assertTrue(any(item.path == "/account_number" and item.needs_review for item in result.field_evidence))

    def test_quantity_tariff_and_adjustment_effects_are_separate(self):
        old_result, old_id = parsed("08")
        new_result, new_id = parsed("09")
        old = ConfirmedBill(receipt_ref=ReceiptRef(id=old_id, revision=1), bill_data=old_result.bill_data, confirmed_at=NOW)
        new = ConfirmedBill(receipt_ref=ReceiptRef(id=new_id, revision=1), bill_data=new_result.bill_data, confirmed_at=NOW)
        result = compare_receipts(CompareRequest(left=old, right=new, identity_acknowledged=False,
                                                 territory_id=None, now=NOW), KNOWLEDGE)
        self.assertEqual(result.status, "partial")  # settlement formula remains unsupported
        self.assertEqual(result.delta_current_charges, "105.00")
        self.assertEqual(result.delta_adjustments, "5.00")
        self.assertEqual(result.delta_total_due, "105.00")
        cold = next(item for item in result.lines if item.older_line_id == old_result.bill_data.services[1].line_id)
        self.assertEqual((cold.quantity_effect, cold.tariff_effect), ("40.00", "10.00"))
        electric = next(item for item in result.lines if item.older_line_id == old_result.bill_data.services[3].line_id)
        self.assertEqual((electric.quantity_effect, electric.tariff_effect), ("50.00", "0.00"))

    def test_model_projection_excludes_identity_and_raw_text(self):
        result, _ = parsed("08")
        projected = project_receipt_facts(result.bill_data)
        serialized = json.dumps(projected, ensure_ascii=False)
        self.assertEqual(projected["period"], "2026-08")
        self.assertEqual(projected["provenance"], "parsed_epd_requires_review")
        self.assertEqual(len(projected["services"]), 4)
        for private in (result.bill_data.account_number, result.bill_data.address_text,
                        result.bill_data.issuer_name, result.bill_data.provider_id, "УЧЕБНАЯ"):
            self.assertNotIn(private, serialized)
        self.assertNotIn("raw_name", serialized)
        table = project_epd_table_candidates((FIXTURES / "epd-synthetic-2026-08.txt").read_text(encoding="utf-8"))
        table_json = json.dumps(table, ensure_ascii=False)
        self.assertEqual(table["source"], "main_charge_table_only")
        self.assertEqual(len(table["rows"]), 4)
        for private in (result.bill_data.account_number, result.bill_data.address_text,
                        result.bill_data.issuer_name, result.bill_data.provider_id,
                        "СТРАХОВАНИЕ", "Справочная информация", "99.00"):
            self.assertNotIn(private, table_json)

    def test_malformed_total_or_missing_row_is_partial_with_issue(self):
        original = (FIXTURES / "epd-synthetic-2026-08.txt").read_text(encoding="utf-8")
        malformed = original.replace("1 670,00       -10,00", "1 671,00       -10,00")
        result = parse_epd_text(malformed, UUID("60000000-0000-4000-8000-000000000099"))
        self.assertEqual(result.outcome, "partial")
        self.assertIn("EPD_CHARGE_SUM_MISMATCH", [item.code for item in result.issues])
        malformed = original.replace("ХОЛОДНОЕ В/С                 4.00", "ХОЛОДНОЕ В/С                 ?")
        result = parse_epd_text(malformed, UUID("60000000-0000-4000-8000-000000000099"))
        self.assertIsNone(result.bill_data.services[1].quantity)
        self.assertIn("EPD_COLUMN_AMBIGUOUS", [item.code for item in result.issues])
        malformed = original.replace("500,00          -10,00", "500,00          ?")
        result = parse_epd_text(malformed, UUID("60000000-0000-4000-8000-000000000099"))
        self.assertIsNone(result.bill_data.adjustments[0].amount)
        self.assertIsNone(project_receipt_facts(result.bill_data)["services"][-1]["adjustment"])
        self.assertIn("ADJUSTMENT_AMOUNT_REQUIRED", [item.code for item in result.issues])

    def test_private_ex_parse_summary_without_disclosing_values(self):
        private_file = next((path for path in (ROOT / "EX.pdf", ROOT.parent.parent / "EX.pdf") if path.is_file()), None)
        if private_file is None:
            self.skipTest("private EX.pdf is not in this checkout")
        payload = private_file.read_bytes()
        receipt_id = UUID("60000000-0000-4000-8000-000000000123")
        result = extract_receipt(DocumentInput(receipt_id=receipt_id, content=payload,
                                               mime_type="application/pdf", sha256=hashlib.sha256(payload).hexdigest()),
                                 ExtractionConfig(workspace=os.fspath(ROOT), enabled_templates=[EPD_TEMPLATE_ID]))
        self.assertEqual(result.template_id, EPD_TEMPLATE_ID)
        self.assertEqual(result.outcome, "partial")
        self.assertEqual(len(result.bill_data.services), 19)
        self.assertEqual(len(result.bill_data.adjustments), 4)
        self.assertEqual(sum(line.service_code != "other" for line in result.bill_data.services), 16)
        self.assertTrue(all(line.charge_amount is not None and line.quantity is not None and line.tariff is not None
                            for line in result.bill_data.services))
        self.assertTrue(result.bill_data.account_number and result.bill_data.provider_id and result.bill_data.address_text)
        self.assertEqual(len(project_epd_table_candidates(
            PdfReader(private_file).pages[0].extract_text(extraction_mode="layout"))["rows"]), 19)
        self.assertFalse(any(item.code in {"EPD_CHARGE_SUM_MISMATCH", "EPD_ADJUSTMENT_SUM_MISMATCH", "EPD_TOTAL_MISMATCH"}
                             for item in result.issues))
