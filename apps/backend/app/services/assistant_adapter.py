"""Translate owner-checked snapshots to C's public question and draft DTOs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
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


def _safe_model_receipt(snapshot: dict) -> dict | None:
    """Explicit allowlist of normalized facts; never copy source names or identity."""
    bill = BillData.model_validate_json(json.dumps(snapshot["bill_data"]))
    if bill.template_id == "mos-oblast-epd-v1":
        from housing_engine import project_receipt_facts

        return project_receipt_facts(bill)
    if bill.template_id != "demo-bill-v1" or snapshot.get("dataset_kind") != "synthetic":
        return None
    return {
        "period": bill.period,
        "services": [{"code": line.service_code, "scope": line.scope,
                      "segment": line.segment_key, "unit": line.unit,
                      "quantity": line.quantity, "tariff": line.tariff,
                      "charge_amount": line.charge_amount}
                     for line in bill.services[:20]],
        "current_charges": bill.document_current_charges,
        "total_due": bill.document_total_due,
        "provenance": "synthetic_demo_receipt",
    }


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
        priced = [line for line in bill.get("services", []) if line.get("charge_amount") is not None]
        priced.sort(key=lambda line: abs(Decimal(line["charge_amount"])), reverse=True)
        entries = [f"{line['raw_name']}: {_money(line['charge_amount'])}" for line in priced]
        text = f"Начисления за {period}: " + ("; ".join(entries[:10]) if entries else "строки не распознаны")
        if len(entries) > 10:
            text += f"; ещё {len(entries) - 10} строк в квитанции"
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
            if len(changed) > 8:
                text += f" Ещё {len(changed) - 8} изменённых строк."
        if compared["status"] != "complete":
            text += " Сравнение частичное: часть строк или итогов не удалось сопоставить."
        ref = {"id": str(newer["id"]), "revision": newer["revision"]}
    return {"status": "answered", "text": text[:1500], "topic_id": "bill_change",
            "steps": [], "sources": [], "actions": [], "clarification": None,
            "limitations": [], "knowledge_version": knowledge.version, "receipt_ref": ref}


def _fallback_intent(question: str) -> str:
    """Whole-word cues only: «простой» is not «рост», «Контакты УК по Москве» is not a comparison."""
    words = re.findall(r"[а-яa-z0-9]+", question.lower().replace("ё", "е"))
    text = f" {' '.join(words)} "

    def has(*roots: str) -> bool:
        return any(word.startswith(root) for word in words for root in roots)

    money = has("плат", "сумм", "начисл", "квитанц", "тариф", "счет", "коммуналк", "жку", "стоим", "дорож")
    subject = money or has("вырос", "подорож", "вод", "свет", "электр", "отоплен", "газ", "тепл", "мусор")
    contact = has("контакт", "телефон", "позвон", "кому", "куда", "управля", "поставщик") or "ук" in words
    if subject and not contact and (has("сосед", "средн") or any(phrase in text for phrase in (
            " у других ", " у всех ", " по городу ", " в городе ", " по москве ", " в москве ",
            " по области ", " везде "))):
        return "city_comparison"
    if (has("вырос", "выросл", "подорож", "дороже", "увелич", "скачок", "скакнул", "прибав")
            or any(word in {"рост", "роста", "росте"} for word in words)):
        return "bill_rise"
    if has("измен", "сравн", "разниц", "отлич", "больше") and money:
        return "bill_rise"
    return "faq"


_SERVICE_WORDS = (
    ("горяч", "hot_water"), ("холод", "cold_water"), ("отоп", "heating"),
    ("элект", "electricity"), ("водоотвед", "drainage"),
    ("капремонт", "capital_repair"), ("мусор", "waste"),
)
_SERVICE_LABELS = {
    "hot_water": "горячая вода", "cold_water": "холодная вода", "heating": "отопление",
    "electricity": "электроэнергия", "drainage": "водоотведение",
    "capital_repair": "капремонт", "waste": "вывоз отходов",
}


def _city_answer(question: str, context: dict, snapshots: list[dict], knowledge,
                 city_lookup: Callable[[str, str, str], dict] | None) -> dict:
    output = _receipt_answer(question, snapshots, knowledge)
    output["text"] = ""
    if not snapshots:
        output["text"] = "Для сравнения с городом загрузите и подтвердите квитанцию."
        return output
    current = snapshots[0]
    bill = current["bill_data"]
    service = context.get("service_code")
    if not service:
        lowered = question.lower()
        matches = {code for needle, code in _SERVICE_WORDS if needle in lowered}
        if len(matches) == 1:
            service = matches.pop()
    services = bill.get("services", [])
    counts = {line.get("service_code"): sum(1 for item in services
              if item.get("service_code") == line.get("service_code")) for line in services}
    eligible = sorted(code for code, count in counts.items() if code and code != "other" and count == 1)
    if not service and len(eligible) == 1:
        service = eligible[0]
    if not service and not eligible:
        output["text"] = "В квитанции нет однозначной строки услуги для городского сравнения."
        return output
    if not service:
        output["status"] = "needs_clarification"
        output["text"] = "Выберите услугу для сравнения начислений с городом."
        output["clarification"] = {
            "field": "service_code", "prompt": "По какой услуге сравнить начисления?",
            "options": [{"value": code, "label": _SERVICE_LABELS.get(code, code.replace("_", " "))}
                        for code in eligible],
        }
        return output
    current_lines = [line for line in services if line.get("service_code") == service]
    if service == "other":
        output["text"] = "Разные услуги без уточнённого вида нельзя объединять в городской показатель."
        return output
    if len(current_lines) != 1:
        output["text"] = ("Городское сравнение по этой услуге пока недоступно: в квитанции "
                          "несколько разных строк, которые нельзя объединять в один показатель.")
        return output
    if city_lookup is None or current.get("dataset_kind") != "user_provided":
        output["text"] = "Для этой квитанции нет сопоставимого подтверждённого городского набора."
        return output
    metric = "tariff" if "тариф" in question.lower() else "charge_amount"
    try:
        latest = city_lookup(str(current["id"]), service, metric)
    except Exception:
        output["text"] = "Городское сравнение сейчас недоступно."
        return output
    if latest["status"] != "available":
        output["text"] = (
            "Город указан неоднозначно; уточните его в квитанции." if latest["status"] == "ambiguous_city"
            else "Пока недостаточно сопоставимых подтверждённых квитанций жителей города для сравнения."
        )
        return output
    city = "Москва" if latest["city"] == "moskva" else latest["city"]
    current_period = latest["period"]
    unit = f"/{latest['unit']}" if metric == "tariff" else ""
    kind = "средний тариф" if metric == "tariff" else "среднее начисление"
    output["text"] = (f"В городе {city} за {current_period} по услуге {_SERVICE_LABELS.get(service, service)} "
                      f"{kind} {latest['average']} руб{unit}, медиана {latest['median']} руб{unit}. "
                      f"Выборка: {latest['sample_size']} жителей с подтверждёнными квитанциями и согласием.")
    own_current = current_lines[0].get(metric)
    if own_current is not None:
        output["text"] += f" По вашей квитанции: {own_current} руб{unit}."
    previous = snapshots[1] if len(snapshots) > 1 else None
    if previous is None:
        output["text"] += " Данных за предыдущий месяц для проверки городского роста нет."
        return output
    older_lines = [line for line in previous["bill_data"].get("services", [])
                   if line.get("service_code") == service]
    key_fields = ("scope", "segment_key", "unit")
    if (len(older_lines) != 1 or
            any(current_lines[0].get(field) != older_lines[0].get(field) for field in key_fields)):
        output["text"] += " Строки двух месяцев несопоставимы по виду услуги или единице."
        return output
    own_previous = older_lines[0].get(metric)
    if own_current is not None and own_previous is not None:
        own_delta = Decimal(own_current) - Decimal(own_previous)
        output["text"] += (f" У вас за {previous['bill_data'].get('period')}: {own_previous} руб{unit}; "
                           f"изменение {own_delta:+.2f} руб{unit}.")
    try:
        older = city_lookup(str(previous["id"]), service, metric)
    except Exception:
        older = {"status": "insufficient_data"}
    if older["status"] != "available" or older.get("unit") != latest.get("unit"):
        output["text"] += " Для прошлого месяца городских данных недостаточно; городской рост не установлен."
        return output
    year, month = map(int, current_period.split("-"))
    expected_previous = f"{year - (month == 1):04d}-{12 if month == 1 else month - 1:02d}"
    if older.get("city") != latest.get("city") or older.get("period") != expected_previous:
        output["text"] += " Города или периоды двух выборок различаются; городской рост не установлен."
        return output
    delta = Decimal(latest["average"]) - Decimal(older["average"])
    output["text"] += (f" За {older['period']} среднее было {older['average']} руб{unit} "
                       f"по {older['sample_size']} жителям; разница средних {delta:+.2f} руб{unit}. ")
    if metric == "charge_amount":
        output["text"] += "Разные площади и объёмы потребления влияют на начисления, поэтому это не изменение тарифа."
    else:
        output["text"] += "Выборка ограничена подтверждёнными квитанциями участников."
    return output


def answer_json(question: str, context: dict, snapshots: list[dict],
                profile: dict, knowledge, *, api_key: str | None = None,
                model: str = "deepseek-flash", personal_snapshots: list[dict] | None = None,
                allow_receipt_model: bool = False,
                city_lookup: Callable[[str, str, str], dict] | None = None,
                intent: str | None = None) -> dict:
    """Answer one question. A valid context territory/role (from a clarification or the dialogue)
    wins over the profile, so answering a clarification never loops back to the same question."""
    territories = {item["id"] for item in knowledge.territories}
    context = {**context,
               "territory_id": context.get("territory_id") if context.get("territory_id") in territories
               else profile["territory_id"],
               "role": context.get("role") if context.get("role") in {"owner", "tenant", "other"}
               else profile["role"]}
    context.pop("receipt_id", None)
    context.pop("receipt_revision", None)
    explicit_topic = context.get("topic_id")
    if intent is not None:
        api_key_for_classify = None
    else:
        api_key_for_classify = api_key
        intent = _fallback_intent(question)
    if api_key_for_classify:
        try:
            detected = classify(question, knowledge.topics, api_key, model)
            intent = detected["intent"]
            if context.get("topic_id") is None:
                context["topic_id"] = detected["topic_id"]
        except ModelUnavailable:
            pass
    if intent in {"bill_rise", "city_comparison"} and explicit_topic in {None, "bill_change"}:
        active_snapshots = personal_snapshots if personal_snapshots is not None else snapshots
        if intent == "city_comparison":
            return _city_answer(question, context, active_snapshots, knowledge, city_lookup)
        output = _receipt_answer(question, active_snapshots, knowledge)
        if api_key and allow_receipt_model and active_snapshots and intent == "bill_rise":
            projected = [_safe_model_receipt(item) for item in active_snapshots]
            if all(item is not None for item in projected):
                safe_facts = {"receipts": projected}
                if len(active_snapshots) > 1:
                    from app.services.comparison_adapter import compare_json

                    computed = compare_json([active_snapshots[1], active_snapshots[0]], None, True)
                    safe_facts["delta_current_charges"] = computed["delta_current_charges"]
                try:
                    introduction = phrase(question, json.dumps(safe_facts, ensure_ascii=False), api_key, model)
                    if (len(introduction) <= 220 and not re.search(r"\d", introduction) and
                            not re.search(r"(?:http|www\.|адрес|сч[её]т\s*№|лицевой)", introduction.lower())):
                        output["text"] = (introduction + " " + output["text"])[:1500]
                except ModelUnavailable:
                    pass
        return output
    receipt = _confirmed(snapshots[0], context["territory_id"]) if snapshots else None
    result = answer_question(QuestionRequest(
        question=question, context=QuestionContext(**context),
        receipt=receipt, now=datetime.now(timezone.utc),
    ), knowledge)
    output = result.model_dump(mode="json")
    if api_key and output["status"] == "answered":
        try:
            facts = "\n".join([output["text"], *output["steps"], *output["limitations"]])
            phrased = phrase(question, facts, api_key, model)
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
