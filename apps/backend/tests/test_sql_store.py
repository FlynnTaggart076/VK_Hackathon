from __future__ import annotations

import uuid
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import IdempotencyKey
from app.main import Settings, create_app
from app.jobs.worker import run_once
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
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("set TEST_POSTGRES_URL for isolated local PostgreSQL")
    assert database_url.startswith("postgresql+psycopg://zhkh@127.0.0.1:")
    assert database_url.endswith("/zhkh_e1_test")
    migrate(database_url, monkeypatch)
    settings = Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                        engine_mode="stub", database_url=database_url, storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        token = login(client, "reviewer_a")["access_token"]
        accept_privacy(client, token)
        key = str(uuid.uuid4())
        queued = upload(client, token, key).json()
    with TestClient(create_app(settings)) as restarted:
        token = login(restarted, "reviewer_a")["access_token"]
        assert restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(token)).status_code == 200
        assert run_once(restarted.app.state.store)
        after = restarted.get(f"/api/v1/receipts/{queued['receipt']['id']}", headers=headers(token)).json()
        assert after["extraction_outcome"] == "manual_required"
        assert after["bill_data"]["services"] == []
        assert restarted.get("/health/ready").status_code == 200
        with restarted.app.state.store.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT pg_typeof(bill_data)::text FROM receipt_revisions LIMIT 1").scalar_one() == "jsonb"
        with restarted.app.state.store.Session.begin() as session:
            row = session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == uuid.UUID(key)))
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        repeated_after_expiry = upload(restarted, token, key).json()
        assert repeated_after_expiry["receipt"]["id"] != queued["receipt"]["id"]


def test_non_dev_modes_rejected_before_start(tmp_path):
    for mode in ("demo", "production"):
        settings = Settings(mode=mode, database_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}",
                            engine_mode="real", storage_path=tmp_path / "private")
        with pytest.raises(ValueError, match="dev mode only"):
            create_app(settings)
