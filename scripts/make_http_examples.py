"""Regenerate synthetic HTTP examples from the accepted engine fixture.

Run from the repository root: python scripts/make_http_examples.py
No network, secrets, or runtime imports are needed.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts/http/examples"
ENGINE_FIXTURE = ROOT / "fixtures/receipts/water-2026-08.json"
T0 = "2026-09-27T10:00:00Z"
T1 = "2026-09-27T10:05:00Z"
RID = "10000000-0000-4000-8000-000000000001"
RID2 = "10000000-0000-4000-8000-000000000002"
JID = "30000000-0000-4000-8000-000000000001"
AID = "40000000-0000-4000-8000-000000000001"
DID = "50000000-0000-4000-8000-000000000001"
REQID = "b1399c8c-d010-4e0c-b75f-bd312a647fea"


def write(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def error(name: str, code: str, message: str, retryable: bool = False, **details: object) -> None:
    write(name, {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "fields": [],
            "details": details,
        },
        "request_id": REQID,
    })


def main() -> None:
    bill = json.loads(ENGINE_FIXTURE.read_text(encoding="utf-8"))
    write("meta-dev", {
        "api_version": "1.0", "engine_version": None, "knowledge_version": None,
        "mode": "dev", "limits": {"upload_max_bytes": 10485760, "pdf_max_pages": 3,
                                "receipt_retention_days": 30, "source_retention_days": 7},
        "features": {"voice": False, "external_submission": False, "receipt_ocr": False,
                     "comparison": False, "engine_stub": True, "demo_auth": False},
        "privacy_notice": {"version": "1.0", "text": "Учебный стенд: исходники хранятся 7 дней, данные квитанций — 30 дней."},
    })
    profile = {"role": "tenant", "territory_id": "demo-territory", "onboarding_completed": True,
               "privacy_notice_version": "1.0", "privacy_acknowledged_at": T0}
    write("me", {"user": {"id": "60000000-0000-4000-8000-000000000001"}, "profile": profile})
    write("catalog", {"territories": [{"id": "demo-territory", "label": "Учебная территория"}],
                      "organizations": [{"id": "demo-provider", "label": "Учебная управляющая организация", "is_synthetic": True}],
                      "topics": [{"id": "payment-change", "label": "Изменение суммы"}],
                      "service_codes": ["cold_water"], "units": ["m3"],
                      "document_kinds": [{"id": "bill", "label": "Квитанция", "territory_id": "demo-territory"}],
                      "demo_receipts": [{"fixture_id": "water-2026-08", "label": "Вода, август",
                                         "description": "Синтетическая квитанция"}]})
    receipt = {
        "id": RID, "status": "confirmed", "revision": 3, "created_at": T0, "updated_at": T1,
        "dataset_kind": "synthetic", "extraction_outcome": "recognized", "bill_data": bill,
        "field_evidence": [], "issues": [],
        "document": {"available": True, "mime_type": "application/pdf", "page_count": 1,
                     "expires_at": "2026-10-04T10:00:00Z"},
        "job": {"id": JID, "state": "succeeded", "stage": None},
        "confirmed_at": T1, "engine_version": "1.0.0-e0",
    }
    write("receipt-confirmed", receipt)
    empty_bill = {"schema_version": "1.0", "period": None, "currency": "RUB", "issuer_name": None,
                  "provider_id": None, "account_number": None, "address_text": None,
                  "template_id": None, "template_version": None, "services": [], "adjustments": [],
                  "settlement": {"formula_kind": "unsupported", "opening_balance": None,
                                 "payments_credited": None, "penalties": None, "other_account_changes": None,
                                 "document_closing_balance": None},
                  "document_current_charges": None, "document_total_due": None}
    queued = {**receipt, "status": "queued", "revision": 1, "updated_at": T0,
              "extraction_outcome": None, "bill_data": empty_bill,
              "job": {"id": JID, "state": "queued", "stage": None},
              "confirmed_at": None, "engine_version": None}
    write("receipt-queued", {"receipt": queued, "job_id": JID})
    write("receipt-manual-required", {
        **queued, "status": "needs_review", "extraction_outcome": "manual_required",
        "job": {"id": JID, "state": "succeeded", "stage": None},
        "issues": [{"code": "UNKNOWN_TEMPLATE", "severity": "warning", "path": None,
                    "message": "Макет неизвестен; проверьте и заполните поля вручную."}],
        "engine_version": "1.0.0-e0",
    })
    write("receipt-list", {"items": [{"id": RID, "status": "confirmed", "revision": 3,
                                      "period": "2026-08", "issuer_name": bill["issuer_name"],
                                      "document_total_due": "200.00", "dataset_kind": "synthetic",
                                      "created_at": T0, "source_available": True}], "next_cursor": None})
    write("job-queued", {"id": JID, "kind": "receipt_ocr", "state": "queued", "stage": None,
                         "receipt_id": RID, "error": None, "updated_at": T0})
    write("answer-unsupported", {
        "id": AID, "created_at": T0, "stale": False, "stale_reasons": [], "dataset_kind": "public_reference",
        "status": "unsupported", "text": "По этой теме пока нет проверенного ответа.", "topic_id": None,
        "steps": [], "sources": [], "actions": [], "clarification": None,
        "limitations": ["Проверьте вопрос в официальном канале вашей организации."],
        "knowledge_version": "demo-v1", "receipt_ref": None,
    })
    write("answer-clarification", {
        "id": AID, "created_at": T0, "stale": False, "stale_reasons": [],
        "dataset_kind": "public_reference", "status": "needs_clarification",
        "text": "Уточните, какая строка квитанции вас интересует.", "topic_id": None,
        "steps": [], "sources": [], "actions": [],
        "clarification": {"field": "service_code", "prompt": "Выберите услугу",
                          "options": [{"value": "cold_water", "label": "Холодная вода"}]},
        "limitations": [], "knowledge_version": "demo-v1", "receipt_ref": None,
    })
    comparison = {
        "status": "needs_identity_confirmation", "dataset_kind": "synthetic",
        "older": {"id": RID, "revision": 3, "period": "2026-08"},
        "newer": {"id": RID2, "revision": 3, "period": "2026-09"},
        "engine_version": "1.0.0-e0", "knowledge_version": "demo-v1",
        "delta_current_charges": None, "delta_adjustments": None, "delta_total_due": None,
        "lines": [], "settlement_deltas": [], "unexplained_delta": None, "issues": [], "actions": [],
    }
    write("comparison-identity", comparison)
    write("comparison-partial", {
        **comparison, "status": "partial",
        "issues": [{"code": "AMOUNT_INCOMPLETE", "severity": "warning", "path": None,
                    "message": "Одна из сумм не указана; изменение не рассчитано."}],
    })
    write("explanation-incomplete", {
        "receipt_ref": {"id": RID, "revision": 3}, "engine_version": "1.0.0-e0",
        "knowledge_version": "demo-v1", "summary": "Проверьте строки квитанции.",
        "current_charges": "200.00", "document_total_due": "200.00",
        "calculated_closing_balance": None, "calculated_total_due": None,
        "unexplained_difference": None, "reconciliation_checks": [],
        "reconciliation_status": "incomplete", "lines": [], "balance_components": [],
        "issues": [], "sources": [], "actions": [],
    })
    write("draft", {"id": DID, "revision": 1, "text": "Прошу разъяснить начисление за воду.",
                    "recipient": None, "actions": [], "receipt_refs": [{"id": RID, "revision": 3}],
                    "stale": False, "knowledge_version": "demo-v1", "created_at": T0, "updated_at": T0})
    error("error-401", "AUTH_REQUIRED", "Войдите в приложение.")
    error("error-409", "REVISION_CONFLICT", "Документ изменён. Загрузите актуальную версию.",
          current_revision=4)
    error("error-413", "FILE_TOO_LARGE", "Файл превышает лимит загрузки.")
    error("error-422", "WARNINGS_NOT_ACKNOWLEDGED", "Подтвердите предупреждения перед сохранением.")
    error("error-429", "QUEUE_LIMIT_REACHED", "Очередь занята, повторите позже.", True)
    error("error-503", "ENGINE_UNAVAILABLE", "Обработка временно недоступна.", True)
    error("error-415", "UNSUPPORTED_MEDIA_TYPE", "Поддерживаются PDF, JPEG и PNG.")
    error("error-410", "SOURCE_EXPIRED", "Срок хранения исходника истёк.")
    error("error-409-incomparable", "INCOMPARABLE_RECEIPTS", "Квитанции относятся к разным счетам.",
          reasons=["account_number_mismatch"])
    error("error-409-preview", "PREVIEW_NOT_READY", "Страница ещё создаётся.", True)


if __name__ == "__main__":
    main()
