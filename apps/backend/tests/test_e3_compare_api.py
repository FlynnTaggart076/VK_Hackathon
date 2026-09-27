"""HTTP comparison uses C arithmetic only after owner/current-confirmed gates."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db.models import Base, Receipt, ReceiptRevision
from app.main import Settings, create_app


ROOT = Path(__file__).resolve().parents[3]
IDS = ("10000000-0000-4000-8000-000000000001", "10000000-0000-4000-8000-000000000002")


def fixture(period: str) -> dict:
    return json.loads((ROOT / "fixtures" / "receipts" / f"water-{period}.json").read_text(encoding="utf-8"))


def test_compare_http_200_to_270_owner_and_stale(tmp_path):
    url = f"sqlite:///{(tmp_path / 'compare.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    app = create_app(Settings(database_url=url, storage_path=tmp_path / "private",
                              engine_mode="real", demo_auth_enabled=True, demo_access_code="fixture-code"))
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/demo", json={"identity": "reviewer_a", "access_code": "fixture-code"}).json()
        other = client.post("/api/v1/auth/demo", json={"identity": "reviewer_b", "access_code": "fixture-code"}).json()
        headers = {"Authorization": "Bearer " + token["access_token"]}
        other_headers = {"Authorization": "Bearer " + other["access_token"]}
        with app.state.store.Session.begin() as session:
            for receipt_id, period in zip(IDS, ("2026-08", "2026-09")):
                rid = uuid.UUID(receipt_id)
                session.add(Receipt(id=rid, user_id=uuid.UUID(token["user"]["id"]), document_id=None,
                                    status="confirmed", current_revision=3, dataset_kind="synthetic",
                                    extraction_outcome="recognized", created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc)))
                session.add(ReceiptRevision(receipt_id=rid, revision=3, bill_data=fixture(period),
                                            extraction_meta={"field_evidence": [], "issues": []},
                                            validation={"can_confirm": True},
                                            confirmed_at=datetime.now(timezone.utc), engine_version="0.1.0"))
        request = {"left": {"id": IDS[1], "revision": 3},
                   "right": {"id": IDS[0], "revision": 3}, "identity_acknowledged": False}
        response = client.post("/api/v1/comparisons", json=request, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "complete" and data["dataset_kind"] == "synthetic"
        assert data["older"]["period"] == "2026-08" and data["newer"]["period"] == "2026-09"
        assert data["delta_current_charges"] == data["delta_total_due"] == "70.00"
        assert (data["lines"][0]["quantity_effect"], data["lines"][0]["tariff_effect"]) == ("40.00", "30.00")
        with app.state.store.Session.begin() as session:
            session.get(Receipt, uuid.UUID(IDS[1])).dataset_kind = "user_provided"
        mixed = client.post("/api/v1/comparisons", json=request, headers=headers)
        assert mixed.status_code == 200 and mixed.json()["dataset_kind"] == "synthetic"
        assert client.post("/api/v1/comparisons", json=request, headers=other_headers).status_code == 404
        with app.state.store.Session.begin() as session:
            revision = session.get(ReceiptRevision, (uuid.UUID(IDS[1]), 3))
            missing_identity = dict(revision.bill_data)
            missing_identity["account_number"] = None
            revision.bill_data = missing_identity
        identity = client.post("/api/v1/comparisons", json=request, headers=headers)
        assert identity.status_code == 200, identity.text
        assert identity.json()["status"] == "needs_identity_confirmation"
        assert identity.json()["delta_total_due"] is None
        assert identity.json()["lines"] == identity.json()["settlement_deltas"] == []
        request["identity_acknowledged"] = True
        acknowledged = client.post("/api/v1/comparisons", json=request, headers=headers)
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["delta_total_due"] == "70.00"
        with app.state.store.Session.begin() as session:
            row = session.get(Receipt, uuid.UUID(IDS[1]))
            row.current_revision = 4
            row.status = "needs_review"
        stale = client.post("/api/v1/comparisons", json=request, headers=headers)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_CONFLICT"
