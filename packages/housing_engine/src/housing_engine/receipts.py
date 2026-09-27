"""Deterministic bill arithmetic. Internal helpers; public entry is validate_bill."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .dto import BillData, Issue, ValidationResult


CENT = Decimal("0.01")
LINE_TOLERANCE = Decimal("0.01")


def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value: Decimal | None) -> str | None:
    return None if value is None else format(rounded(value), ".2f")


def as_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


@dataclass(frozen=True)
class Reconciliation:
    field: str
    document_value: str | None
    calculated_value: str | None
    difference: str | None
    status: str


@dataclass(frozen=True)
class BillMath:
    current_charges: str | None
    calculated_closing_balance: str | None
    calculated_total_due: str | None
    checks: tuple[Reconciliation, ...]
    reconciliation_status: str


def _check(field: str, documented: str | None, calculated: str | None, *, unsupported: bool = False) -> Reconciliation:
    if unsupported:
        return Reconciliation(field, documented, None, None, "unsupported")
    if documented is None or calculated is None:
        return Reconciliation(field, documented, calculated, None, "incomplete")
    difference = money(Decimal(documented) - Decimal(calculated))
    return Reconciliation(field, documented, calculated, difference, "matched" if difference == "0.00" else "mismatch")


def calculate_bill(bill: BillData) -> BillMath:
    """Compute only from known operands; unknown values never become zero."""
    amounts = [as_decimal(line.charge_amount) for line in bill.services]
    amounts += [as_decimal(item.amount) for item in bill.adjustments]
    current = money(sum(amounts, Decimal(0))) if all(item is not None for item in amounts) and bill.services else None
    settlement = bill.settlement
    operands = (
        settlement.opening_balance, current, settlement.penalties,
        settlement.other_account_changes, settlement.payments_credited,
    )
    formula_supported = settlement.formula_kind == "signed_balance_v1"
    closing = None
    total = None
    if formula_supported and all(value is not None for value in operands):
        opening, charges, penalties, other, payments = (Decimal(value) for value in operands)
        closing_value = rounded(opening + charges + penalties + other - payments)
        closing = money(closing_value)
        total = money(max(closing_value, Decimal(0)))
    checks = (
        _check("document_current_charges", bill.document_current_charges, current),
        _check("document_closing_balance", settlement.document_closing_balance, closing, unsupported=not formula_supported),
        _check("document_total_due", bill.document_total_due, total, unsupported=not formula_supported),
    )
    states = {check.status for check in checks}
    if "mismatch" in states:
        status = "mismatch"
    elif "incomplete" in states:
        status = "incomplete"
    elif "unsupported" in states:
        status = "unsupported"
    else:
        status = "matched"
    return BillMath(current, closing, total, checks, status)


def validate_bill(bill: BillData) -> ValidationResult:
    errors: list[Issue] = []
    warnings: list[Issue] = []

    def error(code: str, path: str, message: str) -> None:
        errors.append(Issue(code=code, severity="error", path=path, message=message))

    def warning(code: str, path: str | None, message: str) -> None:
        warnings.append(Issue(code=code, severity="warning", path=path, message=message))

    if bill.period is None:
        error("PERIOD_REQUIRED", "/period", "Укажите период квитанции.")
    if not bill.services:
        error("SERVICE_REQUIRED", "/services", "Добавьте хотя бы одну строку услуги.")
    seen_line_ids = set()
    for index, line in enumerate(bill.services):
        path = f"/services/{index}"
        if line.line_id in seen_line_ids:
            error("DUPLICATE_LINE_ID", path + "/line_id", "Идентификатор строки повторяется.")
        seen_line_ids.add(line.line_id)
        if not line.raw_name.strip():
            error("SERVICE_NAME_REQUIRED", path + "/raw_name", "Укажите название услуги.")
        if line.charge_amount is None:
            error("CHARGE_REQUIRED", path + "/charge_amount", "Подтвердите сумму строки.")
        if line.calculation_kind == "simple_product":
            if line.quantity is None or line.tariff is None:
                warning("LINE_FORMULA_INCOMPLETE", path, "Объём или тариф неизвестен; формулу строки проверить нельзя.")
            elif line.charge_amount is not None:
                computed = rounded(Decimal(line.quantity) * Decimal(line.tariff))
                difference = Decimal(line.charge_amount) - computed
                if abs(difference) > LINE_TOLERANCE:
                    warning("LINE_AMOUNT_MISMATCH", path + "/charge_amount", "Напечатанная сумма отличается от произведения объёма и тарифа.")
    seen_adjustment_ids = set()
    for index, item in enumerate(bill.adjustments):
        path = f"/adjustments/{index}"
        if item.adjustment_id in seen_adjustment_ids:
            error("DUPLICATE_ADJUSTMENT_ID", path + "/adjustment_id", "Идентификатор перерасчёта повторяется.")
        seen_adjustment_ids.add(item.adjustment_id)
        if item.amount is None:
            error("ADJUSTMENT_AMOUNT_REQUIRED", path + "/amount", "Подтвердите сумму перерасчёта.")
        if item.service_line_id is not None and item.service_line_id not in seen_line_ids:
            error("ADJUSTMENT_LINE_UNKNOWN", path + "/service_line_id", "Связанная строка услуги не найдена.")
    for name, value in (("account_number", bill.account_number), ("provider_id", bill.provider_id), ("address_text", bill.address_text)):
        if value is None:
            warning("IDENTITY_INCOMPLETE", f"/{name}", "Реквизит отсутствует; сравнение потребует дополнительной проверки.")
    if bill.document_total_due is None:
        warning("TOTAL_DUE_UNKNOWN", "/document_total_due", "Сумма к оплате не указана.")

    math = calculate_bill(bill)
    for check in math.checks:
        if check.status == "mismatch":
            warning("RECONCILIATION_MISMATCH", "/settlement/document_closing_balance" if check.field == "document_closing_balance" else f"/{check.field}", "Напечатанный итог отличается от рассчитанного; проверьте состав начислений.")
        elif check.status == "incomplete":
            warning("RECONCILIATION_INCOMPLETE", "/settlement/document_closing_balance" if check.field == "document_closing_balance" else f"/{check.field}", "Итог нельзя полностью сверить из известных значений.")
    return ValidationResult(
        can_confirm=not errors,
        errors=errors,
        warnings=warnings,
        reconciliation_status=math.reconciliation_status,
    )
