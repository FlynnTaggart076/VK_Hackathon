"""DeepSeek wire guards, owner pairing, and MAX recovery without network calls."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.db.models import AssistantAnswer, Base, Outbox, Profile, Receipt, ReceiptRevision, User
from app.main import Settings, create_app
from app.services.assistant_adapter import answer_json
from app.services.assistant_store import knowledge, owner_receipt_pair
from app.services.deepseek import ModelUnavailable, _completion, classify
from app.services.max_queue import process_inbox_once
from housing_engine.epd import parse_epd_text


ROOT = Path(__file__).resolve().parents[3]


def _bill(period: str, *, account: str = "000123", provider: str = "demo-provider") -> dict:
    data = json.loads((ROOT / "fixtures/receipts/water-2026-08.json").read_text(encoding="utf-8"))
    data["period"] = period
    data["account_number"] = account
    data["provider_id"] = provider
    return data


def _insert(session, owner: uuid.UUID, period: str, **overrides) -> uuid.UUID:
    rid = uuid.uuid4()
    session.add(Receipt(id=rid, user_id=owner, status="confirmed", current_revision=1,
                        dataset_kind="user_provided", extraction_outcome="recognized",
                        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
    session.flush()
    session.add(ReceiptRevision(receipt_id=rid, revision=1, bill_data=_bill(period, **overrides),
                                extraction_meta={}, validation={"can_confirm": True},
                                confirmed_at=datetime.now(timezone.utc), engine_version="0.1.0"))
    return rid


def _store(tmp_path, **settings):
    url = f"sqlite:///{(tmp_path / 'e4.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    app = create_app(Settings(database_url=url, storage_path=tmp_path / "private", engine_mode="real",
                              **settings))
    return app


def test_owner_pair_requires_exact_previous_month_account_provider_and_owner(tmp_path):
    app = _store(tmp_path)
    a, b = uuid.uuid4(), uuid.uuid4()
    with app.state.store.Session.begin() as session:
        for uid in (a, b):
            session.add(User(id=uid))
        session.flush()
        for uid in (a, b):
            session.add(Profile(user_id=uid, role="owner", territory_id="moscow",
                                onboarding_completed=True, privacy_notice_version="2.0"))
        session.flush()
        _insert(session, a, "2026-06")
        latest = _insert(session, a, "2026-08")
        _insert(session, a, "2026-07", account="other-account")
        _insert(session, a, "2026-07", provider="other-provider")
        _insert(session, b, "2026-07")
    pair, profile = owner_receipt_pair(app.state.store, str(a))
    assert [item["id"] for item in pair] == [latest]
    assert profile["privacy_notice_version"] == "2.0"
    with app.state.store.Session.begin() as session:
        previous = _insert(session, a, "2026-07")
    pair, _ = owner_receipt_pair(app.state.store, str(a))
    assert [item["id"] for item in pair] == [latest, previous]


def test_model_json_validation_redacts_identifiers_and_falls_back():
    seen = {}

    class Response:
        status_code = 200
        content = b'ok'

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": '{"intent":"bill_rise","topic_id":"bill_change"}'}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            seen["url"] = url
            seen["body"] = kwargs["json"]
            return Response()

    with patch("app.services.deepseek.httpx.Client", Client):
        value = classify("Почему выросла сумма? Телефон +7 999 111 22 33", knowledge().topics,
                         "fixture-key", "deepseek-flash")
    assert value == {"intent": "bill_rise", "topic_id": "bill_change"}
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "+7 999 111 22 33" not in seen["body"]["messages"][1]["content"]

    with patch("app.services.assistant_adapter.classify", side_effect=ModelUnavailable()):
        context = {"territory_id": None, "role": "owner", "topic_id": None,
                   "organization_id": None, "service_code": None, "document_kind": None}
        result = answer_json("Почему выросла сумма?", context, [],
                             {"role": "owner", "territory_id": None}, knowledge(),
                             api_key="fixture-key")
    assert result["status"] == "answered" and "квитанц" in result["text"].lower()


def test_selected_topic_wins_and_fabricated_model_number_rejected():
    context = {"territory_id": "moscow", "role": "owner", "topic_id": "bill_change",
               "organization_id": None, "service_code": None, "document_kind": None}
    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "faq", "topic_id": "supplier_contacts"
    }), patch("app.services.assistant_adapter.phrase", return_value="Новый тариф 9999 рублей"):
        result = answer_json("Объясни начисления", context, [],
                             {"role": "owner", "territory_id": "moscow"}, knowledge(),
                             api_key="fixture-key")
    assert result["topic_id"] == "bill_change"
    assert "9999" not in result["text"]


def test_valid_model_faq_intent_overrides_trigger_word_heuristic():
    context = {"territory_id": "moscow", "role": "owner", "topic_id": None,
               "organization_id": None, "service_code": None, "document_kind": None}
    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "faq", "topic_id": "supplier_contacts"
    }), patch("app.services.assistant_adapter.phrase", side_effect=ModelUnavailable()):
        result = answer_json("Где посмотреть контакт поставщика, если тариф вырос везде?", context, [],
                             {"role": "owner", "territory_id": "moscow"}, knowledge(),
                             api_key="fixture-key")
    assert result["topic_id"] == "supplier_contacts"


def test_confirmed_epd_uses_pii_free_model_facts_and_rejects_fake_amount():
    source = (ROOT / "fixtures/receipts/epd-synthetic-2026-08.txt").read_text(encoding="utf-8")
    parsed = parse_epd_text(source, uuid.uuid4())
    bill = parsed.bill_data.model_dump(mode="json")
    receipt = {"id": uuid.uuid4(), "revision": 1, "bill_data": bill,
               "confirmed_at": datetime.now(timezone.utc), "dataset_kind": "user_provided"}
    context = {"territory_id": "moscow-oblast", "role": "owner", "topic_id": None,
               "organization_id": None, "service_code": None, "document_kind": None}
    seen = {}

    def safe_phrase(_question, facts, *_args):
        seen["facts"] = facts
        return "По подтверждённой квитанции видно состав начислений."

    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "bill_rise", "topic_id": "bill_change"
    }), patch("app.services.assistant_adapter.phrase", side_effect=safe_phrase) as model:
        result = answer_json("Почему вырос счёт?", context, [],
                             {"role": "owner", "territory_id": "moscow-oblast"}, knowledge(),
                             api_key="fixture-key", personal_snapshots=[receipt], allow_receipt_model=True)
    model.assert_called_once()
    assert result["text"].startswith("По подтверждённой квитанции")
    for private in (bill["account_number"], bill["address_text"], bill["issuer_name"]):
        if private:
            assert private not in seen["facts"]
    assert "services" in seen["facts"]
    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "bill_rise", "topic_id": "bill_change"
    }), patch("app.services.assistant_adapter.phrase", return_value="Начислено 9999 рублей"):
        rejected = answer_json("Почему вырос счёт?", context, [],
                               {"role": "owner", "territory_id": "moscow-oblast"}, knowledge(),
                               api_key="fixture-key", personal_snapshots=[receipt], allow_receipt_model=True)
    assert "9999" not in rejected["text"]


def test_max_model_failure_then_help_is_not_poisoned(tmp_path):
    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret",
                 deepseek_api_key="fixture-key")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=123))
        session.flush()
        session.add(Profile(user_id=uid, role="other", territory_id=None,
                            privacy_notice_version="1.0", chat_llm_consent_at=datetime.now(timezone.utc)))
    headers = {"X-Max-Bot-Api-Secret": "fixture_secret"}

    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": 123}, "recipient": {"chat_id": 456, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    with TestClient(app) as client:
        assert client.post("/integrations/max/webhook", json=event("e4-1", "Почему вырос счёт?"),
                           headers=headers).status_code == 200
        assert client.post("/integrations/max/webhook", json=event("e4-2", "/help"),
                           headers=headers).status_code == 200
    with patch("app.services.assistant_adapter.classify", side_effect=ModelUnavailable("timeout")) as model:
        assert process_inbox_once(app.state.store)
    model.assert_called_once()
    assert process_inbox_once(app.state.store)
    with app.state.store.Session() as session:
        answers = session.scalars(select(AssistantAnswer)).all()
        outgoing = session.scalars(select(Outbox)).all()
    assert len(answers) == 1 and len(outgoing) == 2
    assert any("DeepSeek" in item.text for item in outgoing)


def test_max_old_profile_never_sends_question_without_chat_consent(tmp_path):
    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret",
                 deepseek_api_key="fixture-key")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=123))
        session.flush()
        session.add(Profile(user_id=uid, role="owner", territory_id="moscow",
                            privacy_notice_version="1.0"))

    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": 123},
                            "recipient": {"chat_id": 456, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    headers = {"X-Max-Bot-Api-Secret": "fixture_secret"}
    with TestClient(app) as client:
        for mid, message in (("old-1", "Почему вырос счёт?"),
                             ("old-2", "/llm_on"), ("old-3", "Почему вырос счёт?"),
                             ("old-4", "/llm_off")):
            assert client.post("/integrations/max/webhook", json=event(mid, message),
                               headers=headers).status_code == 200
    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "bill_rise", "topic_id": "bill_change"
    }) as model:
        assert process_inbox_once(app.state.store)
        model.assert_not_called()
        assert process_inbox_once(app.state.store)  # consent
        assert process_inbox_once(app.state.store)
        model.assert_called_once()
        assert process_inbox_once(app.state.store)  # revoke
    with app.state.store.Session() as session:
        assert session.get(Profile, uid).chat_llm_consent_at is None


def test_max_clarification_followup_preserves_topic_and_service(tmp_path):
    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=123))
        session.flush()
        session.add(Profile(user_id=uid, role="owner", territory_id="moscow"))
        session.add(AssistantAnswer(id=uuid.uuid4(), user_id=uid,
                                    question="Контакт поставщика по начислению",
                                    result={"status": "needs_clarification", "text": "Уточните услугу",
                                            "topic_id": "contact_supplier", "steps": [], "sources": [],
                                            "actions": [], "clarification": {"field": "service_code",
                                                                       "prompt": "По какой услуге?", "options": []},
                                            "limitations": [], "knowledge_version": knowledge().version,
                                            "receipt_ref": None},
                                    receipt_id=None, receipt_revision=None, dataset_kind="public_reference",
                                    created_at=datetime.now(timezone.utc),
                                    expires_at=datetime.now(timezone.utc)))
    event = {"update_type": "message_created", "timestamp": 1_700_000_000_000,
             "message": {"sender": {"user_id": 123},
                         "recipient": {"chat_id": 456, "chat_type": "dialog"},
                         "body": {"mid": "e4-followup", "text": "горячая вода"}}}
    with TestClient(app) as client:
        assert client.post("/integrations/max/webhook", json=event,
                           headers={"X-Max-Bot-Api-Secret": "fixture_secret"}).status_code == 200
    seen = {}
    original = answer_json

    def capture(question, context, *args, **kwargs):
        seen["question"] = question
        seen["context"] = dict(context)
        return original(question, context, *args, **kwargs)

    with patch("app.services.assistant_adapter.answer_json", side_effect=capture):
        assert process_inbox_once(app.state.store)
    assert seen["context"]["topic_id"] == "contact_supplier"
    assert seen["context"]["service_code"] == "hot_water"
    assert "Контакт поставщика" in seen["question"]
