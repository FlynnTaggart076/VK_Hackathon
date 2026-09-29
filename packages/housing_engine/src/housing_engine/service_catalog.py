"""What each service code normally looks like on a bill.

Single source of truth for the allowed units, areas and segments per service.
The web app keeps a JSON mirror (apps/web/src/ui/serviceCatalog.json); a test
keeps the two identical. Deviations are reported only as advisory warnings:
bills confirmed earlier must stay readable for explanation and comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from .dto import BillData, Issue, ServiceCode

UNIT_LABELS = {
    "m3": "м³", "kwh": "кВт·ч", "gcal": "Гкал", "m2": "м²",
    "month": "мес.", "person": "чел.", "other": "другая",
}
SCOPE_LABELS = {
    "individual": "Индивидуальное потребление", "common_property": "Общедомовые нужды", "unspecified": "Не указана",
}
_BOTH_SCOPES = ("individual", "common_property")


@dataclass(frozen=True)
class ServiceSpec:
    code: str
    label: str
    units: tuple[str, ...]
    default_unit: str | None
    scopes: tuple[str, ...]
    default_scope: str
    segments: tuple[tuple[str, str], ...] = ()


CATALOG: dict[str, ServiceSpec] = {spec.code: spec for spec in (
    ServiceSpec("cold_water", "Холодная вода", ("m3",), "m3", _BOTH_SCOPES, "individual"),
    ServiceSpec("hot_water", "Горячая вода", ("m3", "gcal"), "m3", _BOTH_SCOPES, "individual",
                (("carrier", "Носитель"), ("energy", "Энергия"))),
    ServiceSpec("drainage", "Водоотведение", ("m3",), "m3", _BOTH_SCOPES, "individual"),
    ServiceSpec("electricity", "Электроэнергия", ("kwh",), "kwh", _BOTH_SCOPES, "individual",
                (("day", "День"), ("night", "Ночь"))),
    ServiceSpec("heating", "Отопление", ("gcal", "m2"), "gcal", _BOTH_SCOPES, "individual"),
    ServiceSpec("maintenance", "Содержание жилья", ("m2",), "m2", _BOTH_SCOPES, "individual"),
    ServiceSpec("capital_repair", "Капитальный ремонт", ("m2",), "m2", ("individual",), "individual"),
    ServiceSpec("waste", "Обращение с ТКО", ("person", "m2"), "person", ("individual",), "individual"),
    ServiceSpec("other", "Прочее", ("m3", "kwh", "gcal", "m2", "month", "person", "other"), None,
                ("unspecified", "individual", "common_property"), "unspecified"),
)}

assert set(CATALOG) == set(get_args(ServiceCode)), "service catalog must cover every ServiceCode"


def catalog_as_json() -> dict:
    """Shape of apps/web/src/ui/serviceCatalog.json."""
    return {"services": [{
        "code": spec.code, "label": spec.label, "units": list(spec.units), "default_unit": spec.default_unit,
        "scopes": list(spec.scopes), "default_scope": spec.default_scope,
        "segments": [{"key": key, "label": label} for key, label in spec.segments],
    } for spec in CATALOG.values()]}


def _key(line) -> tuple:
    return (line.service_code, line.scope, line.segment_key, line.unit)


def service_warnings(bill: BillData) -> list[Issue]:
    """Advisory checks that a line's unit, area and identity match its service code."""
    result: list[Issue] = []
    seen: set[tuple] = set()
    for index, line in enumerate(bill.services):
        spec = CATALOG[line.service_code]
        path = f"/services/{index}"
        if line.unit not in (None, "other") and line.unit not in spec.units:
            result.append(Issue(
                code="SERVICE_UNIT_UNEXPECTED", severity="warning", path=path + "/unit",
                message=f"Единица «{UNIT_LABELS[line.unit]}» необычна для услуги «{spec.label}»; проверьте её по квитанции."))
        if line.service_code != "other" and line.scope == "unspecified":
            result.append(Issue(
                code="SERVICE_SCOPE_UNSPECIFIED", severity="warning", path=path + "/scope",
                message=f"Для услуги «{spec.label}» не указано, идёт ли начисление по квартире или на общедомовые нужды."))
        if line.service_code != "other":
            key = _key(line)
            if key in seen:
                result.append(Issue(
                    code="SERVICE_DUPLICATE_KEY", severity="warning", path=path,
                    message=(f"Есть ещё одна строка «{spec.label}» с той же областью, сегментом и единицей; "
                             "сравнение с другими месяцами и с городом может быть неоднозначным.")))
            seen.add(key)
    return result
