from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from app.main import Settings, create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(mode="dev", demo_auth_enabled=True, demo_access_code="test-secret",
                              engine_mode="stub", storage_path=tmp_path / "private"))
    with TestClient(app) as value:
        yield value


def login(client, identity):
    result = client.post("/api/v1/auth/demo", json={"identity": identity, "access_code": "test-secret"})
    assert result.status_code == 200
    return result.json()


def headers(token, key=None):
    value = {"Authorization": f"Bearer {token}"}
    if key:
        value["Idempotency-Key"] = key
    return value


def image_bytes(color="white") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(stream, format="PNG")
    return stream.getvalue()


def accept_privacy(client, token):
    response = client.put("/api/v1/me/profile", headers=headers(token), json={
        "role": "tenant", "territory_id": "demo-territory",
        "privacy_notice_version": client.get("/api/v1/meta").json()["privacy_notice"]["version"],
        "privacy_acknowledged": True,
    })
    assert response.status_code == 200


def upload(client, token, key, data=None, mime="image/png"):
    return client.post("/api/v1/receipts", headers=headers(token, key),
                       files={"file": ("receipt.png", data if data is not None else image_bytes(), mime)})


def test_meta_and_demo_auth_guard(client):
    meta = client.get("/api/v1/meta")
    assert meta.status_code == 200
    assert meta.headers["X-Request-ID"]
    assert meta.json()["features"] == {
        "voice": False, "external_submission": False, "receipt_ocr": False,
        "comparison": False, "engine_stub": True, "demo_auth": True,
    }
    assert client.get("/api/v1/me").json()["error"]["code"] == "AUTH_REQUIRED"
    denied = client.post("/api/v1/auth/demo", json={"identity": "reviewer_a", "access_code": "wrong"})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "AUTH_REQUIRED"


def test_two_users_upload_idempotency_and_isolation(client):
    a = login(client, "reviewer_a")
    b = login(client, "reviewer_b")
    assert a["user"]["id"] != b["user"]["id"]
    assert client.get("/api/v1/me", headers=headers(a["access_token"])).json()["user"] == a["user"]
    key = str(uuid.uuid4())
    before_privacy = upload(client, a["access_token"], key)
    assert before_privacy.status_code == 422
    assert before_privacy.json()["error"]["code"] == "PRIVACY_NOTICE_REQUIRED"
    accept_privacy(client, a["access_token"])
    created = upload(client, a["access_token"], key)
    assert created.status_code == 202
    body = created.json()
    assert body["receipt"]["status"] == "queued"
    assert body["receipt"]["dataset_kind"] == "user_provided"
    assert body["receipt"]["extraction_outcome"] is None
    assert upload(client, a["access_token"], key).json() == body
    assert len(list(client.app.state.store.settings.storage_path.iterdir())) == 1
    conflict = upload(client, a["access_token"], key, data=image_bytes("black"))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    job_id = body["job_id"]
    receipt_id = body["receipt"]["id"]
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers(a["access_token"])).json()["state"] == "queued"
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers(b["access_token"])).status_code == 404
    assert client.get(f"/api/v1/receipts/{receipt_id}", headers=headers(b["access_token"])).status_code == 404


def test_upload_limits_and_mime(client):
    token = login(client, "reviewer_a")["access_token"]
    accept_privacy(client, token)
    too_large = upload(client, token, str(uuid.uuid4()), data=image_bytes() + b"x" * 10_485_760)
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"
    wrong_mime = upload(client, token, str(uuid.uuid4()), mime="application/pdf")
    assert wrong_mime.status_code == 415
    writer = PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=72, height=72)
    stream = io.BytesIO()
    writer.write(stream)
    pages = upload(client, token, str(uuid.uuid4()), data=stream.getvalue(), mime="application/pdf")
    assert pages.status_code == 413
    assert pages.json()["error"]["code"] == "PAGE_LIMIT_EXCEEDED"


def test_production_disables_stubs_and_demo(tmp_path):
    with pytest.raises(ValueError, match="Production forbids"):
        create_app(Settings(mode="production", demo_auth_enabled=True, demo_access_code="secret",
                            engine_mode="stub", database_url="postgresql+psycopg://x:y@db/z",
                            storage_path=tmp_path))
