"""Offline catalog loading and conservative question/draft responses."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .dto import (
    AnswerResult, Clarification, ClarificationOption, DraftRequest, DraftResult,
    Issue, KnowledgeBundle, NextAction, QuestionRequest, Recipient, SourceRef,
)
from .errors import EngineError
from .receipts import validate_bill


TOPICS = frozenset({
    "first_bill", "bill_terms", "bill_change", "meter_readings", "meter_deadline",
    "account_number", "management_contacts", "supplier_contacts", "payment_history",
    "arrears_or_credit", "adjustment", "request_breakdown", "service_issue",
    "housing_document", "new_resident",
})
LOCAL_TOPICS = frozenset({"meter_readings", "meter_deadline", "management_contacts", "supplier_contacts", "service_issue", "housing_document"})
MIN_SCORE = 2
MIN_MARGIN = 2


def _timestamp(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("UTC timestamp required")
    return parsed


def _read(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid catalog file: {path.name}")
    return value


def load_knowledge(path: str, now: datetime) -> KnowledgeBundle:
    """Load fixed local YAML files; never follow URLs or fetch during a request."""
    try:
        _timestamp(now)
        root = Path(path)
        manifest = _read(root / "manifest.yaml")
        sources = _read(root / "sources.yaml")["sources"]
        territories = _read(root / "territories.yaml")["territories"]
        organizations = _read(root / "organizations.yaml")["organizations"]
        glossary = _read(root / "glossary.yaml")
        aliases = _read(root / "aliases.yaml")
        allowed_hosts = _read(root / "source-host-allowlist.yaml")["hosts"]
        if not isinstance(allowed_hosts, list) or any(not isinstance(host, str) or not host for host in allowed_hosts):
            raise ValueError("Invalid source host allowlist")
        topic_dir = root / "topics"
        topics = [_read(file) for file in sorted(topic_dir.glob("*.yaml"))]
        if {item["id"] for item in topics} != TOPICS or len(topics) != len(TOPICS):
            raise ValueError("Exactly fifteen unique topic cards required")
        if {item["id"] for item in territories} != set(manifest["territory_ids"]):
            raise ValueError("Territory manifest mismatch")
        if manifest["pilot_territory_id"] is not None and manifest["pilot_territory_id"] not in manifest["territory_ids"]:
            raise ValueError("Unknown pilot territory")
        source_ids = {item["id"] for item in sources}
        if len(source_ids) != len(sources):
            raise ValueError("Duplicate source")
        for item in sources:
            if _timestamp(item["verified_at"]) > _timestamp(item["review_after"]):
                raise ValueError("Source review date precedes verification")
            if item["territory_id"] is not None and item["territory_id"] not in manifest["territory_ids"]:
                raise ValueError("Unknown source territory")
            if item["url"] is not None:
                url = urlsplit(item["url"])
                if url.scheme != "https" or url.hostname not in allowed_hosts or url.username or url.password or url.fragment:
                    raise ValueError("Source URL is outside the reviewed HTTPS host allowlist")
        for item in topics:
            _timestamp(item["review_after"])
            if not set(item["source_ids"]) <= source_ids:
                raise ValueError("Unknown topic source")
            for action in item["action_templates"]:
                if action["source_id"] is not None and action["source_id"] not in source_ids:
                    raise ValueError("Unknown action source")
        for item in aliases["aliases"]:
            if item["topic_id"] not in TOPICS:
                raise ValueError("Unknown alias topic")
        for item in glossary["terms"]:
            if not set(item["source_ids"]) <= source_ids:
                raise ValueError("Unknown glossary source")
        for item in organizations:
            if item["territory_id"] not in manifest["territory_ids"] or item["source_id"] not in source_ids:
                raise ValueError("Unknown organization provenance")
            for channel in item["channels"]:
                url = urlsplit(channel["url"])
                if channel["source_id"] not in source_ids or url.scheme != "https" or url.hostname not in allowed_hosts or url.username or url.password or url.fragment:
                    raise ValueError("Unknown or insecure organization channel")
                _timestamp(channel["verified_at"])
        payload = {
            "manifest": manifest, "sources": sources, "territories": territories,
            "organizations": organizations, "topics": topics, "glossary": glossary,
            "aliases": aliases,
        }
        digest = hashlib.sha256(json.dumps({**payload, "allowed_hosts": allowed_hosts}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
        return KnowledgeBundle(version=f"{manifest['version']}+{digest}", **payload)
    except Exception as exc:
        raise EngineError("KNOWLEDGE_INVALID", "Локальный каталог знаний недоступен или повреждён.") from exc


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold().replace("ё", "е"), flags=re.UNICODE))


def _rank(question: str, knowledge: KnowledgeBundle) -> list[tuple[int, dict]]:
    normalized = _norm(question)
    words = set(normalized.split())
    padded = f" {normalized} "
    ranked = []
    aliases = knowledge.aliases.get("aliases", [])
    for card in knowledge.topics:
        score = 0
        for phrase in card["utterances"]:
            value = _norm(phrase)
            if value and f" {value} " in padded:
                score = max(score, 6)
        score += sum(2 for keyword in card["keywords"] if _norm(keyword) in words)
        score += sum(5 for item in aliases if item["topic_id"] == card["id"] and f" {_norm(item['phrase'])} " in padded)
        ranked.append((score, card))
    return sorted(ranked, key=lambda item: (-item[0], item[1]["id"]))


def _clarify(field: str, knowledge: KnowledgeBundle) -> Clarification:
    prompts = {
        "topic_id": "Какой вопрос вы хотите разобрать?",
        "territory_id": "Для какой территории нужна информация?",
        "role": "Вы собственник или наниматель?",
        "organization_id": "Какая организация указана в вашем документе?",
        "service_code": "По какой услуге возник вопрос?",
        "document_kind": "Какой именно документ или справка вам нужны?",
    }
    options = []
    if field == "role":
        options = [ClarificationOption(value=value, label=label) for value, label in (("owner", "Собственник"), ("tenant", "Наниматель"), ("other", "Другая роль"))]
    elif field == "territory_id":
        options = [ClarificationOption(value=item["id"], label=item["label"]) for item in knowledge.territories if not item["is_synthetic"]]
    return Clarification(field=field, prompt=prompts[field], options=options)


def _valid_source(source: dict, territory_id: str | None, now: datetime) -> bool:
    return (not source["is_synthetic"] and _timestamp(source["verified_at"]) <= now <= _timestamp(source["review_after"])
            and (source["territory_id"] is None or source["territory_id"] == territory_id))


def _source_ref(source: dict) -> SourceRef:
    return SourceRef(**{**source, "verified_at": _timestamp(source["verified_at"]), "review_after": _timestamp(source["review_after"])})


def _actions(card: dict, sources: list[SourceRef], receipt_ref) -> list[NextAction]:
    valid_ids = {item.id for item in sources}
    actions = []
    for item in card["action_templates"]:
        source_id = item["source_id"]
        if source_id is not None and source_id not in valid_ids:
            continue
        source = next((ref for ref in sources if ref.id == source_id), None)
        if item["type"] == "open_link" and (source is None or source.url is None):
            continue
        actions.append(NextAction(
            id=item["id"], type=item["type"], label=item["label"],
            url=source.url if item["type"] == "open_link" else None,
            topic_id=card["id"] if item["type"] in ("select_topic", "prepare_draft") else None,
            organization_id=None, source_id=source_id, target=item["target"],
            receipt_ref=receipt_ref if item["target"] == "receipt_detail" else None,
            requires=item["requires"],
        ))
    return actions


def answer_question(request: QuestionRequest, knowledge: KnowledgeBundle) -> AnswerResult:
    cards = {item["id"]: item for item in knowledge.topics}
    explicit = request.context.topic_id
    if explicit is not None and explicit not in cards:
        raise EngineError("KNOWLEDGE_INVALID", "Выбрана неизвестная тема каталога.")
    ranking = _rank(request.question, knowledge)
    topic = cards.get(explicit) if explicit else None
    if topic is None and ranking and ranking[0][0] >= MIN_SCORE and (len(ranking) == 1 or ranking[0][0] - ranking[1][0] >= MIN_MARGIN):
        topic = ranking[0][1]
    if topic is None:
        suggestions = [ClarificationOption(value=item["id"], label=item["title"]) for score, item in ranking if score >= MIN_SCORE][:3]
        if suggestions:
            return AnswerResult(status="needs_clarification", text="Уточните тему вопроса.", topic_id=None, steps=[], sources=[], actions=[], clarification=Clarification(field="topic_id", prompt="Какую тему вы имеете в виду?", options=suggestions), limitations=[], knowledge_version=knowledge.version, receipt_ref=None)
        return AnswerResult(status="unsupported", text="Не удалось определить тему. Выберите тему из каталога или уточните вопрос.", topic_id=None, steps=[], sources=[], actions=[], clarification=None, limitations=["Тема вопроса неизвестна."], knowledge_version=knowledge.version, receipt_ref=None)
    receipt_ref = request.receipt.receipt_ref if request.receipt is not None else None
    if request.receipt is not None and not validate_bill(request.receipt.bill_data).can_confirm:
        raise EngineError("INVALID_BILL", "Для ответа по квитанции сначала подтвердите её данные.")
    for field in topic["required_context"]:
        if getattr(request.context, field) is None:
            return AnswerResult(status="needs_clarification", text="Для точного ответа нужно уточнение.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=_clarify(field, knowledge), limitations=[], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
    for field, permitted in (
        ("territory_id", "territory_ids"), ("role", "roles"),
        ("service_code", "service_codes"), ("document_kind", "document_kinds"),
    ):
        values = topic["applicability"][permitted]
        actual = getattr(request.context, field)
        if values and actual is None:
            return AnswerResult(status="needs_clarification", text="Для точного ответа нужно уточнение.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=_clarify(field, knowledge), limitations=[], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
        if values and actual not in values:
            return AnswerResult(status="unsupported", text="Карточка не применима к выбранному контексту.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=None, limitations=["Территория, роль, услуга или документ вне области применимости."], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
    if _timestamp(topic["review_after"]) < request.now:
        return AnswerResult(status="unsupported", text="Карточка темы требует обновления.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=None, limitations=["Срок проверки карточки истёк."], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
    if topic["id"] in LOCAL_TOPICS and request.context.territory_id not in {item["id"] for item in knowledge.territories}:
        return AnswerResult(status="unsupported", text="Для указанной территории нет проверенной инструкции.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=None, limitations=["Территория отсутствует в каталоге."], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
    source_map = {item["id"]: item for item in knowledge.sources}
    sources = []
    for source_id in topic["source_ids"]:
        item = source_map[source_id]
        if not _valid_source(item, request.context.territory_id, request.now):
            return AnswerResult(status="unsupported", text="Актуальной проверенной инструкции для этой территории нет.", topic_id=topic["id"], steps=[], sources=[], actions=[], clarification=None, limitations=["Источник просрочен, синтетический или относится к другой территории."], knowledge_version=knowledge.version, receipt_ref=receipt_ref)
        sources.append(_source_ref(item))
    limitations = []
    if topic["id"] in LOCAL_TOPICS and not sources:
        limitations.append("Проверенной местной инструкции и канала пока нет.")
    return AnswerResult(
        status="answered", text=topic["answer_template"], topic_id=topic["id"],
        steps=topic["steps"], sources=sources, actions=_actions(topic, sources, receipt_ref),
        clarification=None, limitations=limitations, knowledge_version=knowledge.version,
        receipt_ref=receipt_ref,
    )


def compose_draft(request: DraftRequest, knowledge: KnowledgeBundle) -> DraftResult:
    if request.topic_id not in {item["id"] for item in knowledge.topics}:
        raise EngineError("KNOWLEDGE_INVALID", "Тема черновика отсутствует в каталоге.")
    facts = []
    refs = []
    selected = None
    for receipt in request.receipts:
        if not validate_bill(receipt.bill_data).can_confirm:
            raise EngineError("INVALID_BILL", "Черновик требует подтверждённых данных квитанции.")
        refs.append(receipt.receipt_ref)
        for line in receipt.bill_data.services:
            if line.line_id == request.line_id:
                selected = (receipt.bill_data, line)
    if request.line_id is not None and selected is None:
        raise EngineError("INVALID_BILL", "Выбранная строка не найдена в подтверждённых квитанциях.")
    if selected is not None:
        bill, line = selected
        facts.append(f"Услуга: «{' '.join(line.raw_name.split())}».")
        if bill.period is not None:
            facts.append(f"Период: {bill.period}.")
        if line.charge_amount is not None:
            facts.append(f"Сумма строки в квитанции: {line.charge_amount} руб.")
        if bill.issuer_name is not None:
            facts.append(f"Указанная в квитанции организация: {' '.join(bill.issuer_name.split())}.")
    elif request.receipts:
        for receipt in request.receipts:
            bill = receipt.bill_data
            if bill.period is not None:
                facts.append(f"Период квитанции: {bill.period}.")
            if bill.document_total_due is not None:
                facts.append(f"Напечатано к оплате: {bill.document_total_due} руб.")
    issue_list = []
    source_map = {item["id"]: item for item in knowledge.sources}
    recipient = None
    actions = []
    organization = next((item for item in knowledge.organizations if item["id"] == request.organization_id), None)
    if organization is not None and not organization["is_synthetic"] and organization["territory_id"] == request.territory_id and _valid_source(source_map[organization["source_id"]], request.territory_id, request.now):
        for channel in organization["channels"]:
            source = source_map.get(channel["source_id"])
            if source is not None and _valid_source(source, request.territory_id, request.now) and _timestamp(channel["verified_at"]) <= request.now:
                recipient = Recipient(id=organization["id"], label=organization["name"])
                actions.append(NextAction(id="open-verified-channel", type="open_link", label="Открыть проверенный канал", url=channel["url"], topic_id=None, organization_id=organization["id"], source_id=source["id"], target=None, receipt_ref=None, requires=[]))
                break
    if recipient is None:
        issue_list.append(Issue(code="RECIPIENT_UNVERIFIED", severity="warning", path="/organization_id", message="Получатель и канал не проверены; выберите организацию самостоятельно перед отправкой."))
    question = " ".join(request.user_question.split())
    if question:
        # This is quoted user data, never an instruction to the engine or a verified fact.
        question_line = f"Дополнительный вопрос пользователя (проверьте формулировку): «{question}»."
    else:
        question_line = ""
    text = "\n".join(part for part in [
        "Здравствуйте. Прошу пояснить данные моего документа.", *facts,
        question_line, "Прошу сообщить состав начисления и данные, использованные при расчёте.",
        "Этот текст является черновиком: проверьте и отредактируйте его перед копированием.",
    ] if part)
    return DraftResult(text=text[:5000], recipient=recipient, actions=actions,
                       receipt_refs=refs, knowledge_version=knowledge.version, issues=issue_list)
