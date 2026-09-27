"""Arithmetic explanation of a confirmed bill. No legal or tariff claims."""

from __future__ import annotations

from decimal import Decimal, localcontext

from .dto import (
    BalanceComponent, ExplainRequest, ExplanationLine, Issue, KnowledgeBundle,
    ReceiptExplanation, ReconciliationCheck,
)
from .errors import EngineError
from .receipts import LINE_TOLERANCE, calculate_bill, money, rounded, validate_bill


ENGINE_VERSION = "0.1.0"
MAX_MONEY = Decimal("999999999.99")


def _public_money(value: str | None) -> str | None:
    if value is not None and abs(Decimal(value)) > MAX_MONEY:
        raise EngineError("INVALID_BILL", "Расчётная сумма не помещается в денежный формат договора; проверьте значения квитанции.")
    return value


def _line(index, line) -> ExplanationLine:
    path = f"/services/{index}"
    issues: list[Issue] = []
    calculated = None
    difference = None
    formula = None
    if line.calculation_kind == "simple_product":
        if line.quantity is not None and line.tariff is not None:
            with localcontext() as context:
                context.prec = 50
                product = rounded(Decimal(line.quantity) * Decimal(line.tariff))
            if abs(product) > MAX_MONEY:
                issues.append(Issue(code="LINE_CALCULATION_OUT_OF_RANGE", severity="warning", path=path, message="Произведение объёма и тарифа не помещается в денежный формат договора; проверьте исходные значения."))
            else:
                calculated = money(product)
                formula = f"{line.quantity} × {line.tariff} = {calculated} RUB"
            if line.charge_amount is not None and calculated is not None:
                difference = money(Decimal(line.charge_amount) - Decimal(calculated))
                if abs(Decimal(difference)) > MAX_MONEY:
                    difference = None
                    issues.append(Issue(code="LINE_DIFFERENCE_OUT_OF_RANGE", severity="warning", path=path, message="Разница строки не помещается в денежный формат договора."))
                elif abs(Decimal(difference)) > LINE_TOLERANCE:
                    issues.append(Issue(code="LINE_AMOUNT_MISMATCH", severity="warning", path=path + "/charge_amount", message="Напечатанная сумма строки отличается от произведения объёма и тарифа."))
        else:
            issues.append(Issue(code="LINE_FORMULA_INCOMPLETE", severity="warning", path=path, message="Объём или тариф неизвестен; строку нельзя пересчитать."))
    else:
        issues.append(Issue(code="LINE_FORMULA_UNSUPPORTED", severity="info", path=path, message="Для строки доступна только напечатанная сумма; формула не указана."))
    explanation = (
        f"В квитанции указано {line.charge_amount} RUB. " if line.charge_amount is not None else "Сумма строки не указана. "
    ) + (f"Проверка: {formula}." if formula else "Самостоятельный расчёт строки недоступен.")
    return ExplanationLine(
        line_id=line.line_id, title=line.raw_name, explanation=explanation,
        formula_text=formula, calculated_amount=calculated,
        difference=difference, issues=issues,
    )


def explain_receipt(request: ExplainRequest, knowledge: KnowledgeBundle) -> ReceiptExplanation:
    """Explain only confirmed values; backend validates ownership and revision."""
    bill = request.bill_data
    validation = validate_bill(bill)
    if not validation.can_confirm:
        raise EngineError("INVALID_BILL", "Подтвердите обязательные поля квитанции перед объяснением.")
    arithmetic = calculate_bill(bill)
    for value in (arithmetic.current_charges, arithmetic.calculated_closing_balance, arithmetic.calculated_total_due, *(part for check in arithmetic.checks for part in (check.calculated_value, check.difference))):
        _public_money(value)
    settlement = bill.settlement
    service_charges = _public_money(money(sum((Decimal(line.charge_amount) for line in bill.services), Decimal(0))))
    adjustment_charges = _public_money(money(sum((Decimal(item.amount) for item in bill.adjustments), Decimal(0))))
    components = [
        BalanceComponent(code="opening_balance", label="Остаток на начало", amount=settlement.opening_balance),
        BalanceComponent(code="service_charges", label="Начисления по услугам", amount=service_charges),
        BalanceComponent(code="adjustments", label="Отдельные перерасчёты", amount=adjustment_charges),
        BalanceComponent(code="penalties", label="Пени", amount=settlement.penalties),
        BalanceComponent(code="other_account_changes", label="Прочие изменения счёта", amount=settlement.other_account_changes),
        BalanceComponent(code="payments_credited", label="Зачтённые платежи (вычитаются)", amount=settlement.payments_credited),
    ]
    issues = list(validation.warnings)
    for index, item in enumerate(bill.adjustments):
        period = f" за {item.related_period}" if item.related_period else ""
        issues.append(Issue(code="ADJUSTMENT_APPLIED", severity="info", path=f"/adjustments/{index}/amount", message=f"Отдельный перерасчёт {item.amount} RUB{period} учтён один раз в текущих начислениях."))
    issues.append(Issue(
        code="ARITHMETIC_ONLY", severity="info", path=None,
        message="Объяснение проверяет числа подтверждённой квитанции. Тарифы, нормативы и правомерность начислений внешними источниками не подтверждены.",
    ))
    if arithmetic.reconciliation_status == "matched":
        summary = f"Текущие начисления {arithmetic.current_charges} RUB; к оплате {arithmetic.calculated_total_due} RUB. Напечатанные итоги сходятся с арифметикой."
    elif arithmetic.reconciliation_status == "mismatch":
        summary = "Напечатанные итоги расходятся с арифметическим расчётом; проверьте строки, корректировки и сальдо."
    elif arithmetic.reconciliation_status == "unsupported":
        summary = "Способ расчёта сальдо не поддерживается; сумму к оплате нельзя независимо подтвердить."
    else:
        summary = "Для полной сверки не хватает значений в подтверждённой квитанции."
    return ReceiptExplanation(
        receipt_ref=request.receipt_ref, engine_version=ENGINE_VERSION,
        knowledge_version=knowledge.version, summary=summary,
        current_charges=arithmetic.current_charges,
        document_total_due=bill.document_total_due,
        calculated_closing_balance=arithmetic.calculated_closing_balance,
        calculated_total_due=arithmetic.calculated_total_due,
        unexplained_difference=next((check.difference for check in arithmetic.checks if check.field == "document_total_due"), None),
        reconciliation_checks=[ReconciliationCheck(**vars(check)) for check in arithmetic.checks],
        reconciliation_status=arithmetic.reconciliation_status,
        lines=[_line(index, line) for index, line in enumerate(bill.services)],
        balance_components=components, issues=issues,
        sources=[], actions=[],
    )
