"""Persist engine answer/draft results with owner, revision and stale checks."""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.models import AssistantAnswer, Draft, IdempotencyKey, Profile, Receipt, ReceiptRevision
from app.db.store import SqlStore, aware, now, stamp
from app.errors import ApiError


KNOWLEDGE_ROOT = next(parent / "knowledge" for parent in Path(__file__).resolve().parents
                      if (parent / "knowledge" / "manifest.yaml").is_file())


@lru_cache(maxsize=1)
def knowledge():
    from housing_engine import load_knowledge

    return load_knowledge(str(KNOWLEDGE_ROOT), now())


def receipt_snapshots(store: SqlStore, user_id: str, refs: list[dict]) -> tuple[list[dict], dict]:
    uid = uuid.UUID(user_id)
    ids = [uuid.UUID(item["id"]) for item in refs]
    if len(set(ids)) != len(ids):
        raise ApiError(422, "VALIDATION_FAILED", "Повтор квитанции в запросе.")
    with store.Session.begin() as session:
        profile = session.get(Profile, uid)
        if profile is None:
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        rows = {row.id: row for row in session.scalars(select(Receipt).where(
            Receipt.id.in_(ids), Receipt.user_id == uid).order_by(Receipt.id).with_for_update()).all()}
        snapshots = []
        for ref, rid in zip(refs, ids):
            receipt = rows.get(rid)
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.current_revision != ref["revision"]:
                raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена.",
                               details={"current_revision": receipt.current_revision})
            if receipt.status != "confirmed":
                raise ApiError(409, "RECEIPT_NOT_CONFIRMED", "Сначала подтвердите квитанцию.")
            revision = session.get(ReceiptRevision, (rid, receipt.current_revision))
            if revision is None or revision.confirmed_at is None:
                raise ApiError(409, "RECEIPT_NOT_CONFIRMED", "Сначала подтвердите квитанцию.")
            snapshots.append({"id": rid, "revision": receipt.current_revision,
                              "bill_data": deepcopy(revision.bill_data),
                              "confirmed_at": aware(revision.confirmed_at),
                              "dataset_kind": receipt.dataset_kind})
        return snapshots, {"role": profile.role, "territory_id": profile.territory_id,
                           "privacy_notice_version": profile.privacy_notice_version}


def owner_receipt_pair(store: SqlStore, user_id: str, preferred_id: str | None = None,
                       db_session=None) -> tuple[list[dict], dict]:
    """Current and nearest earlier comparable confirmed bill; never crosses owners."""
    uid = uuid.UUID(str(user_id))

    def read(session):
        profile = session.get(Profile, uid)
        if profile is None:
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        rows = session.execute(select(Receipt, ReceiptRevision).join(
            ReceiptRevision,
            (ReceiptRevision.receipt_id == Receipt.id) &
            (ReceiptRevision.revision == Receipt.current_revision),
        ).where(Receipt.user_id == uid, Receipt.status == "confirmed",
                ReceiptRevision.confirmed_at.is_not(None))).all()
        candidates = [(receipt, revision) for receipt, revision in rows
                      if isinstance(revision.bill_data, dict)]
        if preferred_id is not None:
            candidates = [item for item in candidates if str(item[0].id) == preferred_id] + [
                item for item in candidates if str(item[0].id) != preferred_id]
            if not candidates or str(candidates[0][0].id) != preferred_id:
                raise ApiError(404, "NOT_FOUND", "Подтверждённая квитанция не найдена.")
        else:
            candidates.sort(key=lambda item: (
                item[1].bill_data.get("period") or "", aware(item[1].confirmed_at), str(item[0].id)),
                reverse=True)
        if not candidates:
            return [], {"role": profile.role, "territory_id": profile.territory_id,
                        "privacy_notice_version": profile.privacy_notice_version}
        current, current_revision = candidates[0]
        bill = current_revision.bill_data
        account, provider, period = bill.get("account_number"), bill.get("provider_id"), bill.get("period")
        earlier = []
        previous_period = None
        if isinstance(period, str) and len(period) == 7:
            year, month = map(int, period.split("-"))
            previous_period = f"{year - (month == 1):04d}-{12 if month == 1 else month - 1:02d}"
        if account and provider and previous_period:
            earlier = [(receipt, revision) for receipt, revision in candidates[1:]
                       if revision.bill_data.get("account_number") == account and
                       revision.bill_data.get("provider_id") == provider and
                       revision.bill_data.get("period") == previous_period]
            earlier.sort(key=lambda item: (
                item[1].bill_data["period"], aware(item[1].confirmed_at), str(item[0].id)), reverse=True)

        def snapshot(pair):
            receipt, revision = pair
            return {"id": receipt.id, "revision": receipt.current_revision,
                    "bill_data": deepcopy(revision.bill_data),
                    "confirmed_at": aware(revision.confirmed_at), "dataset_kind": receipt.dataset_kind}

        selected = [snapshot((current, current_revision))]
        if earlier:
            selected.append(snapshot(earlier[0]))
        return selected, {"role": profile.role, "territory_id": profile.territory_id,
                          "privacy_notice_version": profile.privacy_notice_version}

    if db_session is not None:
        return read(db_session)
    with store.Session() as session:
        return read(session)


def _current_refs(session, user_id: uuid.UUID, refs: list[dict]) -> bool:
    for ref in refs:
        row = session.scalar(select(Receipt).where(
            Receipt.id == uuid.UUID(ref["id"]), Receipt.user_id == user_id).with_for_update())
        if row is None or row.current_revision != ref["revision"] or row.status != "confirmed":
            return False
    return True


def _stale_refs(session, user_id: uuid.UUID, refs: list[dict]) -> bool:
    return not _current_refs(session, user_id, refs)


def save_answer(store: SqlStore, user_id: str, question: str, result: dict,
                ref: dict | None, dataset_kind: str) -> dict:
    uid = uuid.UUID(user_id)
    created = now()
    with store.Session.begin() as session:
        if ref and not _current_refs(session, uid, [ref]):
            raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменилась до сохранения ответа.")
        row = AssistantAnswer(id=uuid.uuid4(), user_id=uid, question=question,
                              result=deepcopy(result), receipt_id=uuid.UUID(ref["id"]) if ref else None,
                              receipt_revision=ref["revision"] if ref else None,
                              dataset_kind=dataset_kind, created_at=created,
                              expires_at=created + timedelta(days=30))
        session.add(row)
        return {"id": str(row.id), "created_at": stamp(created), "stale": False,
                "stale_reasons": [], "dataset_kind": dataset_kind, **deepcopy(result)}


def get_answer(store: SqlStore, user_id: str, answer_id: str, current_knowledge_version: str) -> dict:
    uid = uuid.UUID(user_id)
    with store.Session() as session:
        row = session.scalar(select(AssistantAnswer).where(
            AssistantAnswer.id == uuid.UUID(answer_id), AssistantAnswer.user_id == uid))
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Ответ не найден.")
        reasons = []
        ref = ({"id": str(row.receipt_id), "revision": row.receipt_revision}
               if row.receipt_id is not None else None)
        if ref and _stale_refs(session, uid, [ref]):
            reasons.append("receipt_changed")
        if any(datetime.fromisoformat(item["review_after"].replace("Z", "+00:00")) < now()
               for item in row.result.get("sources", [])):
            reasons.append("source_expired")
        if row.result["knowledge_version"] != current_knowledge_version:
            reasons.append("knowledge_updated")
        result = deepcopy(row.result)
        if reasons:
            result["actions"] = []  # A stale card must not offer old navigation or links.
        return {"id": str(row.id), "created_at": stamp(row.created_at), "stale": bool(reasons),
                "stale_reasons": reasons, "dataset_kind": row.dataset_kind, **result}


def _draft_view(session, row: Draft, current_bundle=None) -> dict:
    current_bundle = current_bundle or knowledge()
    source_ids = {action.get("source_id") for action in row.actions if action.get("source_id")}
    sources = {item["id"]: item for item in current_bundle.sources}
    stale_source = any(
        source_id not in sources or
        datetime.fromisoformat(sources[source_id]["review_after"].replace("Z", "+00:00")) < now()
        for source_id in source_ids
    )
    stale = (_stale_refs(session, row.user_id, row.receipt_refs) or
             row.knowledge_version != current_bundle.version or stale_source)
    return {"id": str(row.id), "revision": row.revision, "text": row.text,
            "recipient": deepcopy(row.recipient) if not stale else None,
            "actions": deepcopy(row.actions) if not stale else [],
            "receipt_refs": deepcopy(row.receipt_refs), "stale": stale,
            "knowledge_version": row.knowledge_version,
            "created_at": stamp(row.created_at), "updated_at": stamp(row.updated_at)}


def draft_replay(store: SqlStore, user_id: str, key: str, body: dict) -> dict | None:
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with store.Session() as session:
        prior = session.scalar(select(IdempotencyKey).where(
            IdempotencyKey.user_id == uuid.UUID(user_id),
            IdempotencyKey.route == "POST /api/v1/drafts", IdempotencyKey.key == uuid.UUID(key)))
        if prior is None or aware(prior.expires_at) <= now():
            return None
        if prior.fingerprint != fingerprint:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим запросом.")
        return deepcopy(prior.response_body)


def save_draft(store: SqlStore, user_id: str, key: str, body: dict,
               engine_result: dict) -> dict:
    uid, key_id = uuid.UUID(user_id), uuid.UUID(key)
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    created = now()
    try:
        with store.Session.begin() as session:
            prior = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == "POST /api/v1/drafts",
                IdempotencyKey.key == key_id).with_for_update())
            if prior and aware(prior.expires_at) > created:
                if prior.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим запросом.")
                return deepcopy(prior.response_body)
            if prior:
                session.delete(prior)
                session.flush()
            if not _current_refs(session, uid, body["receipt_refs"]):
                raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменилась до сохранения черновика.")
            row = Draft(id=uuid.uuid4(), user_id=uid, revision=1, text=engine_result["text"],
                        recipient=deepcopy(engine_result["recipient"]),
                        actions=deepcopy(engine_result["actions"]),
                        receipt_refs=deepcopy(engine_result["receipt_refs"]),
                        knowledge_version=engine_result["knowledge_version"],
                        created_at=created, updated_at=created,
                        expires_at=created + timedelta(days=30))
            session.add(row)
            result = _draft_view(session, row)
            session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid, route="POST /api/v1/drafts",
                                       key=key_id, fingerprint=fingerprint, status_code=201,
                                       response_body=deepcopy(result),
                                       expires_at=created + timedelta(hours=24)))
            return result
    except IntegrityError:
        with store.Session() as session:
            prior = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == "POST /api/v1/drafts",
                IdempotencyKey.key == key_id))
            if prior and aware(prior.expires_at) > now() and prior.fingerprint == fingerprint:
                return deepcopy(prior.response_body)
        raise


def get_draft(store: SqlStore, user_id: str, draft_id: str) -> dict:
    with store.Session() as session:
        row = session.scalar(select(Draft).where(
            Draft.id == uuid.UUID(draft_id), Draft.user_id == uuid.UUID(user_id)))
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Черновик не найден.")
        return _draft_view(session, row)


def edit_draft(store: SqlStore, user_id: str, draft_id: str,
               expected_revision: int, text: str) -> dict:
    with store.Session.begin() as session:
        row = session.scalar(select(Draft).where(
            Draft.id == uuid.UUID(draft_id), Draft.user_id == uuid.UUID(user_id)).with_for_update())
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Черновик не найден.")
        if row.revision != expected_revision:
            raise ApiError(409, "REVISION_CONFLICT", "Черновик изменён.",
                           details={"current_revision": row.revision})
        row.revision += 1
        row.text = text
        row.updated_at = now()
        session.flush()
        return _draft_view(session, row)


def delete_draft(store: SqlStore, user_id: str, draft_id: str) -> None:
    with store.Session.begin() as session:
        row = session.scalar(select(Draft).where(
            Draft.id == uuid.UUID(draft_id), Draft.user_id == uuid.UUID(user_id)).with_for_update())
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Черновик не найден.")
        session.delete(row)
        for key in session.scalars(select(IdempotencyKey).where(
            IdempotencyKey.user_id == row.user_id, IdempotencyKey.route == "POST /api/v1/drafts")):
            if key.response_body.get("id") == draft_id:
                session.delete(key)
