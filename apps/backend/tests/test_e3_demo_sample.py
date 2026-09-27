"""Only explicit manifest-bound bytes get synthetic provenance through upload."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import Settings, create_app


ROOT = Path(__file__).resolve().parents[3]


def test_demo_sample_requires_exact_bytes_and_keeps_real_job(tmp_path):
    settings = Settings(mode="dev", engine_mode="real", demo_auth_enabled=True,
                        demo_access_code="fixture-code", storage_path=tmp_path / "private")
    app = create_app(settings)
    sample = (ROOT / "fixtures" / "receipts" / "demo-bill-2026-08.pdf").read_bytes()
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/demo", json={"identity": "reviewer_a",
                                                      "access_code": "fixture-code"}).json()
        token = login["access_token"]
        headers = {"Authorization": "Bearer " + token}
        meta = client.get("/api/v1/meta").json()
        client.put("/api/v1/me/profile", headers=headers, json={
            "role": "tenant", "territory_id": "demo-territory",
            "privacy_notice_version": meta["privacy_notice"]["version"],
            "privacy_acknowledged": True,
        })
        route = "/api/v1/receipts"
        def upload(content, marker):
            return client.post(route, headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                               files={"file": ("arbitrary.pdf", content, "application/pdf")},
                               data={"demo_sample_id": marker} if marker else {})
        rejected = upload(sample, "demo-bill-2026-09.pdf")
        assert rejected.status_code == 422
        assert upload(sample, "unknown.pdf").status_code == 422
        marked = upload(sample, "demo-bill-2026-08.pdf")
        assert marked.status_code == 202, marked.text
        assert marked.json()["receipt"]["dataset_kind"] == "synthetic"
        assert marked.json()["receipt"]["job"]["state"] == "queued"
        assert app.state.store.jobs[marked.json()["job_id"]]["kind"] == "receipt_ocr"
        ordinary = upload(sample, None)
        assert ordinary.status_code == 202
        assert ordinary.json()["receipt"]["dataset_kind"] == "user_provided"
