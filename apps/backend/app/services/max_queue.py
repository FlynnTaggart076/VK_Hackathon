"""Minimal durable MAX webhook and message outbox. No raw update or token is logged."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import AssistantAnswer, Outbox, Profile, User, WebhookInbox
from app.db.store import SqlStore, now
from app.errors import ApiError


@dataclass(frozen=True)
class NormalizedUpdate:
    dedup_key: str
    event_type: str
    max_user_id: int | None
    chat_id: int | None
    text: str | None
    attachment_kind: str | None


def positive_int(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2**63 else None


def normalize_update(value: object) -> NormalizedUpdate:
    if not isinstance(value, dict) or not isinstance(value.get("update_type"), str) or \
            not value["update_type"] or type(value.get("timestamp")) is not int or \
            value["timestamp"] < 0:
        raise ApiError(400, "INVALID_REQUEST", "Некорректное событие MAX.")
    event_type = value["update_type"]
    message = value.get("message") if isinstance(value.get("message"), dict) else {}
    sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    body = message.get("body") if isinstance(message.get("body"), dict) else {}
    direct = recipient.get("chat_type") == "dialog"
    max_user_id = positive_int(sender.get("user_id")) if direct else None
    chat_id = positive_int(recipient.get("chat_id")) if direct else None
    text = body.get("text") if direct and isinstance(body.get("text"), str) else None
    if text is not None:
        text = text[:2000]
    attachments = body.get("attachments") if direct and isinstance(body.get("attachments"), list) else []
    attachment_kind = next((item.get("type") for item in attachments
                            if isinstance(item, dict) and item.get("type") in {"image", "file", "audio"}), None)
    if event_type == "bot_started":
        user = value.get("user") if isinstance(value.get("user"), dict) else {}
        max_user_id = positive_int(user.get("user_id"))
        chat_id = positive_int(value.get("chat_id"))
    if event_type not in {"bot_started", "message_created"}:
        max_user_id = chat_id = None
        text = attachment_kind = None
    mid = body.get("mid") if event_type == "message_created" else None
    if isinstance(mid, str) and 0 < len(mid) <= 256:
        identity = f"{event_type}:{mid}"
    else:
        identity = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return NormalizedUpdate(key, event_type, max_user_id, chat_id, text, attachment_kind)


def enqueue_update(store: SqlStore, update: NormalizedUpdate) -> None:
    try:
        with store.Session.begin() as session:
            session.add(WebhookInbox(
                id=uuid.uuid4(), dedup_key=update.dedup_key, event_type=update.event_type,
                max_user_id=update.max_user_id, chat_id=update.chat_id,
                text=update.text, attachment_kind=update.attachment_kind, state="queued",
                created_at=now(), expires_at=now() + timedelta(hours=24),
            ))
    except IntegrityError:
        # A replay of an already committed event is acknowledged without new work.
        with store.Session() as session:
            if session.scalar(select(WebhookInbox.id).where(WebhookInbox.dedup_key == update.dedup_key)):
                return
        raise


def _command_text(item: WebhookInbox) -> str | None:
    if not item.max_user_id:
        return None
    if item.event_type == "bot_started" or (item.text or "").strip().lower() == "/start":
        return "Помогу разобраться с начислениями ЖКХ. Откройте мини-приложение, чтобы загрузить квитанцию, или задайте текстовый вопрос. Команда /help — возможности и ограничения."
    if (item.text or "").strip().lower() == "/help":
        return "Можно спросить о начислениях и проверить квитанцию в мини-приложении. Файлы и фото загружайте только там. Голосовые сообщения и отправка обращений не поддерживаются."
    if (item.text or "").strip().lower() == "задать вопрос":
        return "Напишите текстовый вопрос о начислениях ЖКХ в этом личном диалоге."
    if item.attachment_kind:
        return "Загрузите PDF или фото квитанции в мини-приложении. Голосовые сообщения не обрабатываются."
    identity_question = " ".join((item.text or "").strip().lower().strip("?!., ").split())
    if identity_question in {"кто ты", "кто ты такой", "что умеешь", "что ты умеешь", "что ты можешь"}:
        return ("Я помощник по начислениям ЖКХ в MAX. В чате отвечаю на текстовые вопросы о начислениях, а в "
                "мини-приложении помогаю разобрать подтверждённую квитанцию и сравнить месяцы. "
                "Голосовые сообщения и отправка обращений не поддерживаются. "
                "Чтобы открыть мини-приложение, отправьте /start.")
    return None


def command_text(item: WebhookInbox) -> str | None:
    result = _command_text(item)
    if result and (item.event_type == "bot_started" or
                   (item.text or "").strip().lower() in {"/start", "/help"}):
        result += ("\nДля ответов текст вопроса после удаления типичных личных данных "
                   "может передаваться внешнему сервису DeepSeek. Включить: /llm_on, "
                   "отозвать согласие: /llm_off. Без согласия доступен локальный справочник. "
                   "Не присылайте в чат адрес, номер счёта или полный документ.")
    return result


def chat_consent_text(session, item: WebhookInbox, settings) -> str | None:
    command = (item.text or "").strip().lower()
    if not item.max_user_id or command not in {"/llm_on", "/llm_off"}:
        return None
    user = session.scalar(select(User).where(User.max_user_id == item.max_user_id).with_for_update())
    if user is None:
        user = User(id=uuid.uuid4(), max_user_id=item.max_user_id, created_at=now())
        session.add(user)
        session.flush()
        session.add(Profile(user_id=user.id, role="other", territory_id=None,
                            onboarding_completed=False))
        session.flush()
    profile = session.get(Profile, user.id)
    profile.chat_llm_consent_at = now() if command == "/llm_on" else None
    return ("Согласие на передачу очищенного текста вопроса DeepSeek сохранено. "
            "Квитанции из мини-приложения требуют отдельного подтверждения правил обработки."
            if command == "/llm_on" else
            "Согласие на передачу текста вопроса DeepSeek отозвано.")


def start_keyboard(settings: object) -> list[dict]:
    open_app = {"type": "open_app", "text": "Разобрать платёжку"}
    if settings.max_web_app:
        open_app["web_app"] = settings.max_web_app
    return [{"type": "inline_keyboard", "payload": {"buttons": [
        [{"type": "message", "text": "Задать вопрос"}], [open_app],
    ]}}]


def question_text(session, item: WebhookInbox, store: SqlStore) -> str | None:
    """Answer direct chat from the same owner-scoped facts as the mini-app."""
    if not item.max_user_id or not item.text:
        return None
    from app.services.assistant_adapter import answer_json
    from app.services.assistant_store import knowledge, owner_receipt_pair
    from app.services.cohort_store import city_comparison

    user = session.scalar(select(User).where(User.max_user_id == item.max_user_id).with_for_update())
    if user is None:
        user = User(id=uuid.uuid4(), max_user_id=item.max_user_id, created_at=now())
        session.add(user)
        # PostgreSQL may flush independent ORM objects in an order that violates
        # profiles_user_id_fkey when only scalar IDs (no relationship) are set.
        session.flush()
        session.add(Profile(user_id=user.id, role="other", territory_id=None,
                            onboarding_completed=False))
        session.flush()
    profile = session.get(Profile, user.id)
    context = {"territory_id": profile.territory_id, "role": profile.role,
               "topic_id": None, "organization_id": None, "service_code": None,
               "document_kind": None, "receipt_id": None, "receipt_revision": None}
    question = item.text
    prior = session.scalar(select(AssistantAnswer).where(
        AssistantAnswer.user_id == user.id,
        AssistantAnswer.created_at >= now() - timedelta(minutes=15),
    ).order_by(AssistantAnswer.created_at.desc(), AssistantAnswer.id.desc()).limit(1))
    if prior and prior.result.get("clarification"):
        clarification = prior.result["clarification"]
        context["topic_id"] = prior.result.get("topic_id")
        if clarification["field"] == "service_code":
            lowered = question.lower()
            for needle, code in (("горяч", "hot_water"), ("холод", "cold_water"),
                                 ("отоп", "heating"), ("элект", "electricity"),
                                 ("водоотвед", "drainage"), ("капремонт", "capital_repair"),
                                 ("мусор", "waste")):
                if needle in lowered:
                    context["service_code"] = code
                    break
        elif clarification["field"] == "document_kind":
            description = " ".join(question.split())[:200]
            if description:
                context["document_kind"] = description
        question = f"{prior.question[:1000]} {question[:900]}"
    personal, _ = owner_receipt_pair(store, str(user.id), db_session=session)
    try:
        result = answer_json(question, context, [],
                             {"role": profile.role, "territory_id": profile.territory_id},
                             knowledge(), api_key=store.settings.deepseek_api_key if (
                                 profile.chat_llm_consent_at is not None or
                                 profile.privacy_notice_version == store.settings.privacy_notice_version
                             ) else None,
                             model=store.settings.deepseek_model, personal_snapshots=personal,
                             allow_receipt_model=profile.privacy_notice_version ==
                             store.settings.privacy_notice_version,
                             city_lookup=lambda rid, code, metric: city_comparison(
                                 store, str(user.id), rid, code, metric))
    except Exception:
        # One malformed external response or exceptional engine record must not poison
        # the durable inbox and block later commands.
        result = {"status": "unsupported", "text": "Сейчас не удалось разобрать вопрос. Попробуйте ещё раз.",
                  "topic_id": None, "steps": [], "sources": [], "actions": [],
                  "clarification": None, "limitations": ["Временная ошибка ответа."],
                  "knowledge_version": knowledge().version, "receipt_ref": None}
    ref = result.get("receipt_ref")
    kind = personal[0]["dataset_kind"] if ref and personal else (
        "synthetic" if profile.territory_id == "demo-territory" else "public_reference")
    session.add(AssistantAnswer(id=uuid.uuid4(), user_id=user.id, question=question,
                                result=result, receipt_id=uuid.UUID(ref["id"]) if ref else None,
                                receipt_revision=ref["revision"] if ref else None,
                                dataset_kind=kind, created_at=now(),
                                expires_at=now() + timedelta(days=30)))
    response = result["text"]
    if result["clarification"]:
        response += "\n" + result["clarification"]["prompt"]
    if result["steps"]:
        response += "\n" + "\n".join(result["steps"])
    return response[:3900]


def process_inbox_once(store: SqlStore) -> bool:
    with store.Session.begin() as session:
        item = session.scalar(select(WebhookInbox).where(
            WebhookInbox.state == "queued", WebhookInbox.expires_at > now())
                              .order_by(WebhookInbox.created_at, WebhookInbox.id)
                              .with_for_update(skip_locked=True).limit(1))
        if item is None:
            return False
        reply = (command_text(item) or chat_consent_text(session, item, store.settings)
                 or question_text(session, item, store))
        if reply:
            command = (item.text or "").strip().lower()
            show_app_keyboard = item.event_type == "bot_started" or command in {"/start", "/help", "/llm_on"}
            session.add(Outbox(id=uuid.uuid4(), business_key=item.dedup_key,
                               max_user_id=item.max_user_id, text=reply,
                               attachments=start_keyboard(store.settings) if show_app_keyboard else [],
                               state="queued", attempt=0,
                               run_after=now(), created_at=now(),
                               expires_at=now() + timedelta(hours=24)))
        item.state = "done"
    return True


def send_text(settings: object, max_user_id: int, text: str, attachments: list[dict]) -> int:
    if not settings.max_bot_token:
        raise RuntimeError("MAX_BOT_TOKEN unavailable")
    url = settings.max_api_base_url.rstrip("/") + "/messages?" + urlencode({"user_id": max_user_id})
    body = {"text": text}
    if attachments:
        body["attachments"] = attachments
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method="POST", headers={
        "Authorization": settings.max_bot_token, "Content-Type": "application/json",
    })
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # Never forward Authorization to another origin.

    try:
        with build_opener(NoRedirect).open(request, timeout=3) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def process_outbox_once(store: SqlStore, sender=send_text) -> bool:
    with store.Session.begin() as session:
        item = session.scalar(select(Outbox).where(
            Outbox.state == "queued", Outbox.run_after <= now(), Outbox.expires_at > now())
                              .order_by(Outbox.run_after, Outbox.id)
                              .with_for_update(skip_locked=True).limit(1))
        if item is None:
            return False
        item.state = "sending"  # Crash after this point is an uncertain send, never auto-retried.
        item.attempt += 1
        item_id, recipient, content, attachments = item.id, item.max_user_id, item.text, item.attachments
    try:
        status = sender(store.settings, recipient, content, attachments)
    except (URLError, TimeoutError, OSError):
        status = None
    with store.Session.begin() as session:
        item = session.get(Outbox, item_id)
        if item is None or item.state != "sending":
            return True
        if status == 200:
            item.state = "sent"
        elif status is None:
            item.state = "uncertain"
        elif status in {429, 500, 502, 503, 504} and item.attempt < 3:
            item.state = "queued"
            item.run_after = now() + timedelta(seconds=2**item.attempt * 10)
        else:
            item.state = "failed"
    return True
