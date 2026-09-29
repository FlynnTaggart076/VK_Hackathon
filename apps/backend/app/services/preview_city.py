"""Fixed synthetic city examples for preview; real cohort tables are never read."""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path

from sqlalchemy import select

from app.db.models import Job, Profile, Receipt, ReceiptRevision
from app.db.store import SqlStore
from app.errors import ApiError
from app.services.cohort_store import canonical_city
from app.services.demo_samples import FIXTURES


PROVENANCE = "synthetic_preview_cohort"
COHORT_FILE = FIXTURES / "city-preview-cohort-v1.json"
FIXTURE_SCENARIOS = {
    "city-moscow-water-2026-08": ("moskva", "moscow", "2026-08"),
    "city-moscow-water-2026-09": ("moskva", "moscow", "2026-09"),
    "city-lyubertsy-water-2026-08": ("lyubertsy", "moscow-oblast", "2026-08"),
    "city-lyubertsy-water-2026-09": ("lyubertsy", "moscow-oblast", "2026-09"),
}
SERVICE_LABELS = {"cold_water": "холодной воды"}
CITY_LABELS = {"moskva": "Москва", "lyubertsy": "Люберцы (Московская область)"}
CITY_GENITIVE = {"moskva": "Москвы", "lyubertsy": "Люберец"}
_NUMBER = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")
_VALID_SERVICES = {"cold_water", "hot_water", "drainage", "electricity", "heating",
                   "maintenance", "capital_repair", "waste", "other"}


def _decimal(raw: object, scale: Decimal) -> Decimal:
    if not isinstance(raw, str) or not _NUMBER.fullmatch(raw):
        raise ValueError("invalid synthetic decimal")
    try:
        value = Decimal(raw)
        if not value.is_finite() or value != value.quantize(scale):
            raise ValueError("invalid synthetic precision")
        return value
    except InvalidOperation as exc:
        raise ValueError("invalid synthetic decimal") from exc


def _cohort_values(group: dict, metric: str) -> list[Decimal]:
    rows = group.get("observations")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("synthetic cohort must contain five fixed observations")
    values = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"quantity", "tariff", "charge_amount"}:
            raise ValueError("invalid synthetic observation")
        quantity = _decimal(row["quantity"], Decimal("0.000001"))
        tariff = _decimal(row["tariff"], Decimal("0.000001"))
        charge = _decimal(row["charge_amount"], Decimal("0.01"))
        if (quantity * tariff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != charge:
            raise ValueError("synthetic observation does not reconcile")
        values.append(charge if metric == "charge_amount" else tariff)
    return sorted(values)


def _group_for(fixture_id: str, path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(document, dict) or document.get("schema_version") != "1.0" or
                document.get("kind") != PROVENANCE or not isinstance(document.get("groups"), list)):
            raise ValueError("invalid synthetic cohort file")
        matches = [group for group in document["groups"] if isinstance(group, dict) and
                   group.get("fixture_id") == fixture_id]
        if len(matches) != 1:
            raise ValueError("missing or duplicate synthetic cohort group")
        return matches[0]
    except (OSError, ValueError, UnicodeError):
        raise ApiError(503, "SERVICE_UNAVAILABLE", "Учебная выборка пока недоступна.", retryable=True) from None


def preview_city_comparison(store: SqlStore, user_id: str, receipt_id: str,
                            service_code: str, metric: str, *, cohort_path: Path = COHORT_FILE) -> dict:
    if store.settings.mode != "preview" or not store.settings.preview_auth_enabled:
        raise ApiError(403, "PREVIEW_DISABLED", "Учебное сравнение доступно только в preview.")
    if service_code not in _VALID_SERVICES or metric not in {"charge_amount", "tariff"}:
        raise ApiError(422, "VALIDATION_FAILED", "Неизвестная услуга или показатель сравнения.")

    def result(status: str, *, city=None, period=None, scope=None, segment=None, unit=None,
               size=None, average=None, median=None, receipt_value=None, difference=None,
               percentage=None, comparison=None, explanation=None):
        return {"status": status, "city": city,
                "city_label": CITY_LABELS.get(city), "period": period,
                "service_code": service_code, "scope": scope, "segment_key": segment,
                "unit": unit, "metric": metric, "sample_size": size, "average": average,
                "median": median, "receipt_value": receipt_value,
                "difference_from_average": difference, "difference_percent": percentage,
                "comparison": comparison, "explanation": explanation,
                "provenance": PROVENANCE}

    uid, rid = uuid.UUID(user_id), uuid.UUID(receipt_id)
    with store.Session() as session:
        receipt = session.scalar(select(Receipt).where(Receipt.id == rid, Receipt.user_id == uid))
        if receipt is None:
            raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
        if receipt.status != "confirmed" or receipt.dataset_kind != "synthetic":
            return result("ineligible")
        revision = session.get(ReceiptRevision, (rid, receipt.current_revision))
        profile = session.get(Profile, uid)
        if revision is None or revision.confirmed_at is None or profile is None:
            return result("ineligible")
        jobs = session.scalars(select(Job).where(Job.resource_id == rid, Job.user_id == uid,
                                                 Job.kind == "demo_import")).all()
        fixture_id = next((name for name in FIXTURE_SCENARIOS if any(
            job.operation_key == f"demo-import:{name}:{rid}" for job in jobs)), None)
        if fixture_id is None:
            return result("ineligible")
        expected_city, expected_territory, expected_period = FIXTURE_SCENARIOS[fixture_id]
        bill = revision.bill_data
        if not isinstance(bill, dict) or not isinstance(bill.get("services"), list):
            return result("ineligible")
        period = bill.get("period")
        if profile.territory_id != expected_territory or period != expected_period:
            return result("ineligible")
        city = canonical_city(bill.get("address_text"), profile.territory_id)
        if city is None:
            return result("ambiguous_city", period=period)
        if city != expected_city:
            return result("ineligible", period=period)
        lines = [line for line in bill.get("services", []) if
                 isinstance(line, dict) and line.get("service_code") == service_code]
        if len(lines) != 1 or service_code == "other":
            return result("ineligible", city=city, period=period)
        line = lines[0]
        scope, segment, unit = line.get("scope"), line.get("segment_key"), line.get("unit")
        group = _group_for(fixture_id, cohort_path)
        if (group.get("city"), group.get("territory_id"), group.get("period"),
                group.get("service_code"), group.get("scope"), group.get("segment_key"),
                group.get("unit")) != (city, expected_territory, period, service_code,
                                       scope, segment, unit):
            return result("insufficient_data", city=city, period=period,
                          scope=scope, segment=segment, unit=unit)
        if not isinstance(group.get("observations"), list) or len(group["observations"]) < 5:
            return result("insufficient_data", city=city, period=period,
                          scope=scope, segment=segment, unit=unit)
        scale = Decimal("0.01") if metric == "charge_amount" else Decimal("0.000001")
        try:
            values = _cohort_values(group, metric)
            own = _decimal(line.get(metric), scale)
        except ValueError:
            return result("ineligible", city=city, period=period,
                          scope=scope, segment=segment, unit=unit)
        with localcontext() as context:
            context.prec = 50
            mean = (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
                scale, rounding=ROUND_HALF_UP)
            median_value = values[len(values) // 2]
            difference_value = (own - mean).quantize(scale, rounding=ROUND_HALF_UP)
            percentage = ((difference_value / mean) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP) if mean else None
        comparison = "above" if difference_value > 0 else "below" if difference_value < 0 else "equal"
        metric_label = "начисление" if metric == "charge_amount" else "тариф"
        service_label = SERVICE_LABELS.get(service_code, "услуги")
        relation = "выше среднего" if comparison == "above" else "ниже среднего" if comparison == "below" else "совпадает со средним"
        adjective = "Учебное" if metric == "charge_amount" else "Учебный"
        explanation = (f"{adjective} {metric_label} {service_label} {relation} по "
                       f"{len(values)} вымышленным квитанциям {CITY_GENITIVE[city]} за {period}. "
                       "Это не статистика жителей города.")
        return result("available", city=city, period=period, scope=scope, segment=segment,
                      unit=unit, size=len(values), average=format(mean, "f"),
                      median=format(median_value, "f"), receipt_value=format(own, "f"),
                      difference=format(difference_value, "f"),
                      percentage=format(percentage, "f") if percentage is not None else None,
                      comparison=comparison, explanation=explanation)
