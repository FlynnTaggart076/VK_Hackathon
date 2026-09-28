"""Pure, privacy-preserving arithmetic over a backend-selected city cohort.

The backend is responsible for ownership, consent, deletion, current revision
selection and canonical city classification. This module independently rejects
unconfirmed, synthetic and non-consenting observations, and never returns rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Iterable, Literal


Metric = Literal["charge_amount", "tariff"]
Status = Literal["ok", "insufficient_data", "ambiguous_data"]
_CITY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_PERIOD = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")
_CODES = {"cold_water", "hot_water", "drainage", "electricity", "heating",
          "maintenance", "capital_repair", "waste", "other"}
_UNITS = {"m3", "kwh", "gcal", "m2", "month", "person"}
_SCOPES = {"individual", "common_property"}


@dataclass(frozen=True, slots=True)
class CohortKey:
    city: str  # canonical city slug, never a full address or region
    period: str
    service_code: str
    scope: str
    segment: str | None
    unit: str
    metric: Metric


@dataclass(frozen=True, slots=True)
class CohortObservation:
    contributor_key: str  # opaque backend key; never returned
    city: str
    period: str
    service_code: str
    scope: str
    segment: str | None
    unit: str
    metric: Metric
    dataset_kind: Literal["real", "synthetic"]
    value: Decimal | str
    confirmed: bool
    opted_in: bool


@dataclass(frozen=True, slots=True)
class CohortSummary:
    status: Status
    city: str | None
    period: str | None
    service_code: str | None
    scope: str | None
    segment: str | None
    unit: str | None
    metric: Metric | None
    sample_size: int | None
    average: str | None
    median: str | None
    provenance: str


def _valid_key(key: CohortKey) -> bool:
    return (bool(_CITY.fullmatch(key.city)) and bool(_PERIOD.fullmatch(key.period))
            and key.service_code in _CODES and key.scope in _SCOPES
            and (key.segment is None or bool(_SEGMENT.fullmatch(key.segment)))
            and key.unit in _UNITS and key.metric in ("charge_amount", "tariff")
            and not (key.service_code in {"electricity", "hot_water"} and key.segment is None))


def _parse_value(raw: Decimal | str, metric: Metric) -> Decimal:
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _DECIMAL.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("invalid cohort decimal") from exc
    else:
        raise ValueError("invalid cohort decimal")
    if not value.is_finite() or value.adjusted() > 8 or value.as_tuple().exponent < -6:
        raise ValueError("invalid cohort decimal")
    scale = Decimal("0.01") if metric == "charge_amount" else Decimal("0.000001")
    if value != value.quantize(scale):
        raise ValueError("invalid cohort decimal precision")
    return value


def summarize_cohort(rows: Iterable[CohortObservation], key: CohortKey) -> CohortSummary:
    """Exact cohort mean/median, with a five-contributor disclosure threshold.

    Duplicate rows for one contributor and the same value count once. Two
    different values for one contributor suppress the whole result rather than
    choosing a revision or leaking conflicting personal data.
    """
    provenance = "confirmed_opted_in_real_receipts"
    if not _valid_key(key):
        return CohortSummary("ambiguous_data", None, None, None, None, None, None,
                             None, None, None, None, provenance)

    def summary(status: Status, sample_size: int | None = None,
                average: str | None = None, median: str | None = None) -> CohortSummary:
        return CohortSummary(status, key.city, key.period, key.service_code, key.scope,
                             key.segment, key.unit, key.metric, sample_size, average,
                             median, provenance)

    seen: dict[str, Decimal] = {}
    for row in rows:
        if ((row.city, row.period, row.service_code, row.scope, row.segment, row.unit, row.metric)
                != (key.city, key.period, key.service_code, key.scope, key.segment, key.unit, key.metric)):
            continue
        if row.dataset_kind != "real" or row.confirmed is not True or row.opted_in is not True:
            continue
        if not isinstance(row.contributor_key, str) or not row.contributor_key:
            raise ValueError("invalid opaque contributor key")
        value = _parse_value(row.value, key.metric)
        previous = seen.setdefault(row.contributor_key, value)
        if previous != value:
            return summary("ambiguous_data")
    if len(seen) < 5:
        return summary("insufficient_data")

    values = sorted(seen.values())
    with localcontext() as context:
        context.prec = 50
        average = sum(values, Decimal(0)) / Decimal(len(values))
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / Decimal(2)
        scale = Decimal("0.01") if key.metric == "charge_amount" else Decimal("0.000001")
        average_text = format(average.quantize(scale, rounding=ROUND_HALF_UP), "f")
        median_text = format(median.quantize(scale, rounding=ROUND_HALF_UP), "f")
    return summary("ok", len(values), average_text, median_text)
