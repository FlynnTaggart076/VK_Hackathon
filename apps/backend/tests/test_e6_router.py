"""DeepSeek router: free text goes to the model, buttons never do; decisions stay inside the catalog."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.db.models import Base, DialogState, Outbox
from app.main import Settings, create_app
from app.services.capabilities import decode, system_prompt, validate_action, validate_decision
from app.services.max_queue import process_inbox_once
from test_contract_responses import validate_response
from test_e5_dialog import FakeLookup


@pytest.fixture
def app(tmp_path):
    url = f"sqlite:///{(tmp_path / 'router.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    return create_app(Settings(database_url=url, storage_path=tmp_path / "private", engine_mode="real",
                               demo_auth_enabled=True, demo_access_code="code", deepseek_api_key="fixture-key",
                               max_webhook_secret="fixture_secret", max_bot_token="fixture-token",
                               max_web_app="fixture_bot", house_lookup_cache_dir=tmp_path / "cache"))


def login(client):
    token = client.post("/api/v1/auth/demo", json={"access_code": "code", "identity": "reviewer_a"}).json()["access_token"]

    def say(message=None, choice=None, **extra):
        response = client.post("/api/v1/assistant/dialog", headers={"Authorization": f"Bearer {token}"},
                               json={"message": message, "choice": choice, **extra})
        assert response.status_code == 200, response.text
        validate_response("DialogReply", response.json())
        return response.json()
    return say


WATER = {"kind": "clarify", "text": "Что случилось с водой?", "options": [
    {"label": "Выросла сумма за воду", "function": "bill_rise", "params": {"service": "hot_water"}},
    {"label": "Нет воды", "function": "service_issue", "params": {"service": "cold_water"}},
    {"label": "Кто поставщик воды", "function": "supplier_contacts", "params": {"service": "cold_water"}},
    {"label": "Взломать сервер", "function": "shell", "params": {}}]}


def test_catalog_validation_rejects_anything_outside_it():
    assert validate_action("shell", {}) is None
    assert validate_action("faq", {}) is None  # The topic is required.
    assert validate_action("faq", {"topic": "adjustment"}) == {"function": "faq", "params": {"topic": "adjustment"}}
    assert validate_action("bill_rise", {"service": "plasma"}) == {"function": "bill_rise", "params": {}}
    assert validate_action("supplier_contacts", {"service": "management"})["function"] == "management_contacts"
    assert validate_decision({"kind": "answer", "text": "Откройте https://evil.example"}, "x") is None
    assert validate_decision({"kind": "answer", "text": "Позвоните +7 999 000-00-00"}, "x") is None
    assert validate_decision({"kind": "answer", "text": "Можно загрузить до 50 файлов"}, "x") is None
    assert validate_decision({"kind": "answer", "text": "PDF до 3 страниц и 10 МБ."}, "x")["kind"] == "answer"
    assert validate_decision({"kind": "clarify", "text": "?", "options": []}, "x") is None
    assert validate_decision({"kind": "delete_everything"}, "x") is None
    decision = validate_decision(WATER, "что-то с водой")
    assert [item["label"] for item in decision["options"]] == [
        "Выросла сумма за воду", "Нет воды", "Кто поставщик воды"]
    assert decode(decision["options"][0]["value"]) == {"function": "bill_rise", "params": {"service": "hot_water"}}
    prompt = system_prompt()
    assert "О приложении" in prompt and "supplier_contacts" in prompt and "только JSON" in prompt


def test_clarify_buttons_run_without_a_second_model_call(app):
    with TestClient(app) as client, patch("app.services.deepseek.route", return_value=WATER) as router, \
            patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        reply = say("у меня что-то с водой")
        assert reply["awaiting"] == "choice" and reply["text"] == "Что случилось с водой?"
        assert [item["label"] for item in reply["options"]] == [
            "Выросла сумма за воду", "Нет воды", "Кто поставщик воды", "Другое — напишу сам", "Новый вопрос"]
        rise = say(choice=reply["options"][0]["value"])
        assert router.call_count == 1
        assert any(action["target"] == "receipt_upload" for action in rise["actions"])  # No receipts yet.
        reply = say("у меня что-то с водой")
        supplier = say("Кто поставщик воды")  # Typed label of a shown button: no model call.
        assert router.call_count == 2
        assert supplier["awaiting"] == "address"
        other = say("у меня что-то с водой")
        assert say("Другое — напишу сам")["text"].startswith("Напишите одним сообщением")
        assert router.call_count == 3 and other["awaiting"] == "choice"


def test_answer_offtopic_and_invalid_decisions(app):
    with TestClient(app) as client:
        say = login(client)
        about = {"kind": "answer", "text": "Квитанцию загружают на вкладке «Платёжка»: PDF или фото до 10 МБ.",
                 "options": [{"label": "Загрузить квитанцию", "function": "receipt_upload", "params": {}}]}
        with patch("app.services.deepseek.route", return_value=about):
            reply = say("а как загрузить квитанцию?")
        assert reply["status"] == "answered" and "Платёжка" in reply["text"]
        upload = say(choice=reply["options"][0]["value"])
        assert upload["actions"][0]["target"] == "receipt_upload"
        with patch("app.services.deepseek.route", return_value={"kind": "offtopic", "text": "Я помогаю только с ЖКХ."}):
            reply = say("напиши стих про кота")
        assert reply["menu"] is True and reply["text"] == "Я помогаю только с ЖКХ."
        with patch("app.services.deepseek.route", return_value={"kind": "run", "action": {"function": "rm_rf"}}):
            reply = say("Почему выросла сумма в квитанции?")
        assert reply["topic_id"] == "bill_change"  # Rejected decision: the rule-based path answered.
        with patch("app.services.deepseek.route", side_effect=TimeoutError()):
            reply = say("какая у нас управляющая компания")
        assert reply["awaiting"] == "address"


def test_memory_keeps_last_three_redacted_exchanges(app):
    seen = []

    def remember(text, state, history, api_key, model):
        seen.append(history)
        return {"kind": "run", "action": {"function": "management_contacts", "params": {}}}

    with TestClient(app) as client, patch("app.services.deepseek.route", side_effect=remember), \
            patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        say("телефон управляющей компании нужен")  # Router → address question.
        say("Москва, ул. Примерная, д. 12, к. 2")  # Address: no router call.
        for question in ("а что там с моей управляющей", "позвони им сам", "как с ними связаться"):
            say(question)
    assert len(seen) == 4
    assert seen[0] == [] and len(seen[-1]) == 3
    flat = str(seen[-1])
    assert "Примерная" not in flat and "000-00-00" not in flat
    with app.state.store.Session() as session:
        assert len(session.scalars(select(DialogState)).one().state["history"]) == 3


def test_bot_buttons_from_router_are_message_buttons(app):
    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": 777}, "recipient": {"chat_id": 1, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    with TestClient(app) as client, patch("app.services.deepseek.route", return_value=WATER) as router, \
            patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        for index, text in enumerate(["у меня что-то с водой", "Нет воды"]):
            assert client.post("/integrations/max/webhook", json=event(f"r-{index}", text),
                               headers={"X-Max-Bot-Api-Secret": "fixture_secret"}).status_code == 200
            assert process_inbox_once(app.state.store)
    assert router.call_count == 1  # The tapped label is resolved from the saved buttons.
    with app.state.store.Session() as session:
        rows = session.scalars(select(Outbox).order_by(Outbox.created_at, Outbox.id)).all()
    first = [button["text"] for row in rows[0].attachments[0]["payload"]["buttons"] for button in row]
    assert "Выросла сумма за воду" in first and "Взломать сервер" not in first
    assert "адрес" in rows[1].text.lower()  # service_issue for cold water asks for the house.
