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
from housing_engine.dto import Adjustment, BillData, ConfirmedBill, ReceiptRef, ServiceLine


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
        self.assertIn("IDENTITY_ACK_REQUIRED", [issue.code for issue in result.issues])
        self.assertIsNone(result.delta_current_charges)
        self.assertIsNone(result.delta_adjustments)
        self.assertIsNone(result.delta_total_due)
        self.assertIsNone(result.unexplained_delta)
        self.assertEqual(result.lines, [])
        self.assertEqual(result.settlement_deltas, [])
        self.assertEqual(result.actions[0].target, "comparison")
        self.assertEqual(result.actions[0].requires, ["identity_acknowledged"])
        self.assertEqual(compare_receipts(request(old, new, True), KNOWLEDGE).status, "complete")

    def test_mismatched_account_and_same_month_block(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        changed = new.model_copy(update={"bill_data": new.bill_data.model_copy(update={"account_number": "000124"})})
        with self.assertRaises(EngineError) as raised:
            compare_receipts(request(old, changed, True), KNOWLEDGE)
        self.assertEqual(raised.exception.code, "INCOMPARABLE_RECEIPTS")

    def test_volume_tariff_rounding_and_nonadjacent_period(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        line = new.bill_data.services[0]
        for quantity, tariff, charge, expected in (
            ("7.000000", "40.000000", "280.00", ("80.00", "0.00", "0.00")),
            ("5.000000", "42.000000", "210.00", ("0.00", "10.00", "0.00")),
            ("5.000000", "40.001000", "200.01", ("0.00", "0.01", "0.00")),
        ):
            with self.subTest(quantity=quantity, tariff=tariff):
                changed_line = line.model_copy(update={"quantity": quantity, "tariff": tariff, "charge_amount": charge})
                bill = new.bill_data.model_copy(update={
                    "services": [changed_line], "document_current_charges": charge,
                    "document_total_due": charge,
                    "settlement": new.bill_data.settlement.model_copy(update={"document_closing_balance": charge}),
                })
                result = compare_receipts(request(old, new.model_copy(update={"bill_data": bill}), True), KNOWLEDGE)
                row = result.lines[0]
                self.assertEqual((row.quantity_effect, row.tariff_effect, row.rounding_effect), expected)
                self.assertEqual(Decimal(row.quantity_effect) + Decimal(row.tariff_effect) + Decimal(row.rounding_effect), Decimal(row.delta))
        far_bill = new.bill_data.model_copy(update={"period": "2026-11"})
        far = compare_receipts(request(old, new.model_copy(update={"bill_data": far_bill}), True), KNOWLEDGE)
        self.assertIn("NONADJACENT_PERIODS", [item.code for item in far.issues])

    def test_adjustment_payment_200_to_190_is_not_double_counted(self):
        expected = json.loads((FIXTURES / "e3-settlement-comparison.json").read_text(encoding="utf-8"))["expected"]
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        adjustment = Adjustment(adjustment_id=UUID("50000000-0000-4000-8000-000000000001"), label="Учебный перерасчёт", amount="-50.00", service_line_id=None, related_period="2026-08")
        bill = new.bill_data.model_copy(update={
            "adjustments": [adjustment], "document_current_charges": "220.00", "document_total_due": "190.00",
            "settlement": new.bill_data.settlement.model_copy(update={"payments_credited": "30.00", "document_closing_balance": "190.00"}),
        })
        result = compare_receipts(request(old, new.model_copy(update={"bill_data": bill}), True), KNOWLEDGE)
        self.assertEqual(result.status, "complete")
        self.assertEqual((result.delta_current_charges, result.delta_adjustments, result.delta_total_due, result.unexplained_delta),
                         (expected["delta_current_charges"], expected["delta_adjustments"], expected["delta_total_due"], expected["unexplained_delta"]))
        self.assertEqual({item.code: item.contribution for item in result.settlement_deltas}["payments_credited"], expected["payments_contribution"])

    def test_credit_clamp_and_unknown_payment_stay_separate(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        old_bill = old.bill_data.model_copy(update={
            "document_total_due": "0.00",
            "settlement": old.bill_data.settlement.model_copy(update={"opening_balance": "-300.00", "document_closing_balance": "-100.00"}),
        })
        new_bill = new.bill_data.model_copy(update={
            "document_total_due": "0.00",
            "settlement": new.bill_data.settlement.model_copy(update={"opening_balance": "-300.00", "document_closing_balance": "-30.00"}),
        })
        compared = compare_receipts(request(old.model_copy(update={"bill_data": old_bill}), new.model_copy(update={"bill_data": new_bill}), True), KNOWLEDGE)
        self.assertEqual(compared.delta_current_charges, "70.00")
        self.assertEqual(compared.delta_total_due, "0.00")
        self.assertEqual({item.code: item.contribution for item in compared.settlement_deltas}["credit_clamp"], "-70.00")
        self.assertEqual(compared.unexplained_delta, "0.00")
        unknown = new_bill.model_copy(update={"settlement": new_bill.settlement.model_copy(update={"payments_credited": None})})
        partial = compare_receipts(request(old, new.model_copy(update={"bill_data": unknown}), True), KNOWLEDGE)
        self.assertEqual(partial.status, "partial")
        self.assertIsNone(partial.unexplained_delta)
        self.assertIsNone({item.code: item.contribution for item in partial.settlement_deltas}["payments_credited"])

    def test_other_unit_mismatch_and_ambiguous_lines(self):
        old, new = from_json("2026-08", 1), from_json("2026-09", 2)
        line = new.bill_data.services[0]
        other = line.model_copy(update={"service_code": "other", "raw_name": "Неизвестная строка", "charge_amount": "50.00", "calculation_kind": "document_amount"})
        bill = new.bill_data.model_copy(update={"services": [other], "document_current_charges": "50.00", "document_total_due": "50.00", "settlement": new.bill_data.settlement.model_copy(update={"document_closing_balance": "50.00"})})
        compared = compare_receipts(request(old, new.model_copy(update={"bill_data": bill}), True), KNOWLEDGE)
        self.assertEqual(compared.delta_current_charges, "-150.00")
        self.assertEqual({item.match_status for item in compared.lines}, {"added", "removed"})
        mismatched = line.model_copy(update={"unit": "kwh"})
        bill2 = new.bill_data.model_copy(update={"services": [mismatched]})
        incompatible = compare_receipts(request(old, new.model_copy(update={"bill_data": bill2}), True), KNOWLEDGE)
        self.assertEqual(incompatible.lines[0].match_status, "incompatible")
        self.assertIsNone(incompatible.lines[0].quantity_effect)
        duplicate = line.model_copy(update={"line_id": UUID("50000000-0000-4000-8000-000000000002")})
        bill3 = new.bill_data.model_copy(update={"services": [line, duplicate], "document_current_charges": "540.00", "document_total_due": "540.00", "settlement": new.bill_data.settlement.model_copy(update={"document_closing_balance": "540.00"})})
        ambiguous = compare_receipts(request(old, new.model_copy(update={"bill_data": bill3}), True), KNOWLEDGE)
        self.assertEqual(ambiguous.status, "partial")
        self.assertTrue(all(item.match_status == "ambiguous" for item in ambiguous.lines))
        self.assertIn("AMBIGUOUS_SERVICE_LINES", [item.code for item in ambiguous.issues])
        with self.assertRaises(EngineError) as raised:
            compare_receipts(request(old, old, True), KNOWLEDGE)
        self.assertEqual(raised.exception.code, "INCOMPARABLE_RECEIPTS")


if __name__ == "__main__":
    unittest.main()
