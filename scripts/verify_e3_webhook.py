"""Offline PG webhook smoke inside the isolated Compose worker container.

Requires MAX_WEBHOOK_SECRET and DATABASE_URL from Compose, but deliberately
requires MAX_BOT_TOKEN to be empty. No event, secret or reply is printed.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import AssistantAnswer, Outbox, Profile, User, WebhookInbox
from app.services.max_queue import normalize_update


def post(url: str, body: bytes, secret: str) -> int:
    request = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Max-Bot-Api-Secret": secret,
    })
    try:
        with urlopen(request, timeout=5) as response:
            return response.status
    except HTTPError as error:
        return error.code


def main() -> None:
    secret = os.environ["MAX_WEBHOOK_SECRET"]
    if not secret or os.environ.get("MAX_BOT_TOKEN"):
        raise AssertionError("offline webhook smoke requires a secret and no bot token")
    url = os.environ.get("WEBHOOK_URL", "http://api:8000/integrations/max/webhook")
    event = {
        "update_type": "message_created", "timestamp": 1_700_000_000_000,
        "message": {
            "sender": {"user_id": 123},
            "recipient": {"chat_id": 456, "chat_type": "dialog"},
            "body": {"mid": str(uuid.uuid4()), "text": "/start"},
        },
    }
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    dedup_key = normalize_update(event).dedup_key
    if post(url, body, "invalid") != 403:
        raise AssertionError("webhook accepted a wrong secret")
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: post(url, body, secret), range(4)))
    if statuses != [200] * 4:
        raise AssertionError(f"webhook replay HTTP statuses: {statuses}")

    engine = create_engine(os.environ["DATABASE_URL"])
    for _ in range(40):
        with Session(engine) as session:
            inbox = session.scalars(select(WebhookInbox).where(
                WebhookInbox.dedup_key == dedup_key)).all()
            outbox = session.scalars(select(Outbox).where(
                Outbox.business_key == dedup_key)).all()
            if len(inbox) == 1 and len(outbox) == 1 and inbox[0].state == "done":
                if outbox[0].state != "queued" or outbox[0].attempt != 0:
                    raise AssertionError("offline outbox was sent or mutated")
                if outbox[0].max_user_id != 123 or not outbox[0].text:
                    raise AssertionError("outbox recipient or reply is missing")
                buttons = outbox[0].attachments[0]["payload"]["buttons"]
                if buttons[0][0]["type"] != "message" or buttons[1][0]["type"] != "open_app":
                    raise AssertionError("start keyboard was not persisted")
                break
            if len(inbox) > 1 or len(outbox) > 1:
                raise AssertionError("webhook replay created duplicate rows")
        time.sleep(0.5)
    else:
        raise AssertionError("webhook inbox was not processed into a single outbox row")

    # A first free-text message creates a User and Profile. This sequence must
    # run against PostgreSQL: SQLite's default FK behavior missed this path.
    questions = [
        "Напиши алгоритм сортировки",  # off topic
        "Почему платёжка стала дороже?",
        "/help",
    ]
    keys = []
    for question in questions:
        update = {
            "update_type": "message_created", "timestamp": 1_700_000_000_001,
            "message": {
                "sender": {"user_id": 123},
                "recipient": {"chat_id": 456, "chat_type": "dialog"},
                "body": {"mid": str(uuid.uuid4()), "text": question},
            },
        }
        keys.append(normalize_update(update).dedup_key)
        if post(url, json.dumps(update, separators=(",", ":")).encode("utf-8"), secret) != 200:
            raise AssertionError("synthetic webhook was rejected")

    for _ in range(40):
        with Session(engine) as session:
            inbox = session.scalars(select(WebhookInbox).where(WebhookInbox.dedup_key.in_(keys))).all()
            outbox = session.scalars(select(Outbox).where(Outbox.business_key.in_(keys))).all()
            if len(inbox) == len(outbox) == 3 and all(row.state == "done" for row in inbox):
                assert all(row.state == "queued" and row.attempt == 0 for row in outbox)
                user = session.scalar(select(User).where(User.max_user_id == 123))
                assert user is not None and session.get(Profile, user.id) is not None
                answers = session.scalars(select(AssistantAnswer).where(
                    AssistantAnswer.user_id == user.id)).all()
                assert len(answers) == 2
                assert {row.result["status"] for row in answers} == {"unsupported", "answered"}
                print("E3 webhook PG new-user text sequence and offline outbox: OK")
                return
        time.sleep(0.5)
    raise AssertionError("synthetic text sequence blocked the PostgreSQL inbox")


if __name__ == "__main__":
    main()
