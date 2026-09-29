"""Isolated derived cohort tests; synthetic fixture values model real rows only inside test DB."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text

from app.db.models import Base, Outbox, Profile, Receipt, ReceiptCohortLine, ReceiptRevision, User
from app.db.store import SqlStore
from app.main import Settings
from app.services.assistant_adapter import answer_json
from app.services.assistant_store import knowledge, owner_receipt_pair
from app.services.cohort_store import canonical_city, city_comparison, set_aggregate_consent
from app.services.max_queue import NormalizedUpdate, enqueue_update, process_inbox_once


ROOT = Path(__file__).resolve().parents[3]


def _bill(period: str, amount: str, *, city="г. Москва, ул. Тестовая, дом 1") -> dict:
    bill = json.loads((ROOT / "fixtures/receipts/water-2026-08.json").read_text(encoding="utf-8"))
    bill["period"] = period
    bill["address_text"] = city
    bill["services"][0]["charge_amount"] = amount
    bill["services"][0]["tariff"] = "10.000000"
    bill["services"] = bill["services"][:1]
    return bill


def _seed(store, index: int, period="2026-08", amount="100.00", *,
          city="г. Москва, ул. Тестовая, дом 1", dataset_kind="user_provided"):
    uid, rid = uuid.uuid4(), uuid.uuid4()
    with store.Session.begin() as session:
        session.add(User(id=uid, max_user_id=10000 + index))
        session.flush()
        session.add(Profile(user_id=uid, role="owner", territory_id="moscow",
                            onboarding_completed=True, privacy_notice_version="3.0"))
        session.add(Receipt(id=rid, user_id=uid, status="confirmed", current_revision=1,
                            dataset_kind=dataset_kind, extraction_outcome="recognized",
                            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        session.flush()
        session.add(ReceiptRevision(receipt_id=rid, revision=1, bill_data=_bill(period, amount, city=city),
                                    extraction_meta={}, validation={"can_confirm": True},
                                    confirmed_at=datetime.now(timezone.utc), engine_version="0.1.0"))
    return str(uid), str(rid)


def _add_prior(store, owner: str, amount: str):
    rid = uuid.uuid4()
    with store.Session.begin() as session:
        session.add(Receipt(id=rid, user_id=uuid.UUID(owner), status="confirmed", current_revision=1,
                            dataset_kind="user_provided", extraction_outcome="recognized",
                            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        session.flush()
        session.add(ReceiptRevision(receipt_id=rid, revision=1,
                                    bill_data=_bill("2026-07", amount), extraction_meta={},
                                    validation={"can_confirm": True},
                                    confirmed_at=datetime.now(timezone.utc), engine_version="0.1.0"))
    set_aggregate_consent(store, owner, True)


def _run(store):
    owners = [_seed(store, i, amount=f"{100 + 10*i}.00") for i in range(5)]
    for uid, _ in owners[:4]:
        assert set_aggregate_consent(store, uid, True) == {"aggregate_opt_in": True}
    query = lambda: city_comparison(store, owners[0][0], owners[0][1], "cold_water", "charge_amount")
    under = query()
    assert under["status"] == "insufficient_data"
    assert under["sample_size"] is under["average"] is under["median"] is None
    snapshots, profile = owner_receipt_pair(store, owners[0][0])
    context = {"territory_id": "moscow", "role": "owner", "topic_id": None,
               "organization_id": None, "service_code": "cold_water", "document_kind": None}
    city_lookup = lambda rid, code, metric: city_comparison(store, owners[0][0], rid, code, metric)
    under_answer = answer_json("У всех по городу выросла холодная вода?", context, [], profile,
                               knowledge(), personal_snapshots=snapshots, city_lookup=city_lookup)
    assert "недостаточно" in under_answer["text"].lower()
    assert "120.00" not in under_answer["text"]
    set_aggregate_consent(store, owners[4][0], True)
    enough = query()
    assert enough == {
        "status": "available", "city": "moskva", "period": "2026-08",
        "service_code": "cold_water", "unit": "m3", "metric": "charge_amount",
        "sample_size": 5, "average": "120.00", "median": "120.00",
        "provenance": "confirmed_opted_in_real_receipts",
    }
    enough_answer = answer_json("У всех по городу выросла холодная вода?", context, [], profile,
                                knowledge(), personal_snapshots=snapshots, city_lookup=city_lookup)
    assert "120.00" in enough_answer["text"]
    assert "предыдущий месяц" in enough_answer["text"]
    for i, (uid, _) in enumerate(owners[:4]):
        _add_prior(store, uid, f"{80 + 10*i}.00")
    pair, profile = owner_receipt_pair(store, owners[0][0])
    no_trend = answer_json("У всех по городу выросла холодная вода?", context, [], profile,
                           knowledge(), personal_snapshots=pair, city_lookup=city_lookup)
    assert "рост не установлен" in no_trend["text"]
    assert "разница средних" not in no_trend["text"]
    _add_prior(store, owners[4][0], "120.00")
    with_trend = answer_json("У всех по городу выросла холодная вода?", context, [], profile,
                             knowledge(), personal_snapshots=pair, city_lookup=city_lookup)
    assert "разница средних +20.00 руб" in with_trend["text"]
    for changed_field, new_value in (("city", "lyubertsy"), ("period", "2026-06")):
        def mismatched(rid, code, metric):
            result = city_lookup(rid, code, metric)
            if rid == str(pair[1]["id"]):
                result = {**result, changed_field: new_value}
            return result
        mismatch = answer_json("У всех по городу выросла холодная вода?", context, [], profile,
                               knowledge(), personal_snapshots=pair, city_lookup=mismatched)
        assert "городской рост не установлен" in mismatch["text"]
        assert "разница средних" not in mismatch["text"]
    tariff_answer = answer_json("Тариф на холодную воду по городу?", context, [], profile,
                                knowledge(), personal_snapshots=pair, city_lookup=city_lookup)
    assert "средний тариф" in tariff_answer["text"]
    duplicate = json.loads(json.dumps(pair[0], default=str))
    duplicate["bill_data"]["services"].append(dict(duplicate["bill_data"]["services"][0]))
    duplicate_answer = answer_json("Везде по городу выросла холодная вода?", context, [], profile,
                                   knowledge(), personal_snapshots=[duplicate], city_lookup=city_lookup)
    assert "пока недоступно" in duplicate_answer["text"]
    assert "Выберите" not in duplicate_answer["text"]
    enqueue_update(store, NormalizedUpdate("city-chat-test", "message_created", 10000, 10000,
                                           "Везде по городу выросла холодная вода?", None))
    assert process_inbox_once(store)
    with store.Session() as session:
        outgoing = session.scalars(select(Outbox).where(Outbox.business_key == "city-chat-test")).one()
        assert "разница средних +20.00 руб" in outgoing.text
    tariff = city_comparison(store, owners[0][0], owners[0][1], "cold_water", "tariff")
    assert tariff["status"] == "available" and tariff["average"] == "10.000000"
    # Cross-owner raw receipt ID is never usable as a query pivot.
    with pytest.raises(Exception) as denial:
        city_comparison(store, owners[0][0], owners[1][1], "cold_water", "charge_amount")
    assert getattr(denial.value, "status", None) == 404
    # Revocation removes derived rows immediately and suppresses the number.
    set_aggregate_consent(store, owners[4][0], False)
    assert query()["status"] == "insufficient_data"
    with store.Session() as session:
        assert session.scalars(select(ReceiptCohortLine).where(
            ReceiptCohortLine.user_id == uuid.UUID(owners[4][0]))).all() == []
    set_aggregate_consent(store, owners[4][0], True)
    store.delete_receipt(*owners[4])
    assert query()["status"] == "insufficient_data"
    # A synthetic document with consent can never fill the fifth real slot.
    synthetic = _seed(store, 20, amount="999.00", dataset_kind="synthetic")
    set_aggregate_consent(store, synthetic[0], True)
    assert query()["status"] == "insufficient_data"


def test_canonical_city_and_consent_sqlite(tmp_path):
    assert canonical_city("Московская область, г. Люберцы, ул. Тестовая", "moscow-oblast") == "lyubertsy"
    assert canonical_city("Московская область", "moscow-oblast") is None
    assert canonical_city("г. Москва, г. Люберцы", "moscow") is None
    url = f"sqlite:///{(tmp_path / 'cohort.sqlite').as_posix()}"
    settings = Settings(database_url=url, storage_path=tmp_path / "private")
    store = SqlStore(settings)
    Base.metadata.create_all(store.engine)
    _run(store)


def test_catchall_other_never_forms_a_cohort(tmp_path):
    url = f"sqlite:///{(tmp_path / 'other.sqlite').as_posix()}"
    store = SqlStore(Settings(database_url=url, storage_path=tmp_path / "private-other"))
    Base.metadata.create_all(store.engine)
    owners = [_seed(store, i + 30) for i in range(5)]
    for i, (uid, rid) in enumerate(owners):
        with store.Session.begin() as session:
            revision = session.get(ReceiptRevision, (uuid.UUID(rid), 1))
            bill = dict(revision.bill_data)
            bill["services"] = [{**bill["services"][0], "service_code": "other",
                                 "raw_name": "Видеонаблюдение" if i % 2 else "Газ"}]
            revision.bill_data = bill
        set_aggregate_consent(store, uid, True)
    assert city_comparison(store, owners[0][0], owners[0][1], "other", "charge_amount")["status"] == "ineligible"
    with store.Session() as session:
        assert session.scalars(select(ReceiptCohortLine)).all() == []


def test_canonical_city_and_consent_postgresql(tmp_path):
    base_url = os.environ.get("TEST_POSTGRES_URL")
    if not base_url:
        pytest.skip("set TEST_POSTGRES_URL for isolated PostgreSQL 17 test")
    assert base_url.startswith("postgresql+psycopg://")
    schema = "cohort_" + uuid.uuid4().hex[:12]
    admin = create_engine(base_url)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        scoped_url = base_url + ("&" if "?" in base_url else "?") + f"options=-csearch_path%3D{schema}"
        settings = Settings(database_url=scoped_url, storage_path=tmp_path / "private-pg")
        store = SqlStore(settings)
        Base.metadata.create_all(store.engine)
        _run(store)
        with store.engine.connect() as connection:
            assert connection.execute(text("SELECT pg_typeof(bill_data)::text FROM receipt_revisions LIMIT 1")).scalar_one() == "jsonb"
        store.engine.dispose()
    finally:
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
