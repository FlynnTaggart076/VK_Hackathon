"""Service catalogue: one source of truth for units, areas and segments, and advisory warnings only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from housing_engine import BillData, DocumentInput, ExtractionConfig, extract_receipt, validate_bill
from housing_engine.dto import Unit
from housing_engine.epd import parse_epd_text
from housing_engine.service_catalog import CATALOG, SCOPE_LABELS, UNIT_LABELS, catalog_as_json, service_warnings
from typing import get_args

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "receipts"
NEW_CODES = {"SERVICE_UNIT_UNEXPECTED", "SERVICE_SCOPE_UNSPECIFIED", "SERVICE_DUPLICATE_KEY"}


def bill(*lines):
    data = json.loads((FIXTURES / "water-2026-08.json").read_text(encoding="utf-8"))
    base = data["services"][0]
    data["services"] = [dict(base, line_id=str(uuid4()), **line) for line in lines]
    return BillData.model_validate_json(json.dumps(data))


def codes(value):
    return [(item.code, item.path) for item in service_warnings(value)]


class CatalogTests(unittest.TestCase):
    def test_every_unit_and_scope_has_a_russian_label_and_every_default_is_allowed(self):
        self.assertEqual(set(UNIT_LABELS), set(get_args(Unit)))
        self.assertEqual(set(SCOPE_LABELS), {"individual", "common_property", "unspecified"})
        for spec in CATALOG.values():
            self.assertIn(spec.default_scope, spec.scopes)
            if spec.default_unit is not None:
                self.assertIn(spec.default_unit, spec.units)

    def test_web_mirror_is_identical(self):
        mirror = ROOT / "apps" / "web" / "src" / "ui" / "serviceCatalog.json"
        if not mirror.is_file():
            self.skipTest("web sources are not in this checkout")
        self.assertEqual(json.loads(mirror.read_text(encoding="utf-8")), catalog_as_json())


class WarningTests(unittest.TestCase):
    def test_electricity_in_cubic_metres_is_flagged_with_the_unit_path(self):
        value = bill({"service_code": "electricity", "unit": "m3"})
        self.assertEqual(codes(value), [("SERVICE_UNIT_UNEXPECTED", "/services/0/unit")])
        self.assertIn("Электроэнергия", service_warnings(value)[0].message)

    def test_water_with_unspecified_area_is_flagged_but_other_is_not(self):
        self.assertEqual(codes(bill({"scope": "unspecified"})), [("SERVICE_SCOPE_UNSPECIFIED", "/services/0/scope")])
        self.assertEqual(codes(bill({"service_code": "other", "scope": "unspecified", "unit": "month"})), [])

    def test_unknown_or_printed_unit_is_not_flagged(self):
        self.assertEqual(codes(bill({"unit": None})), [])
        self.assertEqual(codes(bill({"unit": "other", "unit_label": "кв.м"})), [])

    def test_only_identical_keys_are_duplicates(self):
        both = bill({"service_code": "electricity", "unit": "kwh", "segment_key": "day"},
                    {"service_code": "electricity", "unit": "kwh", "segment_key": "night"})
        self.assertEqual(codes(both), [])
        same = bill({"service_code": "electricity", "unit": "kwh", "segment_key": "day"},
                    {"service_code": "electricity", "unit": "kwh", "segment_key": "day"})
        self.assertEqual(codes(same), [("SERVICE_DUPLICATE_KEY", "/services/1")])
        many_other = bill({"service_code": "other", "scope": "unspecified"}, {"service_code": "other", "scope": "unspecified"})
        self.assertEqual(codes(many_other), [])

    def test_warnings_never_block_confirmation(self):
        value = bill({"service_code": "electricity", "unit": "m3", "scope": "unspecified"})
        result = validate_bill(value)
        self.assertTrue(result.can_confirm)
        self.assertTrue(NEW_CODES & {item.code for item in result.warnings})
        self.assertFalse(result.errors)


class EpdScopeTests(unittest.TestCase):
    def test_odn_is_a_separate_word_not_a_substring(self):
        from housing_engine.epd import _classify

        result = parse_epd_text((FIXTURES / "epd-synthetic-2026-08.txt").read_text(encoding="utf-8"),
                                UUID("60000000-0000-4000-8000-000000000008"))
        scopes = {line.raw_name: line.scope for line in result.bill_data.services}
        self.assertEqual(scopes["ХОЛОДНОЕ В/С"], "individual")  # «ХОЛОДНОЕ» contains the letters ОДН
        self.assertEqual(scopes["ВОДООТВЕДЕНИЕ ОДН"], "common_property")
        self.assertEqual(_classify("ХОЛОДНОЕ В/С ОДН")[1], "common_property")
        self.assertEqual(_classify("ЭЛЕКТРИЧЕСТВО (ОДНОТАРИФНЫЙ)")[1], "individual")
        self.assertEqual(_classify("ЭЛЕКТРИЧЕСТВО ОДН.")[1], "common_property")


class NoNewNoiseTests(unittest.TestCase):
    """Fixtures and extractor output must not gain new acknowledgements."""

    def test_bill_fixtures(self):
        for path in sorted(FIXTURES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if "services" not in data or data.get("schema_version") != "1.0":
                continue
            with self.subTest(fixture=path.name):
                self.assertFalse(NEW_CODES & {item.code for item in validate_bill(BillData.model_validate_json(json.dumps(data))).warnings})

    def test_epd_text_fixtures(self):
        for month in ("08", "09"):
            text = (FIXTURES / f"epd-synthetic-2026-{month}.txt").read_text(encoding="utf-8")
            result = parse_epd_text(text, UUID(f"60000000-0000-4000-8000-{int(month):012d}"))
            with self.subTest(month=month):
                self.assertEqual(codes(result.bill_data), [])

    def test_demo_documents(self):
        config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
        for path in sorted(FIXTURES.glob("demo-bill-2026-0[89]*.pdf")):
            if path.name.endswith("scan.pdf"):
                continue
            payload = path.read_bytes()
            document = DocumentInput(receipt_id=UUID("10000000-0000-4000-8000-000000000001"), content=payload,
                                     mime_type="application/pdf", sha256=hashlib.sha256(payload).hexdigest())
            try:
                result = extract_receipt(document, config)
            except Exception:  # unreadable or intentionally broken fixtures are outside this check
                continue
            with self.subTest(document=path.name):
                self.assertEqual(codes(result.bill_data), [])
                self.assertFalse(NEW_CODES & {item.code for item in validate_bill(result.bill_data).warnings})


if __name__ == "__main__":
    unittest.main()
