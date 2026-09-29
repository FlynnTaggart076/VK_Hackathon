"""Minimal durable MAX webhook and message outbox. No raw update or token is logged."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import DialogState, Outbox, Profile, User, WebhookInbox
from app.db.store import SqlStore, now
from app.errors import ApiError

log = logging.getLogger("app.max_queue")


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
    command = (item.text or "").strip().lower()
    if item.event_type == "bot_started" or command == "/start":
        return ("Помогу разобраться с ЖКХ: найду управляющую компанию и поставщиков по адресу дома, подскажу, "
                "куда передать показания, и объясню квитанцию. Выберите тему кнопкой или напишите вопрос. "
                "Чтобы разобрать квитанцию, откройте мини-приложение. Команда /help — возможности и ограничения.")
    if command == "/help":
        return ("Что я умею:\n"
                "• контакты УК и поставщиков по адресу дома (открытые данные HouseScore и Dominfo);\n"
                "• куда передавать показания и куда обращаться при проблемах с услугой;\n"
                "• объяснение квитанции и роста суммы — после загрузки квитанции в мини-приложении.\n"
                "Кнопка «Новый вопрос» или /reset начинает заново. Файлы и фото загружайте в мини-приложении. "
                "Голосовые сообщения и отправка обращений не поддерживаются.")
    if command == "задать вопрос":
        return ("Напишите текстовый вопрос о ЖКХ в этом личном диалоге — например, «контакты УК» "
                "или «куда передать показания воды».")
    if item.attachment_kind:
        return "Загрузите PDF или фото квитанции в мини-приложении. Голосовые сообщения не обрабатываются."
    identity_question = " ".join((item.text or "").strip().lower().strip("?!., ").split())
    if identity_question in {"кто ты", "кто ты такой", "что умеешь", "что ты умеешь", "что ты можешь"}:
        return ("Я помощник по начислениям ЖКХ в MAX. В чате отвечаю на текстовые вопросы о начислениях и "
                "нахожу контакты УК и поставщиков по адресу дома, а в мини-приложении помогаю разобрать "
                "подтверждённую квитанцию и сравнить месяцы. "
                "Голосовые сообщения и отправка обращений не поддерживаются. "
                "Чтобы открыть мини-приложение, отправьте /start.")
    return None


def command_text(item: WebhookInbox) -> str | None:
    result = _command_text(item)
    if result and (item.event_type == "bot_started" or
                   (item.text or "").strip().lower() in {"/start", "/help"}):
        result += ("\nДля понимания вопросов текст после удаления адреса, телефонов и номеров "
                   "может передаваться внешнему сервису DeepSeek — только с вашего согласия. Включить: /llm_on, "
                   "отключить: /llm_off. Адрес дома (без квартиры) используется только для поиска УК и "
                   "поставщиков в открытых справочниках. Не присылайте номер квартиры, лицевого счёта и документы.")
    return result


def _ensure_user(session, max_user_id: int) -> User:
    user = session.scalar(select(User).where(User.max_user_id == max_user_id).with_for_update())
    if user is None:
        user = User(id=uuid.uuid4(), max_user_id=max_user_id, created_at=now())
        session.add(user)
        # PostgreSQL may flush independent ORM objects in an order that violates
        # profiles_user_id_fkey when only scalar IDs (no relationship) are set.
        session.flush()
        session.add(Profile(user_id=user.id, role="other", territory_id=None,
                            onboarding_completed=False))
        session.flush()
    return user


def chat_consent_text(session, item: WebhookInbox, settings) -> str | None:
    command = (item.text or "").strip().lower()
    if not item.max_user_id or command not in {"/llm_on", "/llm_off"}:
        return None
    user = _ensure_user(session, item.max_user_id)
    profile = session.get(Profile, user.id)
    profile.chat_llm_consent_at = now() if command == "/llm_on" else None
    for row in session.scalars(select(DialogState).where(DialogState.user_id == user.id)):
        row.state = {**row.state, "llm_declined": command == "/llm_off", "consent_offered": True}
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
        [{"type": "message", "text": "Контакты поставщика"}, {"type": "message", "text": "Контакты УК"}],
        [{"type": "message", "text": "Передать показания"}, {"type": "message", "text": "Почему выросла сумма"}],
    ]}}]


def reply_keyboard(settings: object, reply: dict) -> list[dict]:
    """MAX inline keyboard for a dialogue reply: options as message buttons, https links as link buttons."""
    rows: list[list[dict]] = []
    short: list[dict] = []
    for option in reply.get("options", [])[:12]:
        button = {"type": "message", "text": option["label"][:128]}
        if len(option["label"]) <= 22:
            short.append(button)
            if len(short) == 2:
                rows.append(short)
                short = []
        else:
            if short:
                rows.append(short)
                short = []
            rows.append([button])
    if short:
        rows.append(short)
    links = [{"type": "link", "text": link["label"][:128], "url": link["url"]}
             for link in reply.get("links", [])[:3]
             if isinstance(link.get("url"), str) and link["url"].startswith("https://") and len(link["url"]) <= 2048]
    if links:
        rows.append(links)
    if reply.get("menu"):
        open_app = {"type": "open_app", "text": "Разобрать платёжку в мини-приложении"}
        if settings.max_web_app:
            open_app["web_app"] = settings.max_web_app
        rows.append([open_app])
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}] if rows else []


def _reply_text(reply: dict) -> str:
    text = reply["text"]
    if reply.get("links"):
        text += "\n\n" + "\n".join(f"{link['label']}: {link['url']}" for link in reply["links"][:3])
    return text[:3900]


def _enqueue_reply(session, item: WebhookInbox, text: str, attachments: list[dict]) -> None:
    session.add(Outbox(id=uuid.uuid4(), business_key=item.dedup_key,
                       max_user_id=item.max_user_id, text=text,
                       attachments=attachments, state="queued", attempt=0,
                       run_after=now(), created_at=now(),
                       expires_at=now() + timedelta(hours=24)))


def process_inbox_once(store: SqlStore) -> bool:
    """Commands are answered in one short transaction. Dialogue turns are computed outside any
    transaction (house lookup and DeepSeek may take seconds) and committed only if the inbox item
    is still queued, so a slow or failing external service never blocks the queue."""
    from app.services.dialog_store import commit_turn, compute_turn

    with store.Session.begin() as session:
        item = session.scalar(select(WebhookInbox).where(
            WebhookInbox.state == "queued", WebhookInbox.expires_at > now())
                              .order_by(WebhookInbox.created_at, WebhookInbox.id)
                              .with_for_update(skip_locked=True).limit(1))
        if item is None:
            return False
        reply = command_text(item) or chat_consent_text(session, item, store.settings)
        if reply or not item.max_user_id or not item.text:
            if reply:
                command = (item.text or "").strip().lower()
                show_app_keyboard = item.event_type == "bot_started" or command in {"/start", "/help", "/llm_on"}
                _enqueue_reply(session, item, reply, start_keyboard(store.settings) if show_app_keyboard else [])
            item.state = "done"
            return True
        user_id = str(_ensure_user(session, item.max_user_id).id)
        item_id, text = item.id, item.text
    try:
        turn = compute_turn(store, user_id, "max_chat", text, None)
        message, attachments = _reply_text(turn.reply), reply_keyboard(store.settings, turn.reply)
    except Exception:
        # One malformed external response or exceptional record must not poison the inbox.
        log.exception("dialogue turn failed")
        turn = None
        message = "Сейчас не удалось разобрать вопрос. Попробуйте ещё раз или нажмите «Новый вопрос»."
        attachments = reply_keyboard(store.settings, {"options": [{"value": "reset", "label": "Новый вопрос"}]})
    with store.Session.begin() as session:
        item = session.scalar(select(WebhookInbox).where(WebhookInbox.id == item_id)
                              .with_for_update(skip_locked=True))
        if item is None or item.state != "queued":
            return True  # Another processor finished it meanwhile.
        if turn is not None and not commit_turn(session, turn):
            log.info("dialogue state changed concurrently; reply sent without state update")
        _enqueue_reply(session, item, message, attachments)
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
