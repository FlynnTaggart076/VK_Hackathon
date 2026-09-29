"""Server-side dialogue for the mini-app and MAX chat: slots persist, clarifications never loop."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.db.models import AssistantAnswer, Base, DialogState, Outbox, Profile
from app.main import Settings, create_app
from app.services.deepseek import _redact
from app.services.house_lookup import LookupUnavailable
from app.services.max_queue import process_inbox_once
from test_contract_responses import validate_response

GUID_1 = "11111111-1111-4111-8111-111111111111"
GUID_2 = "22222222-2222-4222-8222-222222222222"
CANDIDATES = [{"fias_guid": GUID_1, "address": "г Москва, ул Примерная, д. 12, к. 1"},
              {"fias_guid": GUID_2, "address": "г Москва, ул Примерная, д. 12, к. 2"}]


def details(candidate):
    return {
        "address": candidate["address"], "fias_guid": candidate["fias_guid"], "house": {},
        "management": {"management_company": {"name": "ООО Учебная УК", "ogrn": 1027700000001}},
        "company": {"name": "ООО «Учебная УК»", "phone": "+7 (495) 000-00-00", "email": "uk@example.org"},
        "services": [
            {"service_code": "electricity", "service_name": "Электричество", "status": "candidate",
             "organization": "АО «Учебная энергосбытовая»", "organization_inn": "7700000002",
             "source_url": "https://dominfo.ru/dom/primernaya-12-2", "source_reviewed_at": "2026-09-29"},
            *[{"service_code": code, "service_name": code, "status": "unknown", "organization": None}
              for code in ("heating", "hot_water", "cold_water", "sewerage", "gas", "waste")],
        ],
        "warnings": ["Поставщики указаны по историческим данным; действующий договор с домом не проверен."],
        "sources": {"house": {"url": "https://housescore.ru/x", "fetched_at": "2026-09-29T00:00:00+00:00"},
                    "management": {"url": "https://housescore.ru/y", "fetched_at": "2026-09-29T00:00:00+00:00"},
                    "company": {"url": "https://housescore.ru/z", "fetched_at": "2026-09-29T00:00:00+00:00"},
                    "dominfo": None},
    }


class FakeLookup:
    def __init__(self, fail: str | None = None):
        self.queries = []
        self.fail = fail

    def find_houses(self, address, user_scope=None):
        if self.fail:
            raise LookupUnavailable(self.fail)
        self.queries.append(address)
        return list(CANDIDATES)

    def house_details(self, candidate):
        return details(candidate)


@pytest.fixture
def app(tmp_path):
    url = f"sqlite:///{(tmp_path / 'dialog.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    return create_app(Settings(database_url=url, storage_path=tmp_path / "private", engine_mode="real",
                               demo_auth_enabled=True, demo_access_code="code",
                               max_webhook_secret="fixture_secret", max_bot_token="fixture-token",
                               max_web_app="fixture_bot", house_lookup_cache_dir=tmp_path / "cache"))


def login(client, identity="reviewer_a"):
    token = client.post("/api/v1/auth/demo", json={"access_code": "code", "identity": identity}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def say(message=None, choice=None, **extra):
        response = client.post("/api/v1/assistant/dialog", json={"message": message, "choice": choice, **extra},
                               headers=headers)
        assert response.status_code == 200, response.text
        validate_response("DialogReply", response.json())
        return response.json()
    return say


def labels(reply):
    return [item["label"] for item in reply["options"]]


def test_supplier_contacts_asks_service_city_address_and_house(app):
    lookup = FakeLookup()
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=lookup):
        say = login(client)
        menu = say()
        assert "Контакты поставщика" in labels(menu)
        reply = say("хочу узнать контакт поставщика")
        assert reply["awaiting"] == "service" and "Электричество" in labels(reply)
        reply = say(choice="service:electricity")
        assert reply["awaiting"] == "address"
        reply = say("Москва")  # A city in plain words is accepted, the street is asked next.
        assert reply["awaiting"] == "address" and "в городе Москва" in reply["text"]
        reply = say("Примерная улица, дом 12")
        assert lookup.queries == ["Москва, Примерная улица, дом 12"]
        assert reply["awaiting"] == "house_choice" and len(reply["options"]) == 3
        reply = say("2")
        assert reply["status"] == "answered" and reply["card"]["service"]["code"] == "electricity"
        assert reply["card"]["provider"]["name"] == "АО «Учебная энергосбытовая»"
        assert "+7 (495) 000-00-00" in reply["text"]
        assert labels(reply) == ["Другая услуга", "Другой адрес", "Новый вопрос"]
        other = say("отопление")  # Another service for the same house without a new search.
        assert other["card"]["service"]["code"] == "heating" and other["card"]["provider"] is None
        assert lookup.queries == ["Москва, Примерная улица, дом 12"]


def test_remembered_house_is_reused_and_reset_keeps_it(app):
    lookup = FakeLookup()
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=lookup):
        say = login(client)
        say("Контакты УК Москва, ул. Примерная, д. 12, корпус 2")
        assert lookup.queries == ["Москва, ул. Примерная, д. 12, корпус 2"]
        say(reset=True)
        reply = say("какой телефон управляющей компании?")
        assert reply["card"]["service"]["code"] == "management"
        assert len(lookup.queries) == 1


def test_territory_clarification_accepts_typed_city_without_loop(app):
    with TestClient(app) as client:
        say = login(client)
        reply = say("Как получить жилищный документ?")
        assert reply["awaiting"] == "document_kind"
        reply = say("справка о составе семьи")
        assert reply["awaiting"] == "territory" and "Москва" in labels(reply)
        reply = say("Москва")
        assert reply["awaiting"] != "territory"
        if reply["awaiting"] == "role":
            reply = say("я собственник")
        assert reply["awaiting"] is None and reply["status"] != "needs_input"
    with app.state.store.Session() as session:
        assert all(row.territory_id is None for row in session.scalars(select(Profile)))  # Profile untouched.


def test_new_question_during_pending_address_starts_over(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        assert say("контакты поставщика")["awaiting"] == "service"
        assert say("Газ")["awaiting"] == "address"
        reply = say("Почему выросла сумма в квитанции?")
        assert reply["topic_id"] == "bill_change" and "квитанц" in reply["text"].lower()
        assert reply["awaiting"] is None


def test_off_topic_text_during_a_pending_choice_is_a_new_question(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        assert say("Где передать показания?")["awaiting"] == "service"
        assert say("вод")["awaiting"] == "service"  # A short unclear answer is asked again.
        reply = say("Напиши код сортировки")
        assert reply["awaiting"] is None and reply["menu"] is True


def test_unsupported_local_answer_offers_management_contacts(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        say("Контакты УК Москва, ул. Примерная, д. 12, корпус 2")  # Remembers a real territory.
        say(reset=True)
        say("Как получить жилищный документ?")
        reply = say("справка о составе семьи")
        if reply["awaiting"] == "role":
            reply = say("собственник")
        assert reply["status"] == "unsupported" and "Контакты УК" in labels(reply)
        card = say("Контакты УК")
        assert card["card"]["service"]["code"] == "management"


def test_address_or_city_without_a_question_asks_what_to_find(app):
    lookup = FakeLookup()
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=lookup):
        say = login(client)
        reply = say("Москва, ул. Примерная, д. 12, к. 2")
        assert reply["awaiting"] == "topic" and "Контакты УК" in labels(reply)
        card = say("Контакты УК")
        assert card["card"]["service"]["code"] == "management"
        reply = say("Люберцы")  # After a card a bare city means another house there.
        assert reply["awaiting"] == "address" and "в городе Люберцы" in reply["text"]


def test_bare_service_word_and_numbers_do_not_dead_end(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        say = login(client)
        reply = say("Электричество")
        assert reply["awaiting"] == "address"
        reply = say("контакт поставщика воды")
        assert reply["awaiting"] == "service" and labels(reply)[:2] == ["Холодная вода", "Горячая вода"]


def test_lookup_failure_offers_general_route(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for",
                                          return_value=FakeLookup(fail="quota")):
        say = login(client)
        reply = say("контакты ук Москва, ул. Примерная, д. 12, к. 2")
        assert reply["status"] == "unsupported" and "лимит" in reply["text"]
        assert any("cdn.dom.gosuslugi.ru" in link["url"] for link in reply["links"])


def test_dialogs_are_isolated_between_users(app):
    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        first = login(client, "reviewer_a")
        second = login(client, "reviewer_b")
        assert first("контакты поставщика")["awaiting"] == "service"
        assert second()["awaiting"] is None
        assert second("1")["awaiting"] != "service"
    with app.state.store.Session() as session:
        assert len(session.scalars(select(DialogState)).all()) == 2


def test_router_reads_free_text_by_default_but_never_addresses(app, tmp_path):
    url = f"sqlite:///{(tmp_path / 'router.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    router_app = create_app(Settings(database_url=url, storage_path=tmp_path / "p2", engine_mode="real",
                                     demo_auth_enabled=True, demo_access_code="code",
                                     deepseek_api_key="fixture-key", house_lookup_cache_dir=tmp_path / "c2"))
    decision = {"kind": "run", "action": {"function": "supplier_contacts", "params": {"service": "electricity"}}}
    with TestClient(router_app) as client, \
            patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()), \
            patch("app.services.deepseek.route", return_value=decision) as router, \
            patch("app.services.assistant_adapter.classify", side_effect=AssertionError("no second call")), \
            patch("app.services.assistant_adapter.phrase", side_effect=AssertionError("no phrasing")):
        say = login(client)
        reply = say("Привет")
        assert "Включить умные ответы" not in labels(reply)  # No consent step any more.
        router.assert_not_called()
        reply = say("кто подаёт нам свет в квартиру")
        router.assert_called_once()
        assert reply["awaiting"] == "address"
        say("Москва, ул. Примерная, д. 12")
        router.assert_called_once()  # The address turn never goes to the model.
        say("Без нейросети")
        with router_app.state.store.Session() as session:
            profile = session.scalars(select(Profile)).one()
            assert profile.chat_llm_opt_out_at is not None
        say("кто подаёт нам газ")
        router.assert_called_once()  # Opted out.
    assert "Примерная" not in _redact("Москва, ул. Примерная, д. 12, кв. 5")


def test_answers_endpoint_accepts_clarified_territory_without_profile_write(app):
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/demo", json={"access_code": "code", "identity": "reviewer_a"}).json()
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        context = {"territory_id": "moscow", "role": "owner", "topic_id": "housing_document",
                   "organization_id": None, "service_code": None, "document_kind": "справка",
                   "receipt_id": None, "receipt_revision": None}
        response = client.post("/api/v1/assistant/answers", headers=headers,
                               json={"question": "Как получить справку?", "context": context})
        assert response.status_code == 200
        assert (response.json().get("clarification") or {}).get("field") != "territory_id"
        assert client.get("/api/v1/me", headers=headers).json()["profile"]["territory_id"] is None


def test_max_chat_uses_buttons_and_continues_pending_question(app):
    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": 555}, "recipient": {"chat_id": 1, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    with TestClient(app) as client, patch("app.services.house_lookup.lookup_for", return_value=FakeLookup()):
        for index, text in enumerate(["Контакты поставщика", "Электричество", "Москва",
                                      "Примерная 12 корпус 2"]):
            assert client.post("/integrations/max/webhook", json=event(f"chat-{index}", text),
                               headers={"X-Max-Bot-Api-Secret": "fixture_secret"}).status_code == 200
            assert process_inbox_once(app.state.store)
    with app.state.store.Session() as session:
        rows = session.scalars(select(Outbox).order_by(Outbox.created_at, Outbox.id)).all()
        answers = session.scalars(select(AssistantAnswer)).all()
    texts = [row.text for row in rows]
    assert "По какой услуге" in texts[0]
    first_buttons = [button["text"] for row in rows[0].attachments[0]["payload"]["buttons"] for button in row]
    assert "Электричество" in first_buttons
    assert "адрес дома" in texts[1].lower()
    assert "в городе Москва" in texts[2]  # The city is not asked again.
    assert "Учебная энергосбытовая" in texts[3] and "+7 (495) 000-00-00" in texts[3]
    last_rows = rows[3].attachments[0]["payload"]["buttons"]
    assert any(button["type"] == "link" for row in last_rows for button in row)
    assert answers == []  # Contact cards are not engine answers.
    assert uuid.UUID(str(rows[0].id))


def test_bill_rise_without_receipts_offers_upload_button(app):
    from app.services.max_queue import reply_keyboard

    with TestClient(app) as client:
        say = login(client)
        reply = say(choice="intent:bill_rise")
        upload = [action for action in reply["actions"] if action["target"] == "receipt_upload"]
        assert upload and upload[0]["type"] == "navigate" and "Загрузить" in upload[0]["label"]
        rows = reply_keyboard(app.state.store.settings, reply)[0]["payload"]["buttons"]
        opens = [button for row in rows for button in row if button["type"] == "open_app"]
        assert opens and "Загрузить квитанцию" in opens[0]["text"]
