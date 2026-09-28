"""Conservative parser for the text-bearing, one-page Moscow Oblast EPD layout.

Only the main charge table is parsed. The reference meter table, payment
recipient details and voluntary insurance are deliberately outside its scope.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5

from .dto import BillData, ExtractionResult, FieldEvidence, Issue
from .receipts import money, rounded, validate_bill


EPD_TEMPLATE_ID = "mos-oblast-epd-v1"
_MONTHS = {
    "январь": "01", "февраль": "02", "март": "03", "апрель": "04",
    "май": "05", "июнь": "06", "июль": "07", "август": "08",
    "сентябрь": "09", "октябрь": "10", "ноябрь": "11", "декабрь": "12",
}
_DECIMAL = re.compile(r"^-?(?:[0-9]{1,3}(?: [0-9]{3})*|[0-9]+)(?:[.,][0-9]{1,6})?$")


def is_epd(text: str) -> bool:
    head = text[:4000].casefold()
    return "единый платежный документ" in head and "жилищно-коммунальные" in head and "виды услуг" in text.casefold()


def _number(value: str, *, amount: bool = False) -> str | None:
    value = value.strip().replace("\u00a0", " ").replace("\u202f", " ")
    if not _DECIMAL.fullmatch(value) or (amount and not re.search(r"[.,][0-9]{2}$", value)):
        return None
    try:
        number = Decimal(value.replace(" ", "").replace(",", "."))
        if abs(number) >= 1_000_000_000:
            return None
        return money(number) if amount else format(number, "f")
    except InvalidOperation:
        return None


def _classify(name: str) -> tuple[str, str, str]:
    upper = name.upper()
    scope = "common_property" if "ОДН" in upper else "individual"
    if "ВЗНОС НА КАПИТАЛЬНЫЙ" in upper:
        return "capital_repair", scope, "Капитальный ремонт"
    if "СОДЕРЖАНИЕ ЖИЛОГО" in upper:
        return "maintenance", scope, "Содержание жилья"
    if "ВОДООТВЕДЕНИ" in upper:
        return "drainage", scope, "Водоотведение"
    if "ГОРЯЧЕЕ В/С" in upper:
        label = "Горячая вода: энергия" if "ЭНЕРГИЯ" in upper else "Горячая вода: носитель"
        return "hot_water", scope, label
    if "ХОЛОДНОЕ В/С" in upper:
        return "cold_water", scope, "Холодная вода"
    if "ЭЛЕКТРО" in upper or "ЭЛЕКТРИ" in upper:
        label = "Электричество: ночь" if "НОЧЬ" in upper else "Электричество: день"
        return "electricity", scope, label
    if "ОТОПЛЕНИ" in upper:
        return "heating", scope, "Отопление"
    if "ОБРАЩЕНИЕ С ТКО" in upper:
        return "waste", scope, "Обращение с ТКО"
    for needle, label in (("ВИДЕОНАБЛЮДЕНИЕ", "Видеонаблюдение"),
                          ("КОНСЬЕРЖ", "Консьерж"),
                          ("ТЕЛЕВИДЕНИЕ", "Кабельное телевидение")):
        if needle in upper:
            return "other", "unspecified", label
    return "other", "unspecified", "Другая услуга"


def _segment(name: str) -> str | None:
    upper = name.upper()
    if "ЭЛЕКТРО" in upper or "ЭЛЕКТРИ" in upper:
        if "ДЕНЬ" in upper:
            return "day"
        if "НОЧЬ" in upper:
            return "night"
    if "ГОРЯЧЕЕ В/С" in upper:
        if "НОСИТЕЛЬ" in upper:
            return "carrier"
        if "ЭНЕРГИЯ" in upper:
            return "energy"
    return None


def _unit(label: str) -> tuple[str, str | None]:
    normalized = label.casefold().replace(" ", "").replace(".", "")
    if normalized in {"кубм", "м3", "м³"}:
        return "m3", None
    if normalized in {"квм", "м2", "м²"}:
        return "m2", None
    if normalized in {"гкал"}:
        return "gcal", None
    if normalized in {"квтч", "квт*ч"}:
        return "kwh", None
    if normalized in {"мес", "месяц"}:
        return "month", None
    if normalized in {"чел", "человек"}:
        return "person", None
    return "other", label[:200]


def _parts(line: str) -> list[str]:
    return [part.strip() for part in re.split(r" {2,}", line.strip()) if part.strip()]


def _table_bounds(lines: list[str]) -> tuple[int | None, int | None]:
    start = next((i + 1 for i, line in enumerate(lines) if "Виды услуг" in line and "Объем" in " ".join(lines[max(0, i - 1):i + 1])), None)
    end = next((i for i, line in enumerate(lines) if "без учета добровольного страхования" in line.casefold() and "Всего за" in line), None)
    if start is None or end is None or end <= start or end - start > 70:
        return None, None
    return start, end


def parse_epd_text(text: str, receipt_id: UUID, *, engine_version: str = "0.1.0") -> ExtractionResult:
    """Parse layout-preserving PDF text; never infer absent numeric cells."""
    lines = text.splitlines()
    evidence: list[FieldEvidence] = []
    issues: list[Issue] = []

    def add(path: str, source_line: str | None, *, review: bool = True) -> None:
        if source_line is not None:
            evidence.append(FieldEvidence(
                path=path, source="pdf_text", page_number=1, bbox=None,
                source_text=source_line.strip()[:500], needs_review=review,
                reason="Проверьте значение и колонку ЕПД." if review else None,
            ))

    if not is_epd(text):
        return ExtractionResult(
            outcome="manual_required", bill_data=_empty_epd_bill(), field_evidence=[],
            issues=[Issue(code="TEMPLATE_UNKNOWN", severity="warning", path=None, message="Макет ЕПД не распознан.")],
            template_id=None, engine_version=engine_version,
        )
    header = lines[:min(25, len(lines))]
    period = None
    for line in header:
        match = re.search(r"\bза\s+([А-ЯЁа-яё]+)\s+([0-9]{4})\s*г?\.?", line, re.I)
        if match and match.group(1).casefold() in _MONTHS:
            period = f"{match.group(2)}-{_MONTHS[match.group(1).casefold()]}"
            add("/period", line, review=False)
            break

    issuer = account = address = provider_id = None
    for line in header:
        if "ВАША УПРАВЛЯЮЩАЯ ОРГАНИЗАЦИЯ:" in line.upper():
            value = re.split(r"Юридический адрес УК:", line, maxsplit=1, flags=re.I)[0]
            value = value.split(":", 1)[-1].strip()
            if 2 <= len(value) <= 200:
                issuer = value
                add("/issuer_name", line)
        if "Лицевой счет:" in line:
            segment = re.split(r"Просим", line, maxsplit=1, flags=re.I)[0]
            value = re.sub(r"\s+", "", segment.split(":", 1)[-1])
            if re.fullmatch(r"[0-9]{5,20}(?:-[0-9]{1,8})?", value):
                account = value
                add("/account_number", line)
        if re.match(r"\s*Адрес:\s*", line, re.I):
            value = line.split(":", 1)[-1].strip()
            if 8 <= len(value) <= 500 and "МОСКОВСКАЯ ОБЛ" in value.upper():
                address = value
                add("/address_text", line)
    # The first INN following the management-organization header belongs to
    # the issuer, not the payment recipient on the next paragraph.
    issuer_start = next((i for i, line in enumerate(header) if "ВАША УПРАВЛЯЮЩАЯ ОРГАНИЗАЦИЯ:" in line.upper()), None)
    if issuer_start is not None and issuer is not None:
        for line in header[issuer_start:issuer_start + 3]:
            match = re.search(r"\bИНН\s*([0-9]{10})\b", line, re.I)
            if match:
                provider_id = "inn:" + match.group(1)
                add("/provider_id", line)
                break

    start, end = _table_bounds(lines)
    if start is None or end is None:
        issues.append(Issue(code="EPD_TABLE_BOUNDS", severity="error", path="/services", message="Границы основной таблицы не определены."))
        return ExtractionResult(outcome="manual_required", bill_data=_empty_epd_bill(), field_evidence=evidence,
                                issues=issues, template_id=EPD_TEMPLATE_ID, engine_version=engine_version)

    services: list[dict] = []
    adjustments: list[dict] = []
    parsed_rows = []
    for line in lines[start:end]:
        parts = _parts(line)
        if parts and "ДОБРОВОЛЬНОЕ СТРАХОВАНИЕ" in parts[0].upper():
            continue
        if len(parts) == 1 and services and ("ДВУХТАРИФНЫЙ ПУ" in parts[0] or parts[0] == "АНТЕННА)"):
            services[-1]["raw_name"] += " " + parts[0]
            add(f"/services/{len(services) - 1}/raw_name", line)
            continue
        if len(parts) < 2 or not any(ch.isdigit() for ch in " ".join(parts[1:])):
            continue
        if len(parts) != 9:
            issues.append(Issue(code="EPD_ROW_UNPARSED", severity="warning", path="/services", message="Строка начисления требует ручного разбора."))
            continue
        raw_name, raw_qty, raw_unit, raw_tariff, raw_charge, raw_adjustment, _raw_debt, _raw_paid, _raw_total = parts
        if len(raw_name) > 160:
            issues.append(Issue(code="EPD_ROW_UNPARSED", severity="warning", path="/services", message="Название строки слишком длинное."))
            continue
        index = len(services)
        code, scope, label = _classify(raw_name)
        unit, unit_label = _unit(raw_unit)
        quantity = _number(raw_qty)
        tariff = _number(raw_tariff)
        charge = _number(raw_charge, amount=True)
        adjustment = _number(raw_adjustment, amount=True)
        for field, value in (("quantity", quantity), ("tariff", tariff), ("charge_amount", charge), ("adjustment", adjustment)):
            if value is None:
                issues.append(Issue(code="EPD_COLUMN_AMBIGUOUS", severity="warning", path=f"/services/{index}/{field}", message="Число или колонка требуют подтверждения."))
        line_id = uuid5(receipt_id, f"{EPD_TEMPLATE_ID}:service:{index}")
        product = quantity is not None and tariff is not None and charge is not None and abs(rounded(Decimal(quantity) * Decimal(tariff)) - Decimal(charge)) <= Decimal("0.01")
        kind = "simple_product" if product else "document_amount"
        if not product and quantity is not None and tariff is not None and charge is not None:
            issues.append(Issue(code="EPD_FORMULA_UNSUPPORTED", severity="warning", path=f"/services/{index}", message="Начисление не равно простому произведению объёма и тарифа."))
        if label == "Другая услуга":
            issues.append(Issue(code="SERVICE_UNMAPPED", severity="warning", path=f"/services/{index}/service_code", message="Название услуги сохранено как other."))
        services.append({
            "line_id": line_id, "raw_name": raw_name, "service_code": code, "scope": scope,
            "unit": unit, "unit_label": unit_label, "quantity": quantity, "tariff": tariff,
            "charge_amount": charge, "supplier_key": None, "segment_key": _segment(raw_name),
            "calculation_kind": kind,
        })
        for field in ("raw_name", "service_code", "scope", "unit", "quantity", "tariff", "charge_amount", "calculation_kind"):
            add(f"/services/{index}/{field}", line, review=field in {"service_code", "scope", "unit", "quantity", "tariff", "charge_amount"})
        if adjustment is None or Decimal(adjustment) != 0:
            adjustment_index = len(adjustments)
            adjustments.append({
                "adjustment_id": uuid5(receipt_id, f"{EPD_TEMPLATE_ID}:adjustment:{index}"),
                "label": "Перерасчет", "amount": adjustment,
                "service_line_id": line_id, "related_period": None,
            })
            add(f"/adjustments/{adjustment_index}/amount", line)
            add(f"/adjustments/{adjustment_index}/service_line_id", line)
        parsed_rows.append((raw_charge, raw_adjustment))

    totals = _parts(lines[end])
    base_total = adj_total = debt = paid = row_total = None
    if len(totals) == 7:
        base_total, adj_total, debt, paid, row_total = (_number(value, amount=True) for value in totals[2:])
    else:
        issues.append(Issue(code="EPD_TOTAL_COLUMNS", severity="warning", path="/document_current_charges", message="Колонки итога требуют подтверждения."))
    current = money(Decimal(base_total) + Decimal(adj_total)) if base_total is not None and adj_total is not None else None
    if current is not None:
        add("/document_current_charges", lines[end])
    if debt is not None:
        add("/settlement/opening_balance", lines[end])
    if paid is not None:
        add("/settlement/payments_credited", lines[end])
    if row_total is not None:
        add("/settlement/document_closing_balance", lines[end])

    due_line = next((line for line in lines[end + 1:end + 6] if "Итого к оплате" in line and "без учета добровольного страхования" in line.casefold()), None)
    due_parts = _parts(due_line) if due_line else []
    due = _number(due_parts[-1], amount=True) if len(due_parts) == 2 else None
    if due is not None:
        add("/document_total_due", due_line)
    else:
        issues.append(Issue(code="EPD_DUE_AMBIGUOUS", severity="warning", path="/document_total_due", message="Итог без страхования требует подтверждения."))
    if due is not None and row_total is not None and due != row_total:
        issues.append(Issue(code="EPD_TOTAL_MISMATCH", severity="warning", path="/document_total_due", message="Итоги основной таблицы не совпадают."))

    bill = BillData(
        schema_version="1.0", period=period, currency="RUB", issuer_name=issuer,
        provider_id=provider_id, account_number=account, address_text=address,
        template_id=EPD_TEMPLATE_ID, template_version="1.0", services=services,
        adjustments=adjustments,
        settlement={"formula_kind": "unsupported", "opening_balance": debt,
                    "payments_credited": paid if paid is not None and Decimal(paid) >= 0 else None,
                    "penalties": None, "other_account_changes": None,
                    "document_closing_balance": row_total},
        document_current_charges=current, document_total_due=due,
    )
    if base_total is not None and all(row.charge_amount is not None for row in bill.services):
        found = money(sum((Decimal(row.charge_amount) for row in bill.services), Decimal(0)))
        if found != base_total:
            issues.append(Issue(code="EPD_CHARGE_SUM_MISMATCH", severity="warning", path="/document_current_charges", message="Сумма строк начислений отличается от напечатанного итога."))
    if adj_total is not None and all(_number(value, amount=True) is not None for _, value in parsed_rows):
        found = money(sum((Decimal(_number(value, amount=True)) for _, value in parsed_rows), Decimal(0)))
        if found != adj_total:
            issues.append(Issue(code="EPD_ADJUSTMENT_SUM_MISMATCH", severity="warning", path="/adjustments", message="Сумма строк перерасчёта отличается от напечатанного итога."))
    validation = validate_bill(bill)
    issues += validation.errors + validation.warnings
    issues.append(Issue(code="EPD_SETTLEMENT_UNSUPPORTED", severity="info", path="/settlement/formula_kind", message="Формула задолженности ЕПД не подтверждена; сверьте итог вручную."))
    outcome = "partial" if services and period is not None else "manual_required"
    return ExtractionResult(outcome=outcome, bill_data=bill, field_evidence=evidence, issues=issues,
                            template_id=EPD_TEMPLATE_ID, engine_version=engine_version)


def _empty_epd_bill() -> BillData:
    return BillData(schema_version="1.0", period=None, currency="RUB", issuer_name=None,
                    provider_id=None, account_number=None, address_text=None,
                    template_id=None, template_version=None, services=[], adjustments=[],
                    settlement={"formula_kind": "unsupported", "opening_balance": None,
                                "payments_credited": None, "penalties": None,
                                "other_account_changes": None, "document_closing_balance": None},
                    document_current_charges=None, document_total_due=None)


def project_receipt_facts(bill: BillData) -> dict:
    """Bounded PII-free facts for an LLM prompt; no private identity or raw lines."""
    if bill.template_id != EPD_TEMPLATE_ID:
        raise ValueError("EPD projection requires an EPD bill")
    rows = []
    for line in bill.services[:100]:
        _, _, label = _classify(line.raw_name)
        linked = [item for item in bill.adjustments if item.service_line_id == line.line_id]
        adjustment = (None if any(item.amount is None for item in linked) else
                      money(sum((Decimal(item.amount) for item in linked), Decimal(0))))
        rows.append({"service": label, "code": line.service_code, "scope": line.scope,
                     "segment": line.segment_key,
                     "unit": line.unit, "quantity": line.quantity, "tariff": line.tariff,
                     "charge_amount": line.charge_amount,
                     "adjustment": adjustment})
    return {"period": bill.period, "services": rows,
            "current_charges": bill.document_current_charges, "total_due": bill.document_total_due,
            "provenance": "parsed_epd_requires_review"}


def project_epd_table_candidates(layout_text: str) -> dict:
    """Numbers in the main charge table only; safe input for model suggestions.

    This does not include identity/header/footer/reference meter text or arbitrary
    service names. The model must never be the source of confirmed arithmetic.
    """
    if not is_epd(layout_text):
        raise ValueError("EPD layout is not recognized")
    lines = layout_text.splitlines()
    start, end = _table_bounds(lines)
    if start is None or end is None:
        raise ValueError("EPD charge table bounds are ambiguous")
    rows = []
    for line in lines[start:end]:
        parts = _parts(line)
        if len(parts) != 9 or "ДОБРОВОЛЬНОЕ СТРАХОВАНИЕ" in parts[0].upper():
            continue
        code, scope, label = _classify(parts[0])
        unit, _ = _unit(parts[2])
        # Only numeric tokens are carried through. Corrupted or textual cells
        # become null, never an unredacted slice of the source document.
        rows.append({
            "service": label, "code": code, "scope": scope, "segment": _segment(parts[0]), "unit": unit,
            "quantity": parts[1] if _number(parts[1]) is not None else None,
            "tariff": parts[3] if _number(parts[3]) is not None else None,
            "printed_charge": parts[4] if _number(parts[4], amount=True) is not None else None,
            "printed_adjustment": parts[5] if _number(parts[5], amount=True) is not None else None,
            "printed_line_total": parts[8] if _number(parts[8], amount=True) is not None else None,
        })
    return {"source": "main_charge_table_only", "rows": rows[:100]}
