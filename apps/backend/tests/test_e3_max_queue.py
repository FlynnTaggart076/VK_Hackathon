"""Synthetic MAX webhook replay and durable outbox tests; never call MAX network."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.db.models import AssistantAnswer, Base, Outbox, WebhookInbox
from app.main import Settings, create_app
from app.services.assistant_store import knowledge
from app.services.max_queue import process_inbox_once, process_outbox_once


def event(mid: str, *, chat_type: str = "dialog", text: str = "/start") -> dict:
    return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
            "message": {"sender": {"user_id": 123},
                        "recipient": {"chat_id": 456, "chat_type": chat_type},
                        "body": {"mid": mid, "text": text}}}


def test_webhook_replay_and_bounded_outbox(tmp_path):
    url = f"sqlite:///{(tmp_path / 'max.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    settings = Settings(database_url=url, storage_path=tmp_path / "private",
                        max_webhook_secret="fixture_secret", max_bot_token="fixture-token")
    app = create_app(settings)
    with TestClient(app) as client:
        route = "/integrations/max/webhook"
        headers = {"X-Max-Bot-Api-Secret": "fixture_secret"}
        assert client.post(route, json=event("m-1")).status_code == 403
        assert client.post(route, json={"update_type": "message_created"}, headers=headers).status_code == 400
        for _ in range(2):
            response = client.post(route, json=event("m-1"), headers=headers)
            assert response.status_code == 200 and response.json() == {"accepted": True}
        with app.state.store.Session() as session:
            assert len(session.scalars(select(WebhookInbox)).all()) == 1
        assert process_inbox_once(app.state.store)
        assert not process_inbox_once(app.state.store)
        with app.state.store.Session() as session:
            rows = session.scalars(select(Outbox)).all()
            assert len(rows) == 1 and rows[0].state == "queued"
        sent = []
        assert process_outbox_once(app.state.store,
                                   sender=lambda _settings, uid, text: sent.append((uid, text)) or 200)
        assert sent[0][0] == 123 and "мини-приложение" in sent[0][1]
        assert not process_outbox_once(app.state.store, sender=lambda *_: 200)
        # Group messages are stored only as type/dedup metadata and never answered.
        assert client.post(route, json=event("m-2", chat_type="chat", text="private?"),
                           headers=headers).status_code == 200
        assert process_inbox_once(app.state.store)
        with app.state.store.Session() as session:
            rows = session.scalars(select(WebhookInbox)).all()
            group = next(row for row in rows if row.max_user_id is None)
            assert group.max_user_id is None and group.text is None
            assert len(session.scalars(select(Outbox)).all()) == 1
        assert client.post(route, json=event("m-4", text="Почему изменилась сумма?"),
                           headers=headers).status_code == 200
        assert process_inbox_once(app.state.store)
        with app.state.store.Session() as session:
            answer = session.scalar(select(AssistantAnswer))
            assert answer is not None and answer.result["status"] == "answered"
            assert answer.result["knowledge_version"] == knowledge().version
            replies = session.scalars(select(Outbox)).all()
            assert len(replies) == 2 and any(answer.result["text"] in row.text for row in replies)


def test_unknown_delivery_is_not_retried(tmp_path):
    url = f"sqlite:///{(tmp_path / 'uncertain.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    settings = Settings(database_url=url, storage_path=tmp_path / "private",
                        max_webhook_secret="fixture_secret", max_bot_token="fixture-token")
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.post("/integrations/max/webhook", json=event("m-3", text="/help"),
                           headers={"X-Max-Bot-Api-Secret": "fixture_secret"}).status_code == 200
    assert process_inbox_once(app.state.store)
    def timeout(*_args):
        raise TimeoutError
    assert process_outbox_once(app.state.store, sender=timeout)
    assert not process_outbox_once(app.state.store, sender=lambda *_: 200)
    with app.state.store.Session() as session:
        row = session.scalar(select(Outbox))
        assert row.state == "uncertain" and row.attempt == 1
