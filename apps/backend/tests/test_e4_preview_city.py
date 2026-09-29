"""Preview numbers use fixed artificial observations and an owned demo receipt only."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.db.models import Base, ReceiptCohortLine, ReceiptRevision
from app.db.store import SqlStore
from app.errors import ApiError
from app.jobs.worker import run_once
from app.main import Settings, create_app
from app.services.cohort_store import city_comparison, set_aggregate_consent
from app.services.preview_city import COHORT_FILE, FIXTURE_SCENARIOS, preview_city_comparison
from test_contract_responses import validate_response
from test_sql_store import migrate


EXPECTED = {
    "city-moscow-water-2026-08": ("256.00", "240.00", "200.00", "-56.00"),
    "city-moscow-water-2026-09": ("342.00", "315.00", "270.00", "-72.00"),
    "city-lyubertsy-water-2026-08": ("243.20", "228.00", "190.00", "-53.20"),
    "city-lyubertsy-water-2026-09": ("319.20", "294.00", "252.00", "-67.20"),
}


def _store(tmp_path: Path, mode: str = "preview") -> SqlStore:
    settings = Settings(mode=mode, preview_auth_enabled=mode == "preview",
                        engine_mode="real", database_url=f"sqlite:///{(tmp_path / 'preview.sqlite').as_posix()}",
                        storage_path=tmp_path / "private")
    store = SqlStore(settings)
    Base.metadata.create_all(store.engine)
    return store


def _guest(store: SqlStore, fixture_id: str) -> tuple[str, str, str]:
    session = store.authenticate_preview()
    user_id = session["user"]["id"]
    store.update_profile(user_id, {
        "role": "owner", "territory_id": FIXTURE_SCENARIOS[fixture_id][1],
        "privacy_notice_version": store.settings.privacy_notice_version,
        "privacy_acknowledged": True,
    })
    return user_id, session["access_token"], FIXTURE_SCENARIOS[fixture_id][1]


def _import_and_confirm(store: SqlStore, user_id: str, fixture_id: str) -> str:
    queued = store.import_demo(user_id, str(uuid.uuid4()), fixture_id)
    receipt_id = queued["receipt"]["id"]
    assert run_once(store)
    assert store.receipt(user_id, receipt_id)["status"] == "needs_review"
    store.confirm_revision(user_id, receipt_id, 1, [], str(uuid.uuid4()))
    return receipt_id


def test_all_city_scenarios_numbers_owner_and_real_isolation(tmp_path):
    store = _store(tmp_path)
    assert set(FIXTURE_SCENARIOS) == set(EXPECTED)
    for fixture_id, (expected_mean, expected_median, own, difference) in EXPECTED.items():
        user_id, _, territory = _guest(store, fixture_id)
        queued = store.import_demo(user_id, str(uuid.uuid4()), fixture_id)
        receipt_id = queued["receipt"]["id"]
        pending = preview_city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount")
        assert pending["status"] == "ineligible" and pending["sample_size"] is None
        assert run_once(store)
        store.confirm_revision(user_id, receipt_id, 1, [], str(uuid.uuid4()))
        charge = preview_city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount")
        validate_response("PreviewCityComparisonView", charge)
        assert charge["status"] == "available"
        assert charge["city"] == FIXTURE_SCENARIOS[fixture_id][0]
        assert charge["city_label"]
        assert charge["period"] == FIXTURE_SCENARIOS[fixture_id][2]
        assert charge["service_code"] == "cold_water"
        assert (charge["scope"], charge["segment_key"], charge["unit"]) == ("individual", None, "m3")
        assert (charge["sample_size"], charge["average"], charge["median"],
                charge["receipt_value"], charge["difference_from_average"]) == (
                    5, expected_mean, expected_median, own, difference)
        assert charge["comparison"] == "below"
        assert charge["difference_percent"].startswith("-21.")
        assert charge["provenance"] == "synthetic_preview_cohort"
        assert "учебн" in charge["explanation"].lower()
        tariff = preview_city_comparison(store, user_id, receipt_id, "cold_water", "tariff")
        expected_tariff = "40.000000" if fixture_id.endswith("08") and territory == "moscow" else (
            "45.000000" if territory == "moscow" else
            "38.000000" if fixture_id.endswith("08") else "42.000000")
        assert (tariff["average"], tariff["median"], tariff["receipt_value"],
                tariff["difference_from_average"], tariff["difference_percent"], tariff["comparison"]) == (
                    expected_tariff, expected_tariff, expected_tariff, "0.000000", "0.00", "equal")
        set_aggregate_consent(store, user_id, True)
        assert city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount")["status"] == "ineligible"
    with store.Session() as session:
        assert session.scalars(select(ReceiptCohortLine)).all() == []


def test_unavailable_suppresses_numbers_and_ownership(tmp_path):
    store = _store(tmp_path)
    fixture_id = "city-moscow-water-2026-08"
    user_id, _, _ = _guest(store, fixture_id)
    receipt_id = _import_and_confirm(store, user_id, fixture_id)
    stranger, _, _ = _guest(store, fixture_id)
    with pytest.raises(ApiError) as denied:
        preview_city_comparison(store, stranger, receipt_id, "cold_water", "charge_amount")
    assert denied.value.status == 404
    for code in ("hot_water", "other"):
        answer = preview_city_comparison(store, user_id, receipt_id, code, "charge_amount")
        assert answer["status"] == "ineligible"
        assert all(answer[key] is None for key in ("sample_size", "average", "median", "receipt_value",
                                              "difference_from_average", "difference_percent", "comparison"))
    for bad_metric in ("quantity", "", "charge_amount;select"):
        with pytest.raises(ApiError) as denial:
            preview_city_comparison(store, user_id, receipt_id, "cold_water", bad_metric)
        assert denial.value.status == 422
    document = json.loads(COHORT_FILE.read_text(encoding="utf-8"))
    document["groups"][0]["observations"].pop()
    short = tmp_path / "short.json"
    short.write_text(json.dumps(document), encoding="utf-8")
    under = preview_city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount",
                                    cohort_path=short)
    validate_response("PreviewCityComparisonView", under)
    assert under["status"] == "insufficient_data"
    assert all(under[key] is None for key in ("sample_size", "average", "median", "receipt_value",
                                             "difference_from_average", "difference_percent", "comparison"))
    document["groups"][0]["unit"] = "kwh"
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(document), encoding="utf-8")
    assert preview_city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount",
                                   cohort_path=wrong)["status"] == "insufficient_data"
    with store.Session.begin() as session:
        revision = session.get(ReceiptRevision, (uuid.UUID(receipt_id), 2))
        bill = dict(revision.bill_data)
        bill["address_text"] = "г. Москва, г. Люберцы, ул. Примерная"
        revision.bill_data = bill
    ambiguous = preview_city_comparison(store, user_id, receipt_id, "cold_water", "charge_amount")
    assert ambiguous["status"] == "ambiguous_city" and ambiguous["average"] is None


def test_generic_demo_and_production_http_gate(tmp_path, monkeypatch):
    store = _store(tmp_path)
    user_id, token, _ = _guest(store, "city-moscow-water-2026-08")
    generic = _import_and_confirm(store, user_id, "water-2026-08")
    assert preview_city_comparison(store, user_id, generic, "cold_water", "charge_amount")["status"] == "ineligible"
    city = _import_and_confirm(store, user_id, "city-moscow-water-2026-08")
    # SQLite is used only in this isolated route test; runtime preview validation still requires PostgreSQL.
    monkeypatch.setattr(Settings, "validate", lambda self: None)
    with TestClient(create_app(store.settings)) as client:
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(f"/api/v1/preview/receipts/{city}/city-comparison",
                              params={"service_code": "cold_water", "metric": "charge_amount"},
                              headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["average"] == "256.00"
        assert client.get(f"/api/v1/preview/receipts/{city}/city-comparison",
                          params={"service_code": "cold_water", "metric": "tariff"}).status_code == 401
    production = Settings(mode="production", engine_mode="real", database_url=store.settings.database_url,
                          storage_path=tmp_path / "private")
    with TestClient(create_app(production)) as client:
        denied = client.get(f"/api/v1/preview/receipts/{city}/city-comparison",
                            params={"service_code": "cold_water", "metric": "charge_amount"},
                            headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PREVIEW_DISABLED"
        import_denied = client.post("/api/v1/receipts/demo",
                                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                                    json={"fixture_id": "city-moscow-water-2026-08"})
        assert import_denied.status_code == 404


def test_preview_city_migrated_postgresql(tmp_path, monkeypatch):
    """CI supplies a disposable PostgreSQL 17 URL; no shared DB is modified."""
    base_url = os.environ.get("TEST_PREVIEW_POSTGRES_URL")
    if not base_url:
        pytest.skip("set TEST_PREVIEW_POSTGRES_URL for isolated PostgreSQL 17 test")
    assert base_url.startswith("postgresql+psycopg://") and "?" not in base_url
    schema = f"preview_city_{uuid.uuid4().hex}"
    admin = create_engine(base_url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped_url = f"{base_url}?{urlencode({'options': f'-csearch_path={schema}'})}"
    try:
        migrate(scoped_url, monkeypatch)
        settings = Settings(mode="preview", preview_auth_enabled=True, engine_mode="real",
                            database_url=scoped_url, storage_path=tmp_path / "private-pg")
        settings.validate()
        store = SqlStore(settings)
        user_id, token, _ = _guest(store, "city-moscow-water-2026-08")
        receipt_id = _import_and_confirm(store, user_id, "city-moscow-water-2026-08")
        with TestClient(create_app(settings)) as client:
            response = client.get(f"/api/v1/preview/receipts/{receipt_id}/city-comparison",
                                  params={"service_code": "cold_water", "metric": "charge_amount"},
                                  headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200, response.text
            assert response.json()["average"] == "256.00"
        with store.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM receipt_cohort_lines")).scalar_one() == 0
        store.engine.dispose()
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()
