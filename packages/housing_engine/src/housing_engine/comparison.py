"""Deterministic comparison of two confirmed receipt revisions."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, localcontext

from .dto import (
    CompareRequest, ComparedLine, ComparisonResult, Issue, KnowledgeBundle,
    NextAction, PeriodReceiptRef, SettlementDelta,
)
from .errors import EngineError
from .receipts import LINE_TOLERANCE, calculate_bill, money, rounded, validate_bill


MAX_MONEY = Decimal("999999999.99")


def _amount(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if abs(value) > MAX_MONEY:
        return None
    return money(value)


def _difference(old: str | None, new: str | None) -> str | None:
    return _amount(Decimal(new) - Decimal(old)) if old is not None and new is not None else None


def _normalized_account(value: str | None) -> str | None:
    return re.sub(r"[\s-]+", "", value).casefold() if value else None


def _normalized_text(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value else None


def _normalized_address(value: str | None) -> str | None:
    if value is None:
        return None
    value = _normalized_text(value)
    # Only unambiguous written abbreviations. Never collapse house/flat numbers.
    value = re.sub(r"\bул\.?\b", "улица", value)
    value = re.sub(r"\bд\.?\b", "дом", value)
    value = re.sub(r"\bкв\.?\b", "квартира", value)
    return re.sub(r"\s*([,.])\s*", r"\1", value)


def _identity(old, new) -> tuple[bool, list[Issue]]:
    issues: list[Issue] = []
    missing = False
    for field, normalize in (
        ("account_number", _normalized_account),
        ("provider_id", _normalized_text),
        ("address_text", _normalized_address),
    ):
        a = normalize(getattr(old, field))
        b = normalize(getattr(new, field))
        if a is not None and b is not None and a != b:
            raise EngineError("INCOMPARABLE_RECEIPTS", "Реквизиты квитанций различаются; выберите документы одного счёта и поставщика.")
        if a is None or b is None:
            missing = True
            issues.append(Issue(code="IDENTITY_UNVERIFIED", severity="warning", path=f"/{field}", message="Реквизит отсутствует хотя бы в одной квитанции; принадлежность одному счёту не проверена."))
    if old.provider_id is None or new.provider_id is None:
        a, b = _normalized_text(old.issuer_name), _normalized_text(new.issuer_name)
        if a is not None and b is not None and a != b:
            raise EngineError("INCOMPARABLE_RECEIPTS", "Названия поставщиков различаются; сравнение требует проверки.")
    return missing, issues


def _key(line, *, include_unit: bool) -> tuple:
    base = (line.service_code, line.scope, _normalized_text(line.supplier_key), _normalized_text(line.segment_key))
    if line.service_code == "other":
        base += (_normalized_text(line.raw_name),)
    if include_unit:
        base += (line.unit, _normalized_text(line.unit_label))
    return base


def _effects(old, new) -> tuple[str | None, str | None, str | None]:
    if not (old.calculation_kind == new.calculation_kind == "simple_product"
            and old.unit == new.unit and _normalized_text(old.unit_label) == _normalized_text(new.unit_label)):
        return None, None, None
    values = (old.quantity, old.tariff, old.charge_amount, new.quantity, new.tariff, new.charge_amount)
    if any(value is None for value in values):
        return None, None, None
    with localcontext() as context:
        context.prec = 50
        oq, ot, oa, nq, nt, na = (Decimal(value) for value in values)
        if abs(oa - rounded(oq * ot)) > LINE_TOLERANCE or abs(na - rounded(nq * nt)) > LINE_TOLERANCE:
            return None, None, None
        quantity = rounded((nq - oq) * ot)
        tariff = rounded(nq * (nt - ot))
        residual = na - oa - quantity - tariff
        return _amount(quantity), _amount(tariff), _amount(residual)


def _pair(old, new, status: str) -> ComparedLine:
    delta = _difference(old.charge_amount if old else "0.00", new.charge_amount if new else "0.00")
    if old is None:
        delta = new.charge_amount
    elif new is None:
        delta = _amount(-Decimal(old.charge_amount)) if old.charge_amount is not None else None
    effects = _effects(old, new) if status == "matched" else (None, None, None)
    if status == "matched" and effects[0] is None:
        explanation = "Изменение суммы строки известно; объём и тариф нельзя достоверно разложить из подтверждённых данных."
    elif status == "matched":
        explanation = "Вклад объёма рассчитан по прежнему тарифу; это арифметика квитанций, не доказательство расхода."
    elif status == "incompatible":
        explanation = "Единицы строк различаются; разложение объёма и тарифа недоступно."
    elif status == "added":
        explanation = "Строка появилась в новой квитанции; это не подтверждает появление самой услуги."
    elif status == "removed":
        explanation = "Строка отсутствует в новой квитанции; это не подтверждает исчезновение самой услуги."
    else:
        explanation = "Есть несколько возможных строк; сопоставление требует уточнения."
    return ComparedLine(
        older_line_id=old.line_id if old else None, newer_line_id=new.line_id if new else None,
        label=new.raw_name if new else old.raw_name, match_status=status,
        older_amount=old.charge_amount if old else None,
        newer_amount=new.charge_amount if new else None, delta=delta,
        quantity_effect=effects[0], tariff_effect=effects[1], rounding_effect=effects[2],
        explanation=explanation,
    )


def _lines(old, new) -> tuple[list[ComparedLine], list[Issue]]:
    rows: list[ComparedLine] = []
    issues: list[Issue] = []
    pending_old = list(old.services)
    pending_new = list(new.services)
    for include_unit in (True, False):
        by_old, by_new = defaultdict(list), defaultdict(list)
        for item in pending_old:
            by_old[_key(item, include_unit=include_unit)].append(item)
        for item in pending_new:
            by_new[_key(item, include_unit=include_unit)].append(item)
        used_old, used_new = set(), set()
        for key in by_old.keys() & by_new.keys():
            older, newer = by_old[key], by_new[key]
            if len(older) == len(newer) == 1:
                a, b = older[0], newer[0]
                status = "matched" if include_unit or (a.unit == b.unit and _normalized_text(a.unit_label) == _normalized_text(b.unit_label)) else "incompatible"
                rows.append(_pair(a, b, status))
                used_old.add(a.line_id)
                used_new.add(b.line_id)
            elif include_unit:
                for item in older:
                    rows.append(_pair(item, None, "ambiguous"))
                    used_old.add(item.line_id)
                for item in newer:
                    rows.append(_pair(None, item, "ambiguous"))
                    used_new.add(item.line_id)
                issues.append(Issue(code="AMBIGUOUS_SERVICE_LINES", severity="warning", path="/services", message="Несколько строк имеют один ключ; уточните код, область и сегмент услуги."))
            else:
                for item in older:
                    rows.append(_pair(item, None, "ambiguous"))
                    used_old.add(item.line_id)
                for item in newer:
                    rows.append(_pair(None, item, "ambiguous"))
                    used_new.add(item.line_id)
                issues.append(Issue(code="AMBIGUOUS_SERVICE_LINES", severity="warning", path="/services", message="Несколько строк могут соответствовать друг другу; требуется уточнение."))
        pending_old = [item for item in pending_old if item.line_id not in used_old]
        pending_new = [item for item in pending_new if item.line_id not in used_new]
    rows.extend(_pair(item, None, "removed") for item in pending_old)
    rows.extend(_pair(None, item, "added") for item in pending_new)
    if any(item.match_status == "incompatible" for item in rows):
        issues.append(Issue(code="UNIT_MISMATCH", severity="warning", path="/services", message="Единицы строк различаются; объём и тариф не сравниваются."))
    if any(item.match_status == "matched" and item.quantity_effect is None for item in rows):
        issues.append(Issue(code="LINE_DECOMPOSITION_UNAVAILABLE", severity="warning", path="/services", message="Не для каждой пары доступно разложение суммы на объём и тариф."))
    return rows, issues


def compare_receipts(request: CompareRequest, knowledge: KnowledgeBundle) -> ComparisonResult:
    left, right = request.left, request.right
    if left.receipt_ref.id == right.receipt_ref.id and left.receipt_ref.revision != right.receipt_ref.revision:
        raise EngineError("INCOMPARABLE_RECEIPTS", "Сравнение редакций одного документа вне MVP.")
    if not validate_bill(left.bill_data).can_confirm or not validate_bill(right.bill_data).can_confirm:
        raise EngineError("INVALID_BILL", "Обе квитанции должны быть подтверждены с заполненными обязательными строками.")
    if left.bill_data.period == right.bill_data.period:
        raise EngineError("INCOMPARABLE_RECEIPTS", "Для сравнения выберите разные периоды.")
    older, newer = sorted((left, right), key=lambda item: item.bill_data.period)
    old, new = older.bill_data, newer.bill_data
    missing_identity, issues = _identity(old, new)
    if missing_identity and not request.identity_acknowledged:
        issues.append(Issue(code="IDENTITY_ACK_REQUIRED", severity="warning", path=None, message="Проверьте недостающие реквизиты обеих квитанций и подтвердите сравнение."))
        return ComparisonResult(
            status="needs_identity_confirmation",
            older=PeriodReceiptRef(id=older.receipt_ref.id, revision=older.receipt_ref.revision, period=old.period),
            newer=PeriodReceiptRef(id=newer.receipt_ref.id, revision=newer.receipt_ref.revision, period=new.period),
            engine_version="0.1.0", knowledge_version=knowledge.version,
            delta_current_charges=None, delta_adjustments=None, delta_total_due=None,
            lines=[], settlement_deltas=[], unexplained_delta=None,
            issues=issues, actions=[NextAction(
                id="review-receipt-identity", type="navigate", label="Проверить реквизиты и подтвердить",
                url=None, topic_id=None, organization_id=None, source_id=None,
                target="comparison", receipt_ref=None, requires=["identity_acknowledged"],
            )],
        )
    rows, line_issues = _lines(old, new)
    issues += line_issues
    old_math, new_math = calculate_bill(old), calculate_bill(new)
    if old_math.reconciliation_status != "matched" or new_math.reconciliation_status != "matched":
        issues.append(Issue(code="RECONCILIATION_INCOMPLETE", severity="warning", path=None, message="Один из итогов не подтверждён полной сверкой; разница по строкам не объясняет весь платёж."))
    if old.period[:4] != new.period[:4] or int(new.period[5:]) - int(old.period[5:]) != 1:
        issues.append(Issue(code="NONADJACENT_PERIODS", severity="info", path="/period", message=f"Сравниваются периоды {old.period} и {new.period}."))
    adjustment_old = _amount(sum((Decimal(item.amount) for item in old.adjustments), Decimal(0))) if all(item.amount is not None for item in old.adjustments) else None
    adjustment_new = _amount(sum((Decimal(item.amount) for item in new.adjustments), Decimal(0))) if all(item.amount is not None for item in new.adjustments) else None
    delta_adjustments = _difference(adjustment_old, adjustment_new)
    delta_current = _difference(old_math.current_charges, new_math.current_charges)
    delta_due = _difference(old.document_total_due, new.document_total_due)
    labels = {"opening_balance": "Остаток на начало", "payments_credited": "Учтённые оплаты", "penalties": "Пени", "other_account_changes": "Прочие изменения счёта", "credit_clamp": "Использование переплаты"}
    deltas = []
    full_formula = old.settlement.formula_kind == new.settlement.formula_kind == "signed_balance_v1" and old_math.calculated_closing_balance is not None and new_math.calculated_closing_balance is not None
    for code in ("opening_balance", "payments_credited", "penalties", "other_account_changes"):
        raw = _difference(getattr(old.settlement, code), getattr(new.settlement, code))
        contribution = _amount(-Decimal(raw)) if code == "payments_credited" and raw is not None else raw
        deltas.append(SettlementDelta(code=code, label=labels[code], raw_delta=raw, contribution=contribution))
    clamp = None
    if full_formula:
        old_balance, new_balance = Decimal(old_math.calculated_closing_balance), Decimal(new_math.calculated_closing_balance)
        clamp = _amount((max(new_balance, Decimal(0)) - new_balance) - (max(old_balance, Decimal(0)) - old_balance))
    deltas.append(SettlementDelta(code="credit_clamp", label=labels["credit_clamp"], raw_delta=clamp, contribution=clamp))
    unexplained = None
    if full_formula and delta_current is not None and delta_due is not None and all(item.contribution is not None for item in deltas):
        explained = Decimal(delta_current) + sum((Decimal(item.contribution) for item in deltas), Decimal(0))
        unexplained = _amount(Decimal(delta_due) - explained)
    if unexplained is None or old_math.reconciliation_status != "matched" or new_math.reconciliation_status != "matched" or line_issues:
        status = "partial"
    else:
        status = "complete"
    if unexplained is None:
        issues.append(Issue(code="COMPARISON_PARTIAL", severity="warning", path=None, message="Недостаточно данных для полного объяснения разницы к оплате."))
    return ComparisonResult(
        status=status,
        older=PeriodReceiptRef(id=older.receipt_ref.id, revision=older.receipt_ref.revision, period=old.period),
        newer=PeriodReceiptRef(id=newer.receipt_ref.id, revision=newer.receipt_ref.revision, period=new.period),
        engine_version="0.1.0", knowledge_version=knowledge.version,
        delta_current_charges=delta_current, delta_adjustments=delta_adjustments, delta_total_due=delta_due,
        lines=rows, settlement_deltas=deltas, unexplained_delta=unexplained, issues=issues, actions=[],
    )
