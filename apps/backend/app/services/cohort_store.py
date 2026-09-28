"""Consent-gated derived city cohort values; no cross-user source data leaves this module."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import delete, select

from app.db.models import Profile, Receipt, ReceiptCohortLine, ReceiptRevision
from app.db.store import SqlStore, aware, now
from app.errors import ApiError
from housing_engine import CohortKey, CohortObservation, summarize_cohort


_CITY_TOKEN = re.compile(r"(?:^|[,;]\s*)(?:г\.?|город)\s*([А-ЯЁа-яё-]{2,})", re.IGNORECASE)
_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ("a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n",
     "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"),
))


def canonical_city(address: str | None, territory_id: str | None) -> str | None:
    """Require an explicit unambiguous city; a region is never a city cohort."""
    if not isinstance(address, str) or territory_id not in {"moscow", "moscow-oblast"}:
        return None
    names = [name.lower() for name in _CITY_TOKEN.findall(address)]
    if territory_id == "moscow" and re.match(r"^\s*москва\s*[,;]", address, re.IGNORECASE):
        names.append("москва")
    if len(set(names)) != 1:
        return None
    name = names[0]
    if (territory_id == "moscow") != (name == "москва"):
        return None
    slug = "".join(_TRANSLIT.get(char, char) for char in name)
    return slug if re.fullmatch(r"[a-z][a-z-]{1,63}", slug) else None


def _bill_rows(receipt: Receipt, bill: dict, profile: Profile) -> list[ReceiptCohortLine]:
    city = canonical_city(bill.get("address_text"), profile.territory_id)
    period = bill.get("period")
    if city is None or not isinstance(period, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", period):
        return []
    rows = []
    for line in bill.get("services", []):
        if (line.get("service_code") == "other" or
                line.get("scope") not in {"individual", "common_property"} or
                line.get("unit") not in {"m3", "kwh", "gcal", "m2", "month", "person"} or
                not line.get("line_id")):
            continue
        if line.get("service_code") in {"hot_water", "electricity"} and not line.get("segment_key"):
            continue
        for metric in ("charge_amount", "tariff"):
            value = line.get(metric)
            if value is None:
                continue
            rows.append(ReceiptCohortLine(
                id=uuid.uuid4(), receipt_id=receipt.id, user_id=receipt.user_id,
                line_id=uuid.UUID(str(line["line_id"])), city=city, period=period,
                service_code=line["service_code"], scope=line["scope"],
                segment=line.get("segment_key"), unit=line["unit"], metric=metric,
                value=value, created_at=now(),
            ))
    return rows


def index_confirmed_receipt(session, receipt: Receipt, bill: dict, profile: Profile) -> None:
    session.execute(delete(ReceiptCohortLine).where(ReceiptCohortLine.receipt_id == receipt.id))
    if receipt.status == "confirmed" and receipt.dataset_kind == "user_provided" and profile.aggregate_opt_in:
        session.add_all(_bill_rows(receipt, bill, profile))


def set_aggregate_consent(store: SqlStore, user_id: str, enabled: bool) -> dict:
    uid = uuid.UUID(user_id)
    with store.Session.begin() as session:
        profile = session.get(Profile, uid, with_for_update=True)
        if profile is None:
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        if enabled and profile.privacy_notice_version != store.settings.privacy_notice_version:
            raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальные правила обработки данных.")
        profile.aggregate_opt_in = enabled
        session.execute(delete(ReceiptCohortLine).where(ReceiptCohortLine.user_id == uid))
        if enabled:
            rows = session.execute(select(Receipt, ReceiptRevision).join(
                ReceiptRevision,
                (ReceiptRevision.receipt_id == Receipt.id) &
                (ReceiptRevision.revision == Receipt.current_revision),
            ).where(Receipt.user_id == uid, Receipt.status == "confirmed",
                    Receipt.dataset_kind == "user_provided",
                    ReceiptRevision.confirmed_at.is_not(None))).all()
            for receipt, revision in rows:
                index_confirmed_receipt(session, receipt, revision.bill_data, profile)
        return {"aggregate_opt_in": profile.aggregate_opt_in}


def city_comparison(store: SqlStore, user_id: str, receipt_id: str,
                    service_code: str, metric: str) -> dict:
    if metric not in {"charge_amount", "tariff"}:
        raise ApiError(422, "VALIDATION_FAILED", "Неизвестная метрика сравнения.")
    if service_code not in {"cold_water", "hot_water", "drainage", "electricity", "heating",
                            "maintenance", "capital_repair", "waste", "other"}:
        raise ApiError(422, "VALIDATION_FAILED", "Неизвестная услуга.")
    provenance = "confirmed_opted_in_real_receipts"

    def result(status, *, city=None, period=None, unit=None, size=None, average=None, median=None):
        return {"status": status, "city": city, "period": period, "service_code": service_code,
                "unit": unit, "metric": metric, "sample_size": size, "average": average,
                "median": median, "provenance": provenance}

    uid, rid = uuid.UUID(user_id), uuid.UUID(receipt_id)
    with store.Session() as session:
        profile = session.get(Profile, uid)
        receipt = session.scalar(select(Receipt).where(Receipt.id == rid, Receipt.user_id == uid))
        if receipt is None:
            raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
        if receipt.status != "confirmed" or receipt.dataset_kind != "user_provided":
            return result("ineligible")
        revision = session.get(ReceiptRevision, (rid, receipt.current_revision))
        if revision is None or revision.confirmed_at is None:
            return result("ineligible")
        bill = revision.bill_data
        if service_code == "other":
            return result("ineligible")
        city = canonical_city(bill.get("address_text"), profile.territory_id)
        if city is None:
            return result("ambiguous_city")
        period = bill.get("period")
        lines = [line for line in bill.get("services", []) if line.get("service_code") == service_code]
        if len(lines) != 1 or not isinstance(period, str):
            return result("ineligible", city=city, period=period)
        line = lines[0]
        key = CohortKey(city=city, period=period, service_code=service_code,
                        scope=line.get("scope"), segment=line.get("segment_key"),
                        unit=line.get("unit"), metric=metric)
        candidates = session.scalars(select(ReceiptCohortLine).join(
            Profile, Profile.user_id == ReceiptCohortLine.user_id).join(
            Receipt, Receipt.id == ReceiptCohortLine.receipt_id).where(
            ReceiptCohortLine.city == city, ReceiptCohortLine.period == period,
            ReceiptCohortLine.service_code == service_code,
            ReceiptCohortLine.scope == line.get("scope"),
            ReceiptCohortLine.segment == line.get("segment_key"),
            ReceiptCohortLine.unit == line.get("unit"),
            ReceiptCohortLine.metric == metric,
            Profile.aggregate_opt_in.is_(True), Receipt.status == "confirmed",
            Receipt.dataset_kind == "user_provided",
        )).all()
        observations = [CohortObservation(
            contributor_key=str(row.user_id), city=row.city, period=row.period,
            service_code=row.service_code, scope=row.scope, segment=row.segment,
            unit=row.unit, metric=row.metric, dataset_kind="real", value=row.value,
            confirmed=True, opted_in=True,
        ) for row in candidates]
        summary = summarize_cohort(observations, key)
        if summary.status == "ambiguous_data":
            return result("ineligible", city=city, period=period, unit=line.get("unit"))
        if summary.status != "ok":
            return result("insufficient_data", city=city, period=period, unit=line.get("unit"))
        return result("available", city=city, period=period, unit=line.get("unit"),
                      size=summary.sample_size, average=summary.average, median=summary.median)
