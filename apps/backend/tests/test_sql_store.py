from __future__ import annotations

import uuid
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from urllib.parse import urlencode

from app.db.models import IdempotencyKey
from app.main import Settings, create_app
from app.jobs.worker import fixture_root, run_once
from test_contract_responses import validate_response
from test_dev_api import accept_privacy, headers, image_bytes, login, upload


def migrate(database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    command.upgrade(Config(str(alembic_ini)), "head")


def test_migration_and_persisted_ownership_after_restart(tmp_path, monkeypatch):
    database = tmp_path / "isolated-test.sqlite"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="stub", database_url=database_url, storage_path=tmp_path / "private")
    key = str(uuid.uuid4())
    with TestClient(create_app(settings)) as client:
        token = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, token)
        queued = upload(client, token, key).json()
        assert queued["receipt"]["status"] == "queued"
        assert client.get("/health/ready").status_code == 503  # no worker yet
    with TestClient(create_app(settings)) as restarted:
        a = login(restarted, "reviewer_a")
        b = login(restarted, "reviewer_b")
        a_token, b_token = a["access_token"], b["access_token"]
        assert a["user"]["id"] != b["user"]["id"]
        assert restarted.get(f"/api/v1/jobs/{queued['job_id']}", headers=headers(a_token)).json()["state"] == "queued"
        assert restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(a_token)).json()["id"] == queued["receipt"]["id"]
        assert restarted.get(f"/api/v1/jobs/{queued['job_id']}", headers=headers(b_token)).status_code == 404
        assert restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(b_token)).status_code == 404
        assert upload(restarted, a_token, key).json() == queued
        conflict = upload(restarted, a_token, key, data=image_bytes("black"))
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert run_once(restarted.app.state.store)
        after = restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(a_token)).json()
        assert after["status"] == "needs_review"
        assert after["extraction_outcome"] == "manual_required"
        assert after["bill_data"]["services"] == []
        assert after["issues"][0]["code"] == "DEV_STUB_NO_OCR"
        assert restarted.get(f"/api/v1/jobs/{queued['job_id']}", headers=headers(a_token)).json()["state"] == "succeeded"
        assert restarted.get("/health/ready").status_code == 200
        assert not run_once(restarted.app.state.store)
        demo = restarted.post("/api/v1/receipts/demo", headers=headers(a_token, str(uuid.uuid4())),
                              json={"fixture_id": "water-2026-08"})
        assert demo.status_code == 202
        assert demo.json()["receipt"]["dataset_kind"] == "synthetic"
        assert run_once(restarted.app.state.store)
        demo_receipt = restarted.get(f"/api/v1/receipts/{demo.json()['receipt']['id']}", headers=headers(a_token)).json()
        assert demo_receipt["status"] == "needs_review"
        assert demo_receipt["bill_data"]["document_current_charges"] == "200.00"
        assert demo_receipt["issues"][0]["code"] == "SYNTHETIC_DEMO"
        assert demo_receipt["job"]["id"] == demo.json()["job_id"]


def test_postgresql_migration_persistence_and_worker(tmp_path, monkeypatch):
    base_url = os.environ.get("TEST_POSTGRES_URL")
    if not base_url:
        pytest.skip("set TEST_POSTGRES_URL for isolated local PostgreSQL")
    assert base_url.startswith("postgresql+psycopg://zhkh@127.0.0.1:")
    assert base_url.endswith("/zhkh_e1_test")
    schema = f"e1_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(base_url)
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    admin_engine.dispose()
    database_url = f"{base_url}?{urlencode({'options': f'-csearch_path={schema}'})}"
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="stub", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        auth = login(client, "reviewer_a")
        validate_response("AuthResponse", auth)
        token = auth["access_token"]
        accept_privacy(client, token)
        key = str(uuid.uuid4())
        queued = upload(client, token, key).json()
        validate_response("ReceiptQueued", queued)
    with TestClient(create_app(settings)) as restarted:
        token = login(restarted, "reviewer_a")["access_token"]
        assert restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(token)).status_code == 200
        job_url = f"/api/v1/jobs/{queued['job_id']}"
        assert restarted.get(job_url, headers=headers(token)).json()["state"] == "queued"
        for _ in range(100):
            assert run_once(restarted.app.state.store), "worker had no claimable job before target finished"
            if restarted.get(job_url, headers=headers(token)).json()["state"] == "succeeded":
                break
        else:
            pytest.fail("target persisted job did not finish after draining earlier test jobs")
        after = restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(token)).json()
        validate_response("ReceiptView", after)
        validate_response("Job", restarted.get(job_url, headers=headers(token)).json())
        assert after["extraction_outcome"] == "manual_required"
        assert after["bill_data"]["services"] == []
        assert restarted.get("/health/ready").status_code == 200
        with restarted.app.state.store.engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT pg_typeof(bill_data)::text FROM receipt_revisions WHERE receipt_id = %s",
                (uuid.UUID(queued["receipt"]["id"]),)).scalar_one() == "jsonb"
        with restarted.app.state.store.Session.begin() as session:
            row = session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == uuid.UUID(key)))
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        repeated_after_expiry = upload(restarted, token, key).json()
        assert repeated_after_expiry["receipt"]["id"] != queued["receipt"]["id"]


def test_non_dev_modes_require_postgres_and_production_requires_max(tmp_path):
    sqlite_url = f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"
    with pytest.raises(ValueError, match="PostgreSQL psycopg URL"):
        create_app(Settings(mode="demo", database_url=sqlite_url, engine_mode="real",
                            storage_path=tmp_path / "private"))
    with pytest.raises(ValueError, match="MAX bot token"):
        create_app(Settings(mode="production", database_url=sqlite_url, engine_mode="real",
                            storage_path=tmp_path / "private"))
    with pytest.raises(ValueError, match="PostgreSQL psycopg URL"):
        create_app(Settings(mode="production", database_url=sqlite_url, engine_mode="real",
                            max_bot_token="synthetic-token", max_webhook_secret="synthetic_secret",
                            max_web_app="fixture_bot",
                            storage_path=tmp_path / "private"))
    with pytest.raises(ValueError, match="MAX_WEB_APP"):
        create_app(Settings(mode="production", database_url=sqlite_url, engine_mode="real",
                            max_bot_token="synthetic-token", max_webhook_secret="synthetic_secret",
                            storage_path=tmp_path / "private"))


def test_worker_finds_fixture_directory_in_container_layout(tmp_path):
    root = tmp_path / "workspace"
    fixture_dir = root / "fixtures" / "receipts"
    fixture_dir.mkdir(parents=True)
    module_file = root / "app" / "jobs" / "worker.py"
    assert fixture_root(module_file, str(fixture_dir)) == fixture_dir
    assert fixture_root(module_file, None) == fixture_dir


def test_e2_owner_source_list_delete_and_revision_cas(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'e2.sqlite').as_posix()}"
    monkeypatch.setenv("APP_MODE", "dev")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="stub", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        owner_auth = login(client, "reviewer_a")
        owner, owner_id = owner_auth["access_token"], owner_auth["user"]["id"]
        stranger = login(client, "reviewer_b")["access_token"]
        accept_privacy(client, owner)
        original = image_bytes()
        upload_key = str(uuid.uuid4())
        queued = upload(client, owner, upload_key, data=original).json()
        receipt_id = queued["receipt"]["id"]
        source_url = f"/api/v1/receipts/{receipt_id}/source"
        assert client.get(source_url, headers=headers(stranger)).status_code == 404
        response = client.get(source_url, headers=headers(owner))
        assert response.status_code == 200 and response.content == original
        assert response.headers["cache-control"] == "no-store"
        listing = client.get("/api/v1/receipts", headers=headers(owner)).json()
        validate_response("ReceiptList", listing)
        assert [entry["id"] for entry in listing["items"]] == [receipt_id]
        assert client.get("/api/v1/receipts", headers=headers(stranger)).json()["items"] == []
        assert run_once(client.app.state.store)
        store = client.app.state.store
        before = store.receipt(owner_id, receipt_id)
        edited_bill = dict(before["bill_data"], period="2026-08")
        changed = store.edit_revision(owner_id, receipt_id, 1, edited_bill, [], [],
                                      {"can_confirm": False}, "test")
        assert changed["revision"] == 2 and changed["bill_data"]["period"] == "2026-08"
        assert before["bill_data"]["period"] is None
        with pytest.raises(Exception) as stale:
            store.edit_revision(owner_id, receipt_id, 1, edited_bill, [], [], {}, "test")
        assert getattr(stale.value, "code", None) == "REVISION_CONFLICT"
        assert client.delete(f"/api/v1/receipts/{receipt_id}", headers=headers(stranger)).status_code == 204
        assert client.get(source_url, headers=headers(owner)).status_code == 200
        assert client.delete(f"/api/v1/receipts/{receipt_id}", headers=headers(owner)).status_code == 204
        assert client.delete(f"/api/v1/receipts/{receipt_id}", headers=headers(owner)).status_code == 204
        assert client.get(source_url, headers=headers(owner)).status_code == 404
        assert client.get("/api/v1/receipts", headers=headers(owner)).json()["items"] == []
        assert list(settings.storage_path.iterdir()) == []
        repeated = upload(client, owner, upload_key, data=original)
        assert repeated.status_code == 202
        assert repeated.json()["receipt"]["id"] != receipt_id
