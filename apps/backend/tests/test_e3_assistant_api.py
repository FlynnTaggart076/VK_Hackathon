"""Persisted C FAQ/draft flow, owner isolation and revision stale behavior."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db.models import Base, Receipt, ReceiptRevision
from app.main import Settings, create_app
from test_contract_responses import validate_response


ROOT = Path(__file__).resolve().parents[3]
RID = "10000000-0000-4000-8000-000000000001"


def test_answer_draft_owner_stale_delete(tmp_path):
    url = f"sqlite:///{(tmp_path / 'assistant.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    app = create_app(Settings(database_url=url, storage_path=tmp_path / "private",
                              engine_mode="real", demo_auth_enabled=True,
                              demo_access_code="fixture-code"))
    with TestClient(app) as client:
        def login(identity):
            return client.post("/api/v1/auth/demo", json={
                "identity": identity, "access_code": "fixture-code",
            }).json()
        a, b = login("reviewer_a"), login("reviewer_b")
        auth = {"Authorization": "Bearer " + a["access_token"]}
        other = {"Authorization": "Bearer " + b["access_token"]}
        meta = client.get("/api/v1/meta").json()
        profile = {"role": "owner", "territory_id": "demo-territory",
                   "privacy_notice_version": meta["privacy_notice"]["version"],
                   "privacy_acknowledged": True}
        assert client.put("/api/v1/me/profile", headers=auth, json=profile).status_code == 200
        bill = json.loads((ROOT / "fixtures" / "receipts" / "water-2026-08.json").read_text(encoding="utf-8"))
        with app.state.store.Session.begin() as session:
            session.add(Receipt(id=uuid.UUID(RID), user_id=uuid.UUID(a["user"]["id"]),
                                status="confirmed", current_revision=3, dataset_kind="synthetic",
                                extraction_outcome="recognized", created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc)))
            session.add(ReceiptRevision(receipt_id=uuid.UUID(RID), revision=3, bill_data=bill,
                                        extraction_meta={"field_evidence": [], "issues": []},
                                        validation={"can_confirm": True}, confirmed_at=datetime.now(timezone.utc),
                                        engine_version="0.1.0"))
        context = {"territory_id": "demo-territory", "role": "owner", "topic_id": "bill_change",
                   "organization_id": None, "service_code": None, "document_kind": None,
                   "receipt_id": RID, "receipt_revision": 3}
        answer = client.post("/api/v1/assistant/answers", headers=auth,
                             json={"question": "Почему выросла сумма?", "context": context})
        assert answer.status_code == 200, answer.text
        assert answer.json()["status"] == "answered"
        validate_response("AnswerView", answer.json())
        assert answer.json()["dataset_kind"] == "synthetic" and not answer.json()["stale"]
        answer_id = answer.json()["id"]
        assert client.get(f"/api/v1/assistant/answers/{answer_id}", headers=other).status_code == 404
        question = client.post("/api/v1/assistant/answers", headers=auth, json={
            "question": "xyzzy неизвестное", "context": {**context, "topic_id": None, "receipt_id": None,
                                                     "receipt_revision": None},
        })
        assert question.status_code == 200 and question.json()["status"] == "unsupported"
        draft_body = {"topic_id": "request_breakdown", "organization_id": None,
                      "receipt_refs": [{"id": RID, "revision": 3}],
                      "line_id": bill["services"][0]["line_id"], "user_question": "Поясните сумму"}
        key = str(uuid.uuid4())
        draft = client.post("/api/v1/drafts", headers={**auth, "Idempotency-Key": key},
                            json=draft_body)
        assert draft.status_code == 201, draft.text
        validate_response("DraftView", draft.json())
        assert "200.00" in draft.json()["text"] and draft.json()["recipient"] is None
        draft_id = draft.json()["id"]
        assert client.post("/api/v1/drafts", headers={**auth, "Idempotency-Key": key},
                           json=draft_body).json() == draft.json()
        assert client.get(f"/api/v1/drafts/{draft_id}", headers=other).status_code == 404
        edited = client.put(f"/api/v1/drafts/{draft_id}", headers=auth,
                            json={"expected_revision": 1, "text": "Мой исправленный текст"})
        assert edited.status_code == 200 and edited.json()["revision"] == 2
        assert client.put(f"/api/v1/drafts/{draft_id}", headers=auth,
                          json={"expected_revision": 1, "text": "Повтор"}).status_code == 409
        with app.state.store.Session.begin() as session:
            row = session.get(Receipt, uuid.UUID(RID))
            row.current_revision = 4
            row.status = "needs_review"
        stale_answer = client.get(f"/api/v1/assistant/answers/{answer_id}", headers=auth)
        assert stale_answer.status_code == 200 and stale_answer.json()["stale_reasons"] == ["receipt_changed"]
        stale_draft = client.get(f"/api/v1/drafts/{draft_id}", headers=auth)
        assert stale_draft.status_code == 200 and stale_draft.json()["stale"]
        assert client.delete(f"/api/v1/receipts/{RID}", headers=auth).status_code == 204
        assert client.get(f"/api/v1/assistant/answers/{answer_id}", headers=auth).status_code == 404
        assert client.get(f"/api/v1/drafts/{draft_id}", headers=auth).status_code == 404
