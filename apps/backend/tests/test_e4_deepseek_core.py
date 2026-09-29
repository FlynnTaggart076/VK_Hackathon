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
                                onboarding_completed=True, privacy_notice_version="3.0"))
        session.flush()
        _insert(session, a, "2026-06")
        latest = _insert(session, a, "2026-08")
        _insert(session, a, "2026-07", account="other-account")
        _insert(session, a, "2026-07", provider="other-provider")
        _insert(session, b, "2026-07")
    pair, profile = owner_receipt_pair(app.state.store, str(a))
    assert [item["id"] for item in pair] == [latest]
    assert profile["privacy_notice_version"] == "3.0"
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


def test_synthetic_demo_receipt_model_projection_excludes_identity_and_raw_name():
    bill = _bill("2026-08")
    bill["address_text"] = "СЕКРЕТНЫЙ АДРЕС"
    bill["account_number"] = "СЕКРЕТНЫЙ СЧЕТ"
    bill["issuer_name"] = "СЕКРЕТНЫЙ ПОСТАВЩИК"
    bill["services"][0]["raw_name"] = "СЕКРЕТНОЕ НАЗВАНИЕ УСЛУГИ"
    snapshot = {"id": uuid.uuid4(), "revision": 1, "bill_data": bill,
                "confirmed_at": datetime.now(timezone.utc), "dataset_kind": "synthetic"}
    context = {"territory_id": "demo-territory", "role": "owner", "topic_id": None,
               "organization_id": None, "service_code": None, "document_kind": None}
    seen = {}

    def capture(_question, facts, *_args):
        seen["facts"] = facts
        return "Учебная квитанция показывает состав начислений."

    with patch("app.services.assistant_adapter.classify", return_value={
        "intent": "bill_rise", "topic_id": "bill_change"
    }), patch("app.services.assistant_adapter.phrase", side_effect=capture):
        result = answer_json("Почему вырос счёт?", context, [],
                             {"role": "owner", "territory_id": "demo-territory"}, knowledge(),
                             api_key="fixture-key", personal_snapshots=[snapshot],
                             allow_receipt_model=True)
    assert result["text"].startswith("Учебная квитанция")
    assert "synthetic_demo_receipt" in seen["facts"]
    for secret in (bill["address_text"], bill["account_number"], bill["issuer_name"],
                   bill["services"][0]["raw_name"]):
        assert secret not in seen["facts"]


def test_max_model_failure_then_help_is_not_poisoned(tmp_path):
    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret",
                 deepseek_api_key="fixture-key")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=123))
        session.flush()
        session.add(Profile(user_id=uid, role="other", territory_id=None, privacy_notice_version="1.0"))
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
    with patch("app.services.deepseek.route", side_effect=ModelUnavailable("timeout")) as router, \
            patch("app.services.assistant_adapter.classify", side_effect=AssertionError("single model call")):
        assert process_inbox_once(app.state.store)
    router.assert_called_once()
    assert process_inbox_once(app.state.store)
    with app.state.store.Session() as session:
        answers = session.scalars(select(AssistantAnswer)).all()
        outgoing = session.scalars(select(Outbox)).all()
    assert len(answers) == 1 and len(outgoing) == 2  # The rule-based path answered despite the failure.
    assert any("DeepSeek" in item.text for item in outgoing)


def test_max_deepseek_is_on_by_default_and_llm_off_opts_out(tmp_path):
    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret",
                 deepseek_api_key="fixture-key")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=123))
        session.flush()
        session.add(Profile(user_id=uid, role="owner", territory_id="moscow", privacy_notice_version="1.0"))

    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": 123},
                            "recipient": {"chat_id": 456, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    headers = {"X-Max-Bot-Api-Secret": "fixture_secret"}
    with TestClient(app) as client:
        for mid, message in (("d-1", "Почему вырос счёт?"), ("d-2", "/llm_off"),
                             ("d-3", "Почему вырос счёт?"), ("d-4", "/llm_on"), ("d-5", "Почему вырос счёт?")):
            assert client.post("/integrations/max/webhook", json=event(mid, message),
                               headers=headers).status_code == 200
    decision = {"kind": "run", "action": {"function": "bill_rise", "params": {}}, "text": "", "options": []}
    with patch("app.services.deepseek.route", return_value=decision) as router:
        assert process_inbox_once(app.state.store)
        router.assert_called_once()  # On by default, no consent step.
        assert process_inbox_once(app.state.store)  # /llm_off
        assert process_inbox_once(app.state.store)
        router.assert_called_once()  # Opted out: the rules answer, nothing goes to the model.
        assert process_inbox_once(app.state.store)  # /llm_on
        assert process_inbox_once(app.state.store)
        assert router.call_count == 2
    with app.state.store.Session() as session:
        profile = session.get(Profile, uid)
        assert profile.chat_llm_opt_out_at is None and profile.chat_llm_consent_at is not None


def _chat(app, user_id, texts):
    def event(mid, text):
        return {"update_type": "message_created", "timestamp": 1_700_000_000_000,
                "message": {"sender": {"user_id": user_id},
                            "recipient": {"chat_id": 456, "chat_type": "dialog"},
                            "body": {"mid": mid, "text": text}}}

    with TestClient(app) as client:
        for index, text in enumerate(texts):
            assert client.post("/integrations/max/webhook", json=event(f"{user_id}-{index}", text),
                               headers={"X-Max-Bot-Api-Secret": "fixture_secret"}).status_code == 200
            assert process_inbox_once(app.state.store)
    with app.state.store.Session() as session:
        return [row.text for row in session.scalars(select(Outbox).where(Outbox.max_user_id == user_id)
                                                      .order_by(Outbox.created_at, Outbox.id))]


def test_max_clarification_followup_preserves_topic_and_service(tmp_path):
    from app.db.models import DialogState

    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret")
    replies = _chat(app, 123, ["Контакт поставщика по начислению", "горячая вода"])
    assert "По какой услуге" in replies[0]
    assert "адрес дома" in replies[1].lower()
    with app.state.store.Session() as session:
        state = session.scalars(select(DialogState)).one().state
    assert state["topic_id"] == "supplier_contacts"
    assert state["service"] == "hot_water"
    assert state["awaiting"] == "address"


def test_document_kind_free_text_finishes_clarification(tmp_path):
    context = {"territory_id": "moscow", "role": "owner", "topic_id": "housing_document",
               "organization_id": None, "service_code": None,
               "document_kind": "справка о составе семьи"}
    answer = answer_json("Как получить справку о составе семьи?", context, [],
                         {"role": "owner", "territory_id": "moscow"}, knowledge())
    assert answer["status"] != "needs_clarification"

    app = _store(tmp_path, max_bot_token="fixture-token", max_webhook_secret="fixture_secret")
    uid = uuid.uuid4()
    with app.state.store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=223))
        session.flush()
        session.add(Profile(user_id=uid, role="owner", territory_id="moscow"))
    replies = _chat(app, 223, ["Как получить жилищный документ?", "справка о составе семьи"])
    assert "документ" in replies[0].lower()
    with app.state.store.Session() as session:
        latest = session.scalar(select(AssistantAnswer).where(AssistantAnswer.user_id == uid)
                                .order_by(AssistantAnswer.created_at.desc(), AssistantAnswer.id.desc()))
        assert latest.result["status"] != "needs_clarification"
        assert latest.question == "Как получить жилищный документ?"
