"""A real bytes-to-engine flow across persisted receipt revisions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from sqlalchemy import create_engine, select, text

from app.db.models import Document, Job, Receipt, ReceiptRevision
from app.db.store import now
from app.jobs.retention import run_retention_once
from app.services.revision_logic import rebase_evidence
from app.main import Settings, create_app
from app.jobs.worker import communicate_bounded, run_once
from test_contract_responses import validate_response
from test_dev_api import accept_privacy, headers, login, upload
from test_sql_store import migrate
from housing_engine import EngineError


FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "receipts" / "demo-bill-2026-08.pdf"


def test_real_bytes_edit_confirm_explain_after_restart(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'e2.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        owner = login(client, "reviewer_a")["access_token"]
        stranger = login(client, "reviewer_b")["access_token"]
        accept_privacy(client, owner)
        queued = upload(client, owner, str(uuid.uuid4()), data=FIXTURE.read_bytes(), mime="application/pdf")
        assert queued.status_code == 202
        receipt_id, job_id = queued.json()["receipt"]["id"], queued.json()["job_id"]
        assert client.get(f"/api/v1/receipts/{receipt_id}/explanation?revision=1", headers=headers(owner)).status_code == 409
        preview_url = f"/api/v1/receipts/{receipt_id}/pages/1"
        assert client.get(preview_url, headers=headers(owner)).json()["error"]["code"] == "PREVIEW_NOT_READY"
        assert run_once(client.app.state.store)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers(owner)).json()
        assert job["state"] == "succeeded", job
        receipt = client.get(f"/api/v1/receipts/{receipt_id}", headers=headers(owner)).json()
        validate_response("ReceiptView", receipt)
        assert receipt["extraction_outcome"] == "recognized"
        assert receipt["bill_data"]["document_total_due"] == "200.00"
        assert any(e["source"] == "pdf_text" for e in receipt["field_evidence"])
        assert client.get(f"/api/v1/receipts/{receipt_id}", headers=headers(stranger)).status_code == 404
        assert client.get(preview_url, headers=headers(stranger)).status_code == 404
        preview = client.get(preview_url, headers=headers(owner))
        assert preview.status_code == 200 and preview.content.startswith(b"\x89PNG\r\n\x1a\n")

        data = dict(receipt["bill_data"], issuer_name="Проверенное название")
        edit_url = f"/api/v1/receipts/{receipt_id}/draft"
        edited = client.put(edit_url, headers=headers(owner), json={"expected_revision": 1, "bill_data": data})
        assert edited.status_code == 200, edited.json()
        validate_response("ReceiptView", edited.json())
        assert edited.json()["revision"] == 2
        assert any(e["path"] == "/issuer_name" and e["source"] == "manual" for e in edited.json()["field_evidence"])
        stale = client.put(edit_url, headers=headers(owner), json={"expected_revision": 1, "bill_data": data})
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_CONFLICT"

        confirm_url = f"/api/v1/receipts/{receipt_id}/confirm"
        key = str(uuid.uuid4())
        confirmed = client.post(confirm_url, headers=headers(owner, key),
                                json={"expected_revision": 2, "acknowledged_warning_codes": []})
        assert confirmed.status_code == 200, confirmed.json()
        assert confirmed.json()["revision"] == 3 and confirmed.json()["status"] == "confirmed"
        replay = client.post(confirm_url, headers=headers(owner, key),
                             json={"expected_revision": 2, "acknowledged_warning_codes": []})
        assert replay.json() == confirmed.json()
        assert client.get(f"/api/v1/receipts/{receipt_id}/explanation?revision=2", headers=headers(owner)).status_code == 409
        assert client.get(f"/api/v1/receipts/{receipt_id}/explanation?revision=3", headers=headers(stranger)).status_code == 404
    with TestClient(create_app(settings)) as restarted:
        owner = login(restarted, "reviewer_a")["access_token"]
        explanation = restarted.get(f"/api/v1/receipts/{receipt_id}/explanation?revision=3", headers=headers(owner))
        assert explanation.status_code == 200, explanation.json()
        schema = json.loads((FIXTURE.parents[2] / "contracts" / "engine" / "v1" /
                             "ReceiptExplanation.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(explanation.json())
        assert explanation.json()["calculated_total_due"] == "200.00"
        assert explanation.json()["sources"] == []
        assert "ARITHMETIC_ONLY" in [item["code"] for item in explanation.json()["issues"]]
        next_bill = dict(confirmed.json()["bill_data"], issuer_name="Повторная правка")
        reopened = restarted.put(edit_url, headers=headers(owner),
                                 json={"expected_revision": 3, "bill_data": next_bill})
        assert reopened.status_code == 200, reopened.json()
        assert reopened.json()["revision"] == 4 and reopened.json()["status"] == "needs_review"
        assert restarted.get(f"/api/v1/receipts/{receipt_id}/explanation?revision=3",
                             headers=headers(owner)).status_code == 409
        with restarted.app.state.store.Session() as session:
            old_confirmed = session.get(ReceiptRevision, (uuid.UUID(receipt_id), 3))
            assert old_confirmed.confirmed_at is not None
            assert old_confirmed.bill_data["issuer_name"] == "Проверенное название"
    with TestClient(create_app(settings)) as restarted_again:
        owner = login(restarted_again, "reviewer_a")["access_token"]
        persisted = restarted_again.get(f"/api/v1/receipts/{receipt_id}", headers=headers(owner)).json()
        assert persisted["revision"] == 4 and persisted["bill_data"]["issuer_name"] == "Повторная правка"
        stale = restarted_again.put(edit_url, headers=headers(owner),
                                    json={"expected_revision": 3, "bill_data": next_bill})
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_CONFLICT"


def test_manual_receipt_is_owned_idempotent_and_server_canonical(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'manual.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        a = login(client, "reviewer_a")["access_token"]
        b = login(client, "reviewer_b")["access_token"]
        accept_privacy(client, a)
        bill = json.loads((FIXTURE.parent / "water-2026-08.json").read_text(encoding="utf-8"))
        bill["template_id"] = "client-forged-template"
        bill["settlement"]["formula_kind"] = "signed_balance_v1"
        bill["document_total_due"] = None
        key = str(uuid.uuid4())
        created = client.post("/api/v1/receipts/manual", headers=headers(a, key), json={"bill_data": bill})
        assert created.status_code == 201, created.json()
        validate_response("ReceiptView", created.json())
        assert created.json()["bill_data"]["template_id"] == "manual-v1"
        assert created.json()["bill_data"]["settlement"]["formula_kind"] == "unsupported"
        assert created.json()["extraction_outcome"] == "manual_required"
        rid = created.json()["id"]
        assert client.post("/api/v1/receipts/manual", headers=headers(a, key), json={"bill_data": bill}).json() == created.json()
        assert client.get(f"/api/v1/receipts/{rid}", headers=headers(b)).status_code == 404
        assert client.get(f"/api/v1/receipts/{rid}/source", headers=headers(a)).status_code == 404
        warnings = {item["code"] for item in created.json()["issues"] if item["severity"] == "warning"}
        assert "TOTAL_DUE_UNKNOWN" in warnings
        confirmation = f"/api/v1/receipts/{rid}/confirm"
        unacknowledged = client.post(confirmation, headers=headers(a, str(uuid.uuid4())),
                                     json={"expected_revision": 1, "acknowledged_warning_codes": []})
        assert unacknowledged.status_code == 422
        assert set(unacknowledged.json()["error"]["details"]["unacknowledged_warning_codes"]) <= warnings
        acknowledged = client.post(confirmation, headers=headers(a, str(uuid.uuid4())),
                                   json={"expected_revision": 1,
                                         "acknowledged_warning_codes": sorted(warnings)})
        assert acknowledged.status_code == 200, acknowledged.json()


@pytest.mark.parametrize("name,outcome", [
    ("demo-bill-2026-09-unknown-service.pdf", "partial"),
    ("unknown-layout.pdf", "manual_required"),
])
def test_real_worker_preserves_uncertain_outcome(tmp_path, monkeypatch, name, outcome):
    database_url = f"sqlite:///{(tmp_path / 'negative.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        token = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, token)
        response = upload(client, token, str(uuid.uuid4()), data=(FIXTURE.parent / name).read_bytes(),
                          mime="application/pdf")
        assert response.status_code == 202
        rid = response.json()["receipt"]["id"]
        assert run_once(client.app.state.store)
        receipt = client.get(f"/api/v1/receipts/{rid}", headers=headers(token)).json()
        assert receipt["status"] == "needs_review"
        assert receipt["extraction_outcome"] == outcome
        assert receipt["issues"]
        assert receipt["confirmed_at"] is None
        assert client.get(f"/api/v1/receipts/{rid}/explanation?revision=1", headers=headers(token)).status_code == 409


def test_e2_postgres_revisions_and_restart(tmp_path, monkeypatch):
    base_url = os.environ.get("TEST_E2_POSTGRES_URL")
    if not base_url:
        pytest.skip("set TEST_E2_POSTGRES_URL for isolated PostgreSQL")
    assert base_url.startswith("postgresql+psycopg://zhkh@127.0.0.1:")
    assert base_url.endswith("/zhkh_e2_test")
    schema = f"e2_test_{uuid.uuid4().hex}"
    admin = create_engine(base_url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    admin.dispose()
    database_url = f"{base_url}?{urlencode({'options': f'-csearch_path={schema}'})}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        identity = login(client, "reviewer_a")
        token, uid = identity["access_token"], identity["user"]["id"]
        accept_privacy(client, token)
        queued = upload(client, token, str(uuid.uuid4()), data=FIXTURE.read_bytes(),
                        mime="application/pdf").json()
        rid = queued["receipt"]["id"]
        assert run_once(client.app.state.store)
        current = client.get(f"/api/v1/receipts/{rid}", headers=headers(token)).json()
        assert current["status"] == "needs_review" and current["bill_data"]["period"] == "2026-08"
        bill = dict(current["bill_data"], issuer_name="Two editors")

        def edit():
            try:
                return client.app.state.store.edit_revision(
                    uid, rid, 1, bill, [], [], {"can_confirm": True, "errors": [], "warnings": []}, "test")
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: edit(), range(2)))
        assert sum(isinstance(item, dict) for item in outcomes) == 1
        assert "REVISION_CONFLICT" in outcomes
        with client.app.state.store.engine.connect() as connection:
            assert connection.execute(text("SELECT pg_typeof(bill_data)::text FROM receipt_revisions WHERE receipt_id=:rid AND revision=2"),
                                      {"rid": uuid.UUID(rid)}).scalar_one() == "jsonb"
    with TestClient(create_app(settings)) as restarted:
        token = login(restarted, "reviewer_a")["access_token"]
        current = restarted.get(f"/api/v1/receipts/{rid}", headers=headers(token)).json()
        assert current["revision"] == 2 and current["bill_data"]["issuer_name"] == "Two editors"


def test_source_and_receipt_retention_are_separate(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'retention.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        token = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, token)
        queued = upload(client, token, str(uuid.uuid4()), data=FIXTURE.read_bytes(),
                        mime="application/pdf").json()
        rid = queued["receipt"]["id"]
        assert run_once(client.app.state.store)
        with client.app.state.store.Session.begin() as session:
            receipt = session.get(Receipt, uuid.UUID(rid))
            session.get(Document, receipt.document_id).expires_at = now() - timedelta(seconds=1)
        run_retention_once(client.app.state.store)
        assert client.get(f"/api/v1/receipts/{rid}/source", headers=headers(token)).status_code == 410
        assert client.get(f"/api/v1/receipts/{rid}/pages/1", headers=headers(token)).status_code == 410
        retained = client.get(f"/api/v1/receipts/{rid}", headers=headers(token)).json()
        assert retained["bill_data"]["period"] == "2026-08"
        assert retained["document"]["available"] is False
        with client.app.state.store.Session.begin() as session:
            session.get(Receipt, uuid.UUID(rid)).created_at = now() - timedelta(days=31)
        run_retention_once(client.app.state.store)
        assert client.get(f"/api/v1/receipts/{rid}", headers=headers(token)).status_code == 404
        assert list(settings.storage_path.iterdir()) == []


def test_failed_retry_requires_live_source_and_replays_key(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'retry.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        token = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, token)
        queued = upload(client, token, str(uuid.uuid4()), data=FIXTURE.read_bytes(),
                        mime="application/pdf").json()
        rid = queued["receipt"]["id"]
        with client.app.state.store.Session.begin() as session:
            session.get(Receipt, uuid.UUID(rid)).status = "failed"
            session.get(Job, uuid.UUID(queued["job_id"])).state = "failed"
        path = f"/api/v1/receipts/{rid}/retry"
        key = str(uuid.uuid4())
        result = client.post(path, headers=headers(token, key), json={"expected_revision": 1})
        assert result.status_code == 202, result.json()
        assert result.json()["job_id"] != queued["job_id"]
        assert client.post(path, headers=headers(token, key), json={"expected_revision": 1}).json() == result.json()
        assert run_once(client.app.state.store)
        assert client.get(f"/api/v1/jobs/{result.json()['job_id']}", headers=headers(token)).json()["state"] == "succeeded"
        with client.app.state.store.Session.begin() as session:
            receipt = session.get(Receipt, uuid.UUID(rid))
            receipt.status = "failed"
            session.get(Document, receipt.document_id).expires_at = now() - timedelta(seconds=1)
        expired = client.post(path, headers=headers(token, str(uuid.uuid4())), json={"expected_revision": 1})
        assert expired.status_code == 410 and expired.json()["error"]["code"] == "SOURCE_EXPIRED"


def test_evidence_follows_stable_line_id_after_reorder():
    first = {"line_id": str(uuid.uuid4()), "charge_amount": "200.00"}
    second = {"line_id": str(uuid.uuid4()), "charge_amount": "50.00"}
    old = {"services": [first, second]}
    new = {"services": [dict(second, charge_amount="60.00"), first]}
    extracted = {"path": "/services/0/charge_amount", "source": "pdf_text",
                 "page_number": 1, "bbox": None, "source_text": "200.00",
                 "needs_review": False, "reason": None}
    evidence = rebase_evidence(old, new, [extracted])
    assert next(item for item in evidence if item["path"] == "/services/1/charge_amount")["source"] == "pdf_text"
    assert next(item for item in evidence if item["path"] == "/services/0/charge_amount")["source"] == "manual"


def test_outer_engine_budget_kills_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = time.monotonic()
    with pytest.raises(EngineError) as error:
        communicate_bounded(child, b"", 0.2, lambda: True)
    assert error.value.code == "OCR_TIMEOUT"
    assert child.poll() is not None
    assert time.monotonic() - started < 2
