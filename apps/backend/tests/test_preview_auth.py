"""Preview sessions are explicit, isolated, and cannot activate MAX."""

from __future__ import annotations

import uuid
import os
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.db.models import Base, Profile, User
from app.db.store import SqlStore, now
from app.errors import ApiError
from app.jobs.worker import run_once
from app.jobs.retention import run_retention_once
from app.main import Settings, create_app
from test_sql_store import migrate


POSTGRES_URL = "postgresql+psycopg://fixture:fixture@127.0.0.1/fixture"


def test_preview_requires_both_mode_and_opt_in_and_no_max(tmp_path):
    common = dict(database_url=POSTGRES_URL, engine_mode="real", storage_path=tmp_path / "private")
    Settings(mode="preview", preview_auth_enabled=True, **common).validate()
    with pytest.raises(ValueError, match="Preview auth requires"):
        Settings(mode="preview", **common).validate()
    with pytest.raises(ValueError, match="Preview auth requires"):
        Settings(mode="production", preview_auth_enabled=True, max_bot_token="fake",
                 max_webhook_secret="fake_secret", max_web_app="fixture_bot", **common).validate()
    with pytest.raises(ValueError, match="forbids demo auth and MAX credentials"):
        Settings(mode="preview", preview_auth_enabled=True, max_bot_token="stray", **common).validate()
    with pytest.raises(ValueError, match="forbids demo auth and MAX credentials"):
        Settings(mode="preview", preview_auth_enabled=True, demo_auth_enabled=True,
                 demo_access_code="stray", **common).validate()
    with pytest.raises(ValueError, match="PostgreSQL psycopg URL"):
        Settings(mode="preview", preview_auth_enabled=True,
                 database_url=f"sqlite:///{(tmp_path / 'private.sqlite').as_posix()}",
                 engine_mode="real", storage_path=tmp_path / "private").validate()


def test_preview_route_is_disabled_in_dev_and_production(tmp_path):
    with TestClient(create_app(Settings(mode="dev", storage_path=tmp_path / "dev"))) as client:
        denied = client.post("/api/v1/auth/preview")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PREVIEW_DISABLED"
    production = Settings(mode="production", database_url=POSTGRES_URL, engine_mode="real",
                          max_bot_token="fixture", max_webhook_secret="fixture_secret",
                          max_web_app="fixture_bot", storage_path=tmp_path / "production")
    with TestClient(create_app(production)) as client:
        denied = client.post("/api/v1/auth/preview")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PREVIEW_DISABLED"


def test_preview_guest_owners_and_profiles_are_distinct(tmp_path):
    # Exercise real SQL transactions without a local PostgreSQL daemon. App-level
    # validation above and CI HTTP smoke cover the PostgreSQL-only runtime rule.
    sqlite_url = f"sqlite:///{(tmp_path / 'guests.sqlite').as_posix()}"
    settings = Settings(mode="preview", preview_auth_enabled=True, database_url=sqlite_url,
                        engine_mode="real", storage_path=tmp_path / "private")
    store = SqlStore(settings)
    Base.metadata.create_all(store.engine)
    first = store.authenticate_preview()
    second = store.authenticate_preview()
    assert first["user"]["id"] != second["user"]["id"]
    assert first["access_token"] != second["access_token"]
    with store.Session() as session:
        identities = session.scalars(select(User.demo_identity).order_by(User.id)).all()
        assert len(identities) == 2
        assert all(identity.startswith("preview-") and len(identity) <= 64 for identity in identities)
        assert identities[0] != identities[1]
    assert store.user_for_token(first["access_token"]) == first["user"]["id"]
    assert store.user_for_token(second["access_token"]) == second["user"]["id"]
    store.update_profile(first["user"]["id"], {
        "role": "tenant", "territory_id": "demo-territory",
        "privacy_notice_version": "1.0", "privacy_acknowledged": True,
    })
    assert store.profile(first["user"]["id"])["onboarding_completed"] is True
    assert store.profile(second["user"]["id"])["onboarding_completed"] is False
    with pytest.raises(ApiError) as denied:
        store.authenticate_demo("reviewer_a", "anything")
    assert denied.value.status == 403


def test_preview_http_contract_and_disabled_paths(tmp_path, monkeypatch):
    from app.db import store as store_module

    sqlite_url = f"sqlite:///{(tmp_path / 'http.sqlite').as_posix()}"
    backing = SqlStore(Settings(mode="preview", preview_auth_enabled=True,
                                database_url=sqlite_url, engine_mode="real",
                                storage_path=tmp_path / "private"))
    Base.metadata.create_all(backing.engine)
    monkeypatch.setattr(store_module, "SqlStore", lambda _settings: backing)
    settings = Settings(mode="preview", preview_auth_enabled=True, database_url=POSTGRES_URL,
                        engine_mode="real", storage_path=tmp_path / "private")
    with TestClient(create_app(settings)) as client:
        meta = client.get("/api/v1/meta").json()
        assert meta["mode"] == "preview"
        assert meta["features"]["external_submission"] is False
        first = client.post("/api/v1/auth/preview")
        second = client.post("/api/v1/auth/preview", json={})
        assert first.status_code == second.status_code == 200
        assert first.json()["user"]["id"] != second.json()["user"]["id"]
        assert client.post("/api/v1/auth/preview", json={"identity": "reviewer_a"}).status_code == 422
        token = first.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}
        denied = client.post("/api/v1/receipts", headers=headers,
                             files={"file": ("private.pdf", b"not-saved", "application/pdf")})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PREVIEW_SYNTHETIC_ONLY"
        assert client.post("/api/v1/auth/max", json={"init_data": "fixture"}).status_code == 403
        assert client.post("/integrations/max/webhook", json={}).status_code == 403
        assert client.post("/api/v1/auth/demo", json={"identity": "reviewer_a",
                                                       "access_code": "fixture"}).status_code == 403


def test_preview_guest_obeys_migrated_postgresql_constraint_and_retention(tmp_path, monkeypatch):
    """CI sets TEST_PREVIEW_POSTGRES_URL to the disposable PG17 Compose database."""
    base_url = os.environ.get("TEST_PREVIEW_POSTGRES_URL")
    if not base_url:
        pytest.skip("set TEST_PREVIEW_POSTGRES_URL for isolated PostgreSQL 17 CI")
    assert base_url.startswith("postgresql+psycopg://") and "?" not in base_url
    schema = f"preview_pg_{uuid.uuid4().hex}"
    admin = create_engine(base_url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    admin.dispose()
    database_url = f"{base_url}?{urlencode({'options': f'-csearch_path={schema}'})}"
    migrate(database_url, monkeypatch)
    settings = Settings(mode="preview", preview_auth_enabled=True, database_url=database_url,
                        engine_mode="real", storage_path=tmp_path / "private")
    settings.validate()
    store = SqlStore(settings)
    with store.engine.connect() as connection:
        assert connection.execute(text("""
            SELECT count(*) FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.conname = 'ck_users_one_identity' AND n.nspname = :schema
        """), {"schema": schema}).scalar_one() == 1
    first = store.authenticate_preview()
    second = store.authenticate_preview()
    assert first["user"]["id"] != second["user"]["id"]
    with store.Session.begin() as session:
        guests = session.scalars(select(User).order_by(User.id)).all()
        assert len(guests) == 2
        assert all(user.max_user_id is None and user.demo_identity.startswith("preview-") for user in guests)
        assert guests[0].demo_identity != guests[1].demo_identity
        stale_id = guests[0].id
        guests[0].created_at = now() - timedelta(days=32)
        reviewer = User(id=uuid.uuid4(), demo_identity="reviewer_a",
                        created_at=now() - timedelta(days=32))
        session.add(reviewer)
    run_retention_once(store)
    with store.Session() as session:
        assert session.get(User, stale_id) is None
        assert session.get(User, reviewer.id) is not None
        assert session.get(User, guests[1].id) is not None


@pytest.mark.parametrize("mode", ["preview", "production"])
def test_real_worker_finishes_synthetic_import_outside_dev(tmp_path, mode):
    # Worker transaction regression. SQLite is used only for this unit test;
    # CI's HTTP smoke exercises the same path on migrated PostgreSQL 17.
    sqlite_url = f"sqlite:///{(tmp_path / f'{mode}.sqlite').as_posix()}"
    settings = Settings(mode=mode, preview_auth_enabled=mode == "preview",
                        database_url=sqlite_url, engine_mode="real",
                        storage_path=tmp_path / "private")
    store = SqlStore(settings)
    Base.metadata.create_all(store.engine)
    if mode == "preview":
        user_id = store.authenticate_preview()["user"]["id"]
    else:
        user_id = str(uuid.uuid4())
        with store.Session.begin() as session:
            session.add(User(id=uuid.UUID(user_id), max_user_id=123456, created_at=now()))
            session.flush()
            session.add(Profile(user_id=uuid.UUID(user_id), role="other", territory_id=None,
                                onboarding_completed=False, privacy_notice_version=None,
                                privacy_acknowledged_at=None))
    store.update_profile(user_id, {
        "role": "tenant", "territory_id": "demo-territory",
        "privacy_notice_version": "1.0", "privacy_acknowledged": True,
    })
    queued = store.import_demo(user_id, str(uuid.uuid4()), "water-2026-08")
    assert run_once(store) is True
    receipt = store.receipt(user_id, queued["receipt"]["id"])
    assert receipt["status"] == "needs_review"
    assert receipt["extraction_outcome"] == "recognized"
    assert receipt["dataset_kind"] == "synthetic"
    assert receipt["engine_version"] == "synthetic-demo-v1"
    assert receipt["bill_data"]["document_current_charges"] == "200.00"
    assert receipt["job"]["state"] == "succeeded"
