"""Preview sessions are explicit, isolated, and cannot activate MAX."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Base
from app.db.store import SqlStore
from app.errors import ApiError
from app.main import Settings, create_app


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
