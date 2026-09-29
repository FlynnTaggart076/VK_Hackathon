"""Validate the isolated, explicitly artificial city-preview dataset."""

import json
import unittest
from decimal import Decimal
from pathlib import Path
from statistics import median

from jsonschema import Draft202012Validator, FormatChecker
from housing_engine import BillData, validate_bill
from housing_engine.receipts import calculate_bill


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "receipts"
COHORT = FIXTURES / "city-preview-cohort-v1.json"
SCHEMA = FIXTURES.parents[1] / "contracts" / "engine" / "v1" / "BillData.schema.json"
EXPECTED = {
    ("moskva", "2026-08"): ("moscow", "40.000000", "256.00", "240.00", "200.00"),
    ("moskva", "2026-09"): ("moscow", "45.000000", "342.00", "315.00", "270.00"),
    ("lyubertsy", "2026-08"): ("moscow-oblast", "38.000000", "243.20", "228.00", "190.00"),
    ("lyubertsy", "2026-09"): ("moscow-oblast", "42.000000", "319.20", "294.00", "252.00"),
}


class SyntheticCityFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(COHORT.read_text(encoding="utf-8"))

    def test_distinct_city_receipts_validate_and_reconcile(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        accounts = {}
        providers = {}
        for group in self.dataset["groups"]:
            with self.subTest(fixture_id=group["fixture_id"]):
                path = FIXTURES / f"{group['fixture_id']}.json"
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertFalse(list(validator.iter_errors(raw)))
                bill = BillData.model_validate_json(path.read_text(encoding="utf-8"))
                line, = bill.services
                result = validate_bill(bill)
                self.assertTrue(result.can_confirm)
                self.assertEqual(result.reconciliation_status, "matched")
                self.assertFalse(result.errors)
                self.assertFalse(result.warnings)
                self.assertEqual(calculate_bill(bill).current_charges, line.charge_amount)
                self.assertEqual(bill.document_total_due, line.charge_amount)
                self.assertEqual(bill.period, group["period"])
                self.assertEqual((line.service_code, line.scope, line.segment_key, line.unit),
                                 (group["service_code"], group["scope"], group["segment_key"], group["unit"]))
                own = group["observations"][1]
                self.assertEqual((line.quantity, line.tariff, line.charge_amount),
                                 (own["quantity"], own["tariff"], own["charge_amount"]))
                if group["city"] == "moskva":
                    self.assertTrue(bill.address_text.startswith("г. Москва,"))
                else:
                    self.assertIn("г. Люберцы,", bill.address_text)
                    self.assertIn("Московская область", bill.address_text)
                accounts.setdefault(group["city"], set()).add(bill.account_number)
                providers.setdefault(group["city"], set()).add(bill.provider_id)
        self.assertEqual([len(values) for values in accounts.values()], [1, 1])
        self.assertEqual([len(values) for values in providers.values()], [1, 1])
        self.assertEqual(len(set.union(*accounts.values())), 2)

    def test_cohort_has_exact_disjoint_keys_and_five_arithmetically_valid_entries(self):
        self.assertEqual((self.dataset["schema_version"], self.dataset["kind"]),
                         ("1.0", "synthetic_preview_cohort"))
        groups = self.dataset["groups"]
        self.assertEqual(len(groups), 4)
        self.assertEqual({(g["city"], g["period"]) for g in groups}, set(EXPECTED))
        self.assertEqual(len({g["fixture_id"] for g in groups}), 4)
        for group in groups:
            key = (group["city"], group["period"])
            territory, tariff, average, middle, own_charge = EXPECTED[key]
            with self.subTest(key=key):
                self.assertEqual(set(group), {"fixture_id", "city", "territory_id", "period",
                                               "service_code", "scope", "segment_key", "unit", "observations"})
                self.assertEqual(group["territory_id"], territory)
                self.assertEqual((group["service_code"], group["scope"], group["segment_key"], group["unit"]),
                                 ("cold_water", "individual", None, "m3"))
                self.assertEqual(len(group["observations"]), 5)
                charges = []
                for observation in group["observations"]:
                    self.assertEqual(set(observation), {"quantity", "tariff", "charge_amount"})
                    self.assertEqual(observation["tariff"], tariff)
                    calculated = Decimal(observation["quantity"]) * Decimal(observation["tariff"])
                    self.assertEqual(Decimal(observation["charge_amount"]), calculated)
                    charges.append(Decimal(observation["charge_amount"]))
                self.assertEqual(f"{sum(charges) / len(charges):.2f}", average)
                self.assertEqual(f"{median(charges):.2f}", middle)
                self.assertEqual(group["observations"][1]["charge_amount"], own_charge)

    def test_generic_demo_remains_cityless_and_separate(self):
        city_ids = {group["fixture_id"] for group in self.dataset["groups"]}
        for period in ("2026-08", "2026-09"):
            bill = BillData.model_validate_json((FIXTURES / f"water-{period}.json").read_text(encoding="utf-8"))
            self.assertTrue(bill.address_text.startswith("Учебный город,"))
            self.assertNotIn(f"water-{period}", city_ids)


if __name__ == "__main__":
    unittest.main()
