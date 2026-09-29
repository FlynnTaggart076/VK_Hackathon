"""Extraction issues follow the lines they describe and disappear once the user fixes them."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.jobs.worker import run_once
from app.main import Settings, create_app
from app.services.revision_logic import rebase_issues
from test_dev_api import accept_privacy, headers, login, upload
from test_sql_store import migrate

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "receipts"
A, B = "10000000-0000-4000-8000-00000000000a", "10000000-0000-4000-8000-00000000000b"


def bill(*lines):
    return {"services": [dict(line_id=line[0], service_code=line[1]) for line in lines], "adjustments": []}


def issue(code, path, severity="warning"):
    return {"code": code, "severity": severity, "path": path, "message": "Проверьте."}


def test_issue_moves_with_its_line_and_is_dropped_with_it():
    old = bill((A, "other"), (B, "other"))
    new = bill((B, "other"))
    kept = rebase_issues(old, new, [issue("SERVICE_UNMAPPED", "/services/0/service_code"),
                                    issue("SERVICE_UNMAPPED", "/services/1/service_code")])
    assert [item["path"] for item in kept] == ["/services/0/service_code"]


def test_issue_disappears_when_the_user_fixes_exactly_that_value():
    old = bill((A, "other"), (B, "other"))
    new = bill((A, "cold_water"), (B, "other"))
    kept = rebase_issues(old, new, [issue("SERVICE_UNMAPPED", "/services/0/service_code"),
                                    issue("SERVICE_UNMAPPED", "/services/1/service_code")])
    assert [item["path"] for item in kept] == ["/services/1/service_code"]


def test_global_issues_stay_and_extraction_errors_are_superseded_by_a_manual_edit():
    old, new = bill((A, "other")), bill((A, "other"))
    kept = rebase_issues(old, new, [issue("OCR_REVIEW_REQUIRED", None),
                                    issue("EPD_TABLE_BOUNDS", "/services", "error"),
                                    issue("EPD_ROW_UNPARSED", "/services")])
    assert [item["code"] for item in kept] == ["OCR_REVIEW_REQUIRED", "EPD_ROW_UNPARSED"]


def test_fixing_an_unrecognised_service_removes_its_acknowledgement(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'issues.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="real", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        owner = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, owner)
        payload = (FIXTURES / "demo-bill-2026-09-unknown-service.pdf").read_bytes()
        queued = upload(client, owner, str(uuid.uuid4()), data=payload, mime="application/pdf")
        assert queued.status_code == 202
        receipt_id = queued.json()["receipt"]["id"]
        assert run_once(client.app.state.store)
        receipt = client.get(f"/api/v1/receipts/{receipt_id}", headers=headers(owner)).json()
        unmapped = [item for item in receipt["issues"] if item["code"] == "SERVICE_UNMAPPED"]
        assert unmapped and "Прочее" in unmapped[0]["message"] and "other" not in unmapped[0]["message"]
        line = receipt["bill_data"]["services"][0]
        assert line["service_code"] == "other"
        fixed = dict(receipt["bill_data"], services=[dict(line, service_code="cold_water", scope="individual", unit="m3", unit_label=None)])
        edited = client.put(f"/api/v1/receipts/{receipt_id}/draft", headers=headers(owner),
                            json={"expected_revision": 1, "bill_data": fixed})
        assert edited.status_code == 200, edited.json()
        assert "SERVICE_UNMAPPED" not in [item["code"] for item in edited.json()["issues"]]
        required = sorted({item["code"] for item in edited.json()["issues"] if item["severity"] == "warning"})
        confirmed = client.post(f"/api/v1/receipts/{receipt_id}/confirm", headers=headers(owner, str(uuid.uuid4())),
                                json={"expected_revision": 2, "acknowledged_warning_codes": required})
        assert confirmed.status_code == 200, confirmed.json()
