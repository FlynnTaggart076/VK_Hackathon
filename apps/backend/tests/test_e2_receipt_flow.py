"""A real bytes-to-engine flow across persisted receipt revisions."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.main import Settings, create_app
from app.jobs.worker import run_once
from test_contract_responses import validate_response
from test_dev_api import accept_privacy, headers, login, upload
from test_sql_store import migrate


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
        assert client.put(edit_url, headers=headers(owner), json={"expected_revision": 3, "bill_data": data}).status_code == 409
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
