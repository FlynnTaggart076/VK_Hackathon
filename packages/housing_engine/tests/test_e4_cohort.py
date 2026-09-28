"""Cohort arithmetic and minimum disclosure threshold, using synthetic rows."""

import dataclasses
import unittest
from decimal import Decimal

from housing_engine import CohortKey, CohortObservation, summarize_cohort


KEY = CohortKey(city="test-city", period="2026-09", service_code="heating",
                scope="individual", segment=None, unit="gcal", metric="charge_amount")


def row(index: int, value: Decimal | str = "100.00", **changes) -> CohortObservation:
    base = CohortObservation(contributor_key=f"opaque-{index}", city=KEY.city,
                             period=KEY.period, service_code=KEY.service_code,
                             scope=KEY.scope, segment=KEY.segment, unit=KEY.unit,
                             metric=KEY.metric, dataset_kind="real", value=value,
                             confirmed=True, opted_in=True)
    return dataclasses.replace(base, **changes)


class CohortTests(unittest.TestCase):
    def test_five_distinct_real_contributors_mean_median(self):
        result = summarize_cohort([row(i, f"{i * 100}.00") for i in range(1, 6)], KEY)
        self.assertEqual((result.status, result.sample_size, result.average, result.median),
                         ("ok", 5, "300.00", "300.00"))
        self.assertEqual(result.provenance, "confirmed_opted_in_real_receipts")
        public = dataclasses.asdict(result)
        self.assertNotIn("contributor_key", public)
        self.assertNotIn("rows", public)

    def test_four_suppressed_and_deletion_recomputed(self):
        cohort = [row(i) for i in range(1, 6)]
        self.assertEqual(summarize_cohort(cohort, KEY).sample_size, 5)
        for subset in (cohort[:4], cohort[1:]):
            result = summarize_cohort(subset, KEY)
            self.assertEqual(result.status, "insufficient_data")
            self.assertIsNone(result.sample_size)
            self.assertIsNone(result.average)
            self.assertIsNone(result.median)

    def test_identical_duplicate_revision_is_deduplicated(self):
        cohort = [row(i) for i in range(1, 6)] + [row(1)]
        result = summarize_cohort(cohort, KEY)
        self.assertEqual((result.status, result.sample_size), ("ok", 5))
        self.assertEqual(summarize_cohort(cohort[:-1], KEY), result)

    def test_conflicting_duplicate_contributor_suppresses_all_values(self):
        cohort = [row(i) for i in range(1, 6)] + [row(1, "120.00")]
        result = summarize_cohort(cohort, KEY)
        self.assertEqual(result.status, "ambiguous_data")
        self.assertIsNone(result.sample_size)
        self.assertIsNone(result.average)
        self.assertIsNone(result.median)

    def test_exact_city_month_service_scope_segment_unit_and_metric(self):
        key = dataclasses.replace(KEY, service_code="electricity", unit="kwh", segment="day")
        base = [row(i, service_code="electricity", unit="kwh", segment="day") for i in range(1, 6)]
        mismatched = [
            row(6, service_code="electricity", unit="kwh", segment="day", city="other-city"),
            row(7, service_code="electricity", unit="kwh", segment="day", period="2026-08"),
            row(8, service_code="cold_water", unit="kwh", segment="day"),
            row(9, service_code="electricity", unit="kwh", segment="day", scope="common_property"),
            row(10, service_code="electricity", unit="kwh", segment="night"),
            row(11, service_code="electricity", unit="m3", segment="day"),
            row(12, service_code="electricity", unit="kwh", segment="day", metric="tariff"),
        ]
        result = summarize_cohort(base + mismatched, key)
        self.assertEqual((result.status, result.sample_size), ("ok", 5))
        self.assertEqual(summarize_cohort(base[:4] + mismatched, key).status, "insufficient_data")

    def test_synthetic_unconfirmed_and_nonconsenting_rows_excluded(self):
        cohort = [row(i) for i in range(1, 4)] + [
            row(4, dataset_kind="synthetic"), row(5, confirmed=False), row(6, opted_in=False),
        ]
        result = summarize_cohort(cohort, KEY)
        self.assertEqual(result.status, "insufficient_data")
        self.assertIsNone(result.sample_size)
        self.assertEqual(summarize_cohort([row(i, dataset_kind="synthetic") for i in range(1, 6)], KEY).status,
                         "insufficient_data")

    def test_invalid_decimal_and_float_rejected(self):
        for invalid in ("NaN", "Infinity", "1e3", "100.001", Decimal("NaN"),
                        Decimal("Infinity"), 1.25, "1000000000.00"):
            with self.subTest(value=repr(invalid)), self.assertRaises(ValueError):
                summarize_cohort([row(1, invalid)], KEY)
        with self.assertRaises(ValueError):
            summarize_cohort([row(1, contributor_key="")], KEY)

    def test_rounding_at_display_boundary_for_money_and_tariff(self):
        money = summarize_cohort([row(i, "1.00") for i in range(1, 5)] + [row(5, "1.03")], KEY)
        self.assertEqual((money.average, money.median), ("1.01", "1.00"))
        even = summarize_cohort([row(i, f"{i}.00") for i in range(1, 7)], KEY)
        self.assertEqual((even.average, even.median), ("3.50", "3.50"))
        tariff_key = dataclasses.replace(KEY, metric="tariff")
        tariffs = [row(i, "1.000000", metric="tariff") for i in range(1, 5)]
        tariffs.append(row(5, "1.000003", metric="tariff"))
        tariff = summarize_cohort(tariffs, tariff_key)
        self.assertEqual((tariff.average, tariff.median), ("1.000001", "1.000000"))

    def test_ambiguous_key_returns_no_count_or_values(self):
        rows = [row(i) for i in range(1, 6)]
        for invalid in (dataclasses.replace(KEY, city="street 1, apartment 2"),
                        dataclasses.replace(KEY, scope="unspecified"),
                        dataclasses.replace(KEY, unit="other"),
                        dataclasses.replace(KEY, service_code="electricity", segment=None)):
            with self.subTest(key=invalid):
                result = summarize_cohort(rows, invalid)
                self.assertEqual(result.status, "ambiguous_data")
                self.assertIsNone(result.city)
                self.assertIsNone(result.sample_size)
                self.assertIsNone(result.average)


if __name__ == "__main__":
    unittest.main()
