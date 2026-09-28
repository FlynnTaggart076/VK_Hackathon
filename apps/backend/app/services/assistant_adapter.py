"""Translate owner-checked snapshots to C's public question and draft DTOs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from housing_engine import BillData, DraftRequest, QuestionRequest, answer_question, compose_draft
from housing_engine.dto import ExplainRequest, QuestionContext, ReceiptRef

from app.services.deepseek import ModelUnavailable, classify, phrase


def _confirmed(snapshot: dict, territory_id: str | None) -> ExplainRequest:
    return ExplainRequest(
        receipt_ref=ReceiptRef(id=snapshot["id"], revision=snapshot["revision"]),
        bill_data=BillData.model_validate_json(json.dumps(snapshot["bill_data"])),
        confirmed_at=snapshot["confirmed_at"], territory_id=territory_id,
        now=datetime.now(timezone.utc),
    )


def _money(value: str | None) -> str:
    return f"{Decimal(value):.2f} ₽" if value is not None else "не указано"


def _receipt_answer(question: str, snapshots: list[dict], knowledge) -> dict:
    from app.services.comparison_adapter import compare_json

    if not snapshots:
        text = "Для разбора начислений загрузите и подтвердите квитанцию."
        ref = None
    elif len(snapshots) == 1:
        bill = snapshots[0]["bill_data"]
        period = bill.get("period") or "неизвестный месяц"
        entries = [f"{line['raw_name']}: {_money(line['charge_amount'])}"
                   for line in bill.get("services", []) if line.get("charge_amount") is not None]
        text = f"Начисления за {period}: " + ("; ".join(entries[:12]) if entries else "строки не распознаны")
        if bill.get("document_current_charges") is not None:
            text += f". Итого начислено: {_money(bill['document_current_charges'])}."
        else:
            text += "."
        text += " Подтверждённой квитанции за предыдущий месяц нет, поэтому рост проверить нельзя."
        ref = {"id": str(snapshots[0]["id"]), "revision": snapshots[0]["revision"]}
    else:
        newer, older = snapshots[:2]
        compared = compare_json([older, newer], None, True)
        delta = compared.get("delta_current_charges")
        text = (f"Начисления за {older['bill_data'].get('period')} и "
                f"{newer['bill_data'].get('period')}: изменение {_money(delta)}.")
        changed = [line for line in compared["lines"] if line.get("delta") not in (None, "0.00")]
        changed.sort(key=lambda line: abs(Decimal(line["delta"])), reverse=True)
        if changed:
            text += " Изменения по услугам: " + "; ".join(
                f"{line['label']}: {_money(line['older_amount'])} → {_money(line['newer_amount'])} "
                f"(разница {_money(line['delta'])})" for line in changed[:8]) + "."
        if compared["status"] != "complete":
            text += " Сравнение частичное: часть строк или итогов не удалось сопоставить."
        ref = {"id": str(newer["id"]), "revision": newer["revision"]}
    return {"status": "answered", "text": text[:1500], "topic_id": "bill_change",
            "steps": [], "sources": [], "actions": [], "clarification": None,
            "limitations": [], "knowledge_version": knowledge.version, "receipt_ref": ref}


def _fallback_intent(question: str) -> str:
    lowered = question.lower()
    if re.search(r"(по городу|у других|у всех|средн|сосед|по москве|везде)", lowered):
        return "city_comparison"
    if re.search(r"(вырос|подорож|дороже|измен|увелич|скачок|рост|сравн)", lowered):
        return "bill_rise"
    return "faq"


def answer_json(question: str, context: dict, snapshots: list[dict],
                profile: dict, knowledge, *, api_key: str | None = None,
                model: str = "deepseek-flash", personal_snapshots: list[dict] | None = None,
                allow_receipt_model: bool = False) -> dict:
    context = {**context, "territory_id": profile["territory_id"], "role": profile["role"]}
    context.pop("receipt_id", None)
    context.pop("receipt_revision", None)
    explicit_topic = context.get("topic_id")
    heuristic_intent = _fallback_intent(question)
    intent = heuristic_intent
    if api_key:
        try:
            detected = classify(question, knowledge.topics, api_key, model)
            intent = detected["intent"]
            if intent == "faq" and heuristic_intent != "faq":
                intent = heuristic_intent
            if context.get("topic_id") is None:
                context["topic_id"] = detected["topic_id"]
        except ModelUnavailable:
            pass
    if intent in {"bill_rise", "city_comparison"} and explicit_topic in {None, "bill_change"}:
        # The city statistic is a separate query with an explicit cohort metric.
        # A personal comparison is still useful without a city cohort.
        output = _receipt_answer(question, personal_snapshots if personal_snapshots is not None else snapshots, knowledge)
        if intent == "city_comparison":
            output["text"] = ("Сравнение с городом пока недоступно. " + output["text"])[:1500]
        return output
    receipt = _confirmed(snapshots[0], profile["territory_id"]) if snapshots else None
    result = answer_question(QuestionRequest(
        question=question, context=QuestionContext(**context),
        receipt=receipt, now=datetime.now(timezone.utc),
    ), knowledge)
    output = result.model_dump(mode="json")
    if api_key and output["status"] == "answered":
        try:
            phrased = phrase(question, output["text"], api_key, model)
            # Never let model introduce numeric, URL or currency facts absent from the card.
            numbers = set(re.findall(r"\d+(?:[.,]\d+)?", output["text"]))
            if set(re.findall(r"\d+(?:[.,]\d+)?", phrased)) <= numbers:
                output["text"] = phrased
        except ModelUnavailable:
            pass
    return output


def draft_json(body: dict, snapshots: list[dict], profile: dict, knowledge) -> dict:
    result = compose_draft(DraftRequest(
        topic_id=body["topic_id"], organization_id=body["organization_id"],
        territory_id=profile["territory_id"], role=profile["role"],
        receipts=[_confirmed(item, profile["territory_id"]) for item in snapshots],
        line_id=UUID(body["line_id"]) if body["line_id"] else None,
        user_question=body["user_question"],
        now=datetime.now(timezone.utc),
    ), knowledge)
    return result.model_dump(mode="json")
