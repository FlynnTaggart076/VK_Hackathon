"""Transactional PostgreSQL store for E1 routes; no OCR logic lives here."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
import base64
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, func, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AssistantAnswer, Document, Draft, IdempotencyKey, Job, Profile, Receipt, ReceiptRevision, SessionToken, User, WorkerHeartbeat
from app.errors import ApiError


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def stamp(value: datetime) -> str:
    return aware(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def empty_bill() -> dict:
    return {
        "schema_version": "1.0", "period": None, "currency": "RUB", "issuer_name": None,
        "provider_id": None, "account_number": None, "address_text": None,
        "template_id": None, "template_version": None, "services": [], "adjustments": [],
        "settlement": {"formula_kind": "unsupported", "opening_balance": None,
                       "payments_credited": None, "penalties": None,
                       "other_account_changes": None, "document_closing_balance": None},
        "document_current_charges": None, "document_total_due": None,
    }


class SqlStore:
    def __init__(self, settings: Any):
        self.settings = settings
        if not settings.database_url:
            raise ValueError("DATABASE_URL required")
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite:///") else {}
        self.engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        settings.storage_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _profile_value(profile: Profile) -> dict:
        return {"role": profile.role, "territory_id": profile.territory_id,
                "onboarding_completed": profile.onboarding_completed,
                "privacy_notice_version": profile.privacy_notice_version,
                "privacy_acknowledged_at": stamp(profile.privacy_acknowledged_at) if profile.privacy_acknowledged_at else None}

    def authenticate_demo(self, identity: str, access_code: str) -> dict:
        if not self.settings.demo_auth_enabled or self.settings.mode == "production":
            raise ApiError(403, "DEMO_DISABLED", "Демовход выключен.")
        if identity not in {"reviewer_a", "reviewer_b"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неизвестная демо-учётная запись.")
        if not hmac.compare_digest(access_code, self.settings.demo_access_code or ""):
            raise ApiError(401, "AUTH_REQUIRED", "Неверный код доступа.")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        for attempt in range(2):
            try:
                with self.Session.begin() as session:
                    user = session.scalar(select(User).where(User.demo_identity == identity))
                    if user is None:
                        user = User(id=uuid.uuid4(), demo_identity=identity, created_at=now())
                        session.add(user)
                        session.flush()
                        profile = Profile(user_id=user.id, role="other", territory_id=None,
                                          onboarding_completed=False, privacy_notice_version=None,
                                          privacy_acknowledged_at=None)
                        session.add(profile)
                    else:
                        profile = session.get(Profile, user.id)
                    session.add(SessionToken(id=uuid.uuid4(), user_id=user.id,
                                             token_hash=token_hash, expires_at=now() + timedelta(hours=1)))
                    result = {"access_token": token, "token_type": "bearer", "expires_in": 3600,
                              "user": {"id": str(user.id)}, "profile": self._profile_value(profile)}
                return result
            except IntegrityError:
                if attempt:
                    raise
        raise RuntimeError("unreachable")

    def user_for_token(self, token: str) -> str:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.Session() as session:
            row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
            if row is None or row.revoked_at is not None:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            if aware(row.expires_at) <= now():
                raise ApiError(401, "SESSION_EXPIRED", "Срок сессии истёк.")
            return str(row.user_id)

    def authenticate_max(self, max_user_id: int) -> dict:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        for attempt in range(2):
            try:
                with self.Session.begin() as session:
                    user = session.scalar(select(User).where(User.max_user_id == max_user_id))
                    if user is None:
                        user = User(id=uuid.uuid4(), max_user_id=max_user_id, created_at=now())
                        session.add(user)
                        session.flush()
                        profile = Profile(user_id=user.id, role="other", territory_id=None,
                                          onboarding_completed=False, privacy_notice_version=None,
                                          privacy_acknowledged_at=None)
                        session.add(profile)
                    else:
                        profile = session.get(Profile, user.id)
                    session.add(SessionToken(id=uuid.uuid4(), user_id=user.id,
                                             token_hash=token_hash, expires_at=now() + timedelta(hours=1)))
                    return {"access_token": token, "token_type": "bearer", "expires_in": 3600,
                            "user": {"id": str(user.id)}, "profile": self._profile_value(profile)}
            except IntegrityError:
                if attempt:
                    raise
        raise RuntimeError("unreachable")

    def logout(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.Session.begin() as session:
            row = session.scalar(select(SessionToken).where(
                SessionToken.token_hash == token_hash).with_for_update())
            if row is None or row.revoked_at is not None or aware(row.expires_at) <= now():
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            row.revoked_at = now()

    def comparison_snapshots(self, user_id: str, refs: list[dict]) -> tuple[list[dict], str | None]:
        """Read two current confirmed versions atomically with owner checks."""
        uid = uuid.UUID(user_id)
        ids = [uuid.UUID(item["id"]) for item in refs]
        with self.Session.begin() as session:
            receipts = {row.id: row for row in session.scalars(select(Receipt).where(
                Receipt.id.in_(ids), Receipt.user_id == uid
            ).order_by(Receipt.id).with_for_update()).all()}
            profile = session.get(Profile, uid)
            snapshots = []
            for item, rid in zip(refs, ids):
                receipt = receipts.get(rid)
                if receipt is None:
                    raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
                if receipt.current_revision != item["revision"]:
                    raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена; обновите данные.",
                                   details={"current_revision": receipt.current_revision})
                if receipt.status != "confirmed":
                    raise ApiError(409, "RECEIPT_NOT_CONFIRMED", "Сначала подтвердите обе квитанции.")
                revision = session.get(ReceiptRevision, (rid, receipt.current_revision))
                if revision is None or revision.confirmed_at is None:
                    raise ApiError(409, "RECEIPT_NOT_CONFIRMED", "Сначала подтвердите обе квитанции.")
                snapshots.append({"id": rid, "revision": receipt.current_revision,
                                  "bill_data": deepcopy(revision.bill_data),
                                  "confirmed_at": aware(revision.confirmed_at),
                                  "dataset_kind": receipt.dataset_kind})
            return snapshots, profile.territory_id if profile else None

    def profile(self, user_id: str) -> dict:
        with self.Session() as session:
            profile = session.get(Profile, uuid.UUID(user_id))
            if not profile:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            return self._profile_value(profile)

    def update_profile(self, user_id: str, body: dict) -> dict:
        from app.services.assistant_store import knowledge

        territories = {item["id"] for item in knowledge().territories}
        if body.get("role") not in {"owner", "tenant", "other"} or body.get("territory_id") not in territories:
            raise ApiError(422, "VALIDATION_FAILED", "Выберите доступную роль и территорию.")
        if body.get("privacy_notice_version") != self.settings.privacy_notice_version or body.get("privacy_acknowledged") is not True:
            raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
        if set(body) != {"role", "territory_id", "privacy_notice_version", "privacy_acknowledged"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неизвестные поля профиля.")
        with self.Session.begin() as session:
            profile = session.get(Profile, uuid.UUID(user_id), with_for_update=True)
            if not profile:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            profile.role = body["role"]
            profile.territory_id = body["territory_id"]
            profile.onboarding_completed = True
            profile.privacy_notice_version = body["privacy_notice_version"]
            profile.privacy_acknowledged_at = now()
            return self._profile_value(profile)

    def _existing_idempotency(self, user_id: uuid.UUID, key: uuid.UUID, fingerprint: str) -> dict | None:
        with self.Session() as session:
            record = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.route == "POST /api/v1/receipts",
                IdempotencyKey.key == key,
            ))
            if record and aware(record.expires_at) > now():
                if record.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим файлом.")
                return deepcopy(record.response_body)
            return None

    def upload(self, user_id: str, key: str, content: bytes, mime: str, pages: int,
               dataset_kind: str = "user_provided") -> dict:
        uid, key_id = uuid.UUID(user_id), uuid.UUID(key)
        digest = hashlib.sha256(content).hexdigest()
        fingerprint = hashlib.sha256(f"{mime}:{digest}:{dataset_kind}".encode()).hexdigest()
        prior = self._existing_idempotency(uid, key_id, fingerprint)
        if prior is not None:
            return prior
        storage_key = secrets.token_hex(24)
        path = self.settings.storage_path / storage_key
        with open(path, "xb") as destination:
            destination.write(content)
        try:
            with self.Session.begin() as session:
                profile = session.get(Profile, uid, with_for_update=True)
                if not profile or profile.privacy_notice_version != self.settings.privacy_notice_version:
                    raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
                existing = session.scalar(select(IdempotencyKey).where(
                    IdempotencyKey.user_id == uid, IdempotencyKey.route == "POST /api/v1/receipts",
                    IdempotencyKey.key == key_id).with_for_update())
                if existing:
                    if aware(existing.expires_at) > now():
                        if existing.fingerprint != fingerprint:
                            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим файлом.")
                        path.unlink(missing_ok=True)
                        return deepcopy(existing.response_body)
                    session.delete(existing)
                    session.flush()
                pending = session.scalar(select(func.count()).select_from(Job).where(
                    Job.user_id == uid, Job.state.in_(["queued", "running"])))
                if pending >= 2:
                    raise ApiError(429, "QUEUE_LIMIT_REACHED", "Дождитесь обработки предыдущей квитанции.", retryable=True)
                queued = session.scalar(select(func.count()).select_from(Job).where(Job.state == "queued"))
                if queued >= 20:
                    raise ApiError(429, "QUEUE_LIMIT_REACHED", "Очередь занята.", retryable=True)
                recent = session.scalar(select(func.count()).select_from(Document).where(
                    Document.user_id == uid, Document.created_at >= now() - timedelta(hours=1)))
                if recent >= 10:
                    raise ApiError(429, "RATE_LIMITED", "Лимит загрузок за час.", retryable=True)
                created = now()
                document_id, receipt_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                session.add(Document(id=document_id, user_id=uid, storage_key=storage_key, sha256=digest,
                                     mime_type=mime, size_bytes=len(content), page_count=pages,
                                     expires_at=created + timedelta(days=7), created_at=created))
                session.add(Receipt(id=receipt_id, user_id=uid, document_id=document_id,
                                    status="queued", current_revision=1, dataset_kind=dataset_kind,
                                    created_at=created, updated_at=created))
                session.add(Job(id=job_id, user_id=uid, kind="receipt_ocr", resource_id=receipt_id,
                                operation_key=f"receipt-ocr:{receipt_id}", state="queued", stage=None,
                                attempt=0, run_after=created, created_at=created, updated_at=created))
                result = {"receipt": {
                    "id": str(receipt_id), "status": "queued", "revision": 1,
                    "created_at": stamp(created), "updated_at": stamp(created),
                    "dataset_kind": dataset_kind, "extraction_outcome": None,
                    "bill_data": empty_bill(), "field_evidence": [], "issues": [],
                    "document": {"available": True, "mime_type": mime, "page_count": pages,
                                 "expires_at": stamp(created + timedelta(days=7))},
                    "job": {"id": str(job_id), "state": "queued", "stage": None},
                    "confirmed_at": None, "engine_version": None,
                }, "job_id": str(job_id)}
                session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid,
                                           route="POST /api/v1/receipts", key=key_id,
                                           fingerprint=fingerprint, status_code=202,
                                           response_body=result, expires_at=created + timedelta(hours=24)))
            return result
        except IntegrityError:
            path.unlink(missing_ok=True)
            prior = self._existing_idempotency(uid, key_id, fingerprint)
            if prior is not None:
                return prior
            raise
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def import_demo(self, user_id: str, key: str, fixture_id: str) -> dict:
        if fixture_id not in {"water-2026-08", "water-2026-09"}:
            raise ApiError(404, "NOT_FOUND", "Демообразец не найден.")
        uid, key_id = uuid.UUID(user_id), uuid.UUID(key)
        fingerprint = hashlib.sha256(f"demo:{fixture_id}".encode()).hexdigest()
        with self.Session.begin() as session:
            profile = session.get(Profile, uid, with_for_update=True)
            if not profile or profile.privacy_notice_version != self.settings.privacy_notice_version:
                raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
            existing = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == "POST /api/v1/receipts/demo",
                IdempotencyKey.key == key_id).with_for_update())
            if existing and aware(existing.expires_at) > now():
                if existing.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим образцом.")
                return deepcopy(existing.response_body)
            if existing:
                session.delete(existing)
                session.flush()
            pending = session.scalar(select(func.count()).select_from(Job).where(
                Job.user_id == uid, Job.state.in_(["queued", "running"])))
            if pending >= 2:
                raise ApiError(429, "QUEUE_LIMIT_REACHED", "Дождитесь обработки предыдущей квитанции.", retryable=True)
            created = now()
            receipt_id, job_id = uuid.uuid4(), uuid.uuid4()
            session.add(Receipt(id=receipt_id, user_id=uid, document_id=None, status="queued",
                                current_revision=1, dataset_kind="synthetic", created_at=created, updated_at=created))
            session.add(Job(id=job_id, user_id=uid, kind="demo_import", resource_id=receipt_id,
                            operation_key=f"demo-import:{fixture_id}:{receipt_id}", state="queued", attempt=0,
                            run_after=created, created_at=created, updated_at=created))
            result = {"receipt": {"id": str(receipt_id), "status": "queued", "revision": 1,
                                  "created_at": stamp(created), "updated_at": stamp(created),
                                  "dataset_kind": "synthetic", "extraction_outcome": None,
                                  "bill_data": empty_bill(), "field_evidence": [], "issues": [],
                                  "document": {"available": False, "mime_type": None, "page_count": None, "expires_at": None},
                                  "job": {"id": str(job_id), "state": "queued", "stage": None},
                                  "confirmed_at": None, "engine_version": None},
                      "job_id": str(job_id)}
            session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid,
                                       route="POST /api/v1/receipts/demo", key=key_id,
                                       fingerprint=fingerprint, status_code=202, response_body=result,
                                       expires_at=created + timedelta(hours=24)))
            return result

    def create_manual(self, user_id: str, key: str, bill_data: dict, evidence: list[dict],
                      validation: dict) -> dict:
        uid, key_id = uuid.UUID(user_id), uuid.UUID(key)
        route = "POST /api/v1/receipts/manual"
        fingerprint = hashlib.sha256(json.dumps(bill_data, sort_keys=True).encode()).hexdigest()
        with self.Session.begin() as session:
            profile = session.get(Profile, uid, with_for_update=True)
            if not profile or profile.privacy_notice_version != self.settings.privacy_notice_version:
                raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите уведомление о данных.")
            existing = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == route,
                IdempotencyKey.key == key_id).with_for_update())
            if existing and aware(existing.expires_at) > now():
                if existing.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другими данными.")
                return deepcopy(existing.response_body)
            if existing:
                session.delete(existing)
                session.flush()
            created = now()
            rid = uuid.uuid4()
            receipt = Receipt(id=rid, user_id=uid, document_id=None, status="needs_review",
                              current_revision=1, dataset_kind="user_provided",
                              extraction_outcome="manual_required", created_at=created, updated_at=created)
            session.add(receipt)
            session.add(ReceiptRevision(
                receipt_id=rid, revision=1, bill_data=deepcopy(bill_data),
                extraction_meta={"field_evidence": deepcopy(evidence), "issues": [],
                                 "outcome": "manual_required"},
                validation=deepcopy(validation), confirmed_at=None, engine_version="manual-v1"))
            session.flush()
            result = self._receipt_view(session, receipt)
            session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid, route=route, key=key_id,
                                       fingerprint=fingerprint, status_code=201,
                                       response_body=deepcopy(result), expires_at=created + timedelta(hours=24)))
            return result

    def retry_receipt(self, user_id: str, receipt_id: str, expected_revision: int, key: str) -> dict:
        uid, rid, key_id = uuid.UUID(user_id), uuid.UUID(receipt_id), uuid.UUID(key)
        route = f"POST /api/v1/receipts/{receipt_id}/retry"
        fingerprint = hashlib.sha256(f"{receipt_id}:{expected_revision}".encode()).hexdigest()
        with self.Session.begin() as session:
            profile = session.get(Profile, uid, with_for_update=True)
            if profile is None:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            existing = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == route,
                IdempotencyKey.key == key_id).with_for_update())
            if existing and aware(existing.expires_at) > now():
                if existing.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим запросом.")
                return deepcopy(existing.response_body)
            if existing:
                session.delete(existing)
                session.flush()
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == rid, Receipt.user_id == uid).with_for_update())
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.current_revision != expected_revision:
                raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена; обновите данные.",
                               details={"current_revision": receipt.current_revision})
            if receipt.status != "failed":
                raise ApiError(409, "INVALID_STATE", "Повтор доступен после ошибки обработки.")
            document = session.get(Document, receipt.document_id) if receipt.document_id else None
            if document is None or document.deleted_at is not None or aware(document.expires_at) <= now() or \
                    not (self.settings.storage_path / document.storage_key).is_file():
                raise ApiError(410, "SOURCE_EXPIRED", "Исходный документ недоступен для повтора.")
            pending = session.scalar(select(func.count()).select_from(Job).where(
                Job.user_id == uid, Job.state.in_(["queued", "running"])))
            if pending >= 2:
                raise ApiError(429, "QUEUE_LIMIT_REACHED", "Дождитесь обработки другой квитанции.", retryable=True)
            created = now()
            job = Job(id=uuid.uuid4(), user_id=uid, kind="receipt_ocr", resource_id=rid,
                      operation_key=f"receipt-ocr-retry:{rid}:{key_id}", state="queued", stage=None,
                      attempt=0, run_after=created, created_at=created, updated_at=created)
            session.add(job)
            receipt.status = "queued"
            receipt.extraction_outcome = None
            receipt.updated_at = created
            session.flush()
            result = {"receipt": self._receipt_view(session, receipt), "job_id": str(job.id)}
            session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid, route=route, key=key_id,
                                       fingerprint=fingerprint, status_code=202,
                                       response_body=deepcopy(result),
                                       expires_at=created + timedelta(hours=24)))
            return result

    def _receipt_view(self, session: Session, receipt: Receipt) -> dict:
        document = session.get(Document, receipt.document_id) if receipt.document_id else None
        job = session.scalar(select(Job).where(Job.resource_id == receipt.id)
                             .order_by(Job.created_at.desc()))
        revision = session.get(ReceiptRevision, (receipt.id, receipt.current_revision))
        available = bool(document and document.deleted_at is None and aware(document.expires_at) > now()
                         and (self.settings.storage_path / document.storage_key).is_file())
        evidence = revision.extraction_meta.get("field_evidence", []) if revision else []
        issues = []
        if revision:
            seen = set()
            for issue in (revision.validation.get("errors", []) + revision.validation.get("warnings", []) +
                          revision.extraction_meta.get("issues", [])):
                key = (issue.get("code"), issue.get("path"), issue.get("severity"))
                if key not in seen:
                    seen.add(key)
                    issues.append(issue)
        return {
            "id": str(receipt.id), "status": receipt.status, "revision": receipt.current_revision,
            "created_at": stamp(receipt.created_at), "updated_at": stamp(receipt.updated_at),
            "dataset_kind": receipt.dataset_kind, "extraction_outcome": receipt.extraction_outcome,
            "bill_data": deepcopy(revision.bill_data) if revision else empty_bill(),
            "field_evidence": deepcopy(evidence), "issues": deepcopy(issues),
            "document": {"available": available, "mime_type": document.mime_type if document else None,
                         "page_count": document.page_count if document else None,
                         "expires_at": stamp(document.expires_at) if document else None},
            "job": {"id": str(job.id), "state": job.state, "stage": job.stage} if job else None,
            "confirmed_at": stamp(revision.confirmed_at) if revision and revision.confirmed_at else None,
            "engine_version": revision.engine_version if revision else None,
        }

    def receipt(self, user_id: str, receipt_id: str) -> dict:
        with self.Session() as session:
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == uuid.UUID(receipt_id), Receipt.user_id == uuid.UUID(user_id)))
            if not receipt:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            return self._receipt_view(session, receipt)

    def list_receipts(self, user_id: str, cursor: str | None, limit: int) -> dict:
        if limit < 1 or limit > 50:
            raise ApiError(400, "INVALID_REQUEST", "Некорректный размер страницы.")
        boundary = None
        if cursor is not None:
            if len(cursor) > 512:
                raise ApiError(400, "INVALID_REQUEST", "Некорректный курсор.")
            try:
                raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                value = json.loads(raw)
                if not isinstance(value, list) or len(value) != 2:
                    raise ValueError
                boundary = (datetime.fromisoformat(value[0]), uuid.UUID(value[1]))
            except (ValueError, UnicodeDecodeError, TypeError, OverflowError):
                raise ApiError(400, "INVALID_REQUEST", "Некорректный курсор.") from None
        with self.Session() as session:
            query = select(Receipt).where(Receipt.user_id == uuid.UUID(user_id))
            if boundary:
                query = query.where(tuple_(Receipt.created_at, Receipt.id) < boundary)
            rows = session.scalars(query.order_by(Receipt.created_at.desc(), Receipt.id.desc()).limit(limit + 1)).all()
            items = []
            for row in rows[:limit]:
                view = self._receipt_view(session, row)
                bill = view["bill_data"]
                items.append({"id": view["id"], "status": view["status"], "revision": view["revision"],
                              "period": bill.get("period"), "issuer_name": bill.get("issuer_name"),
                              "document_total_due": bill.get("document_total_due"),
                              "dataset_kind": view["dataset_kind"], "created_at": view["created_at"],
                              "source_available": view["document"]["available"]})
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                payload = json.dumps([aware(last.created_at).isoformat(), str(last.id)]).encode()
                next_cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")
            return {"items": items, "next_cursor": next_cursor}

    def source(self, user_id: str, receipt_id: str) -> tuple[bytes, str]:
        with self.Session() as session:
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == uuid.UUID(receipt_id), Receipt.user_id == uuid.UUID(user_id)))
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.document_id is None:
                raise ApiError(404, "NOT_FOUND", "Исходный документ отсутствует.")
            document = session.get(Document, receipt.document_id)
            if document is None or document.deleted_at is not None or aware(document.expires_at) <= now():
                raise ApiError(410, "SOURCE_EXPIRED", "Срок хранения исходного документа истёк.")
            try:
                return (self.settings.storage_path / document.storage_key).read_bytes(), document.mime_type
            except FileNotFoundError:
                raise ApiError(410, "SOURCE_EXPIRED", "Исходный документ удалён.") from None

    def page(self, user_id: str, receipt_id: str, page: int) -> bytes:
        with self.Session() as session:
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == uuid.UUID(receipt_id), Receipt.user_id == uuid.UUID(user_id)))
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.document_id is None:
                raise ApiError(404, "NOT_FOUND", "Изображение документа отсутствует.")
            document = session.get(Document, receipt.document_id)
            if document is None or document.deleted_at is not None or aware(document.expires_at) <= now():
                raise ApiError(410, "SOURCE_EXPIRED", "Срок хранения исходного документа истёк.")
            if page < 1 or page > document.page_count:
                raise ApiError(404, "NOT_FOUND", "Страница не найдена.")
            if receipt.status in {"queued", "processing"}:
                raise ApiError(409, "PREVIEW_NOT_READY", "Изображение ещё готовится.")
            path = self.settings.storage_path / f"{document.storage_key}.page-{page}.png"
            try:
                return path.read_bytes()
            except FileNotFoundError:
                raise ApiError(503, "PREVIEW_UNAVAILABLE", "Изображение страницы недоступно.", retryable=True) from None

    def delete_receipt(self, user_id: str, receipt_id: str) -> None:
        path = None
        with self.Session.begin() as session:
            # Worker locks job before receipt; preserve that order to avoid a PG deadlock.
            session.scalars(select(Job).where(
                Job.resource_id == uuid.UUID(receipt_id), Job.user_id == uuid.UUID(user_id)
            ).order_by(Job.id).with_for_update()).all()
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == uuid.UUID(receipt_id), Receipt.user_id == uuid.UUID(user_id)).with_for_update())
            if receipt is None:
                return
            if receipt.document_id:
                document = session.get(Document, receipt.document_id, with_for_update=True)
                if document:
                    path = self.settings.storage_path / document.storage_key
                    session.delete(document)
            session.execute(delete(Job).where(Job.resource_id == receipt.id, Job.user_id == receipt.user_id))
            session.execute(delete(AssistantAnswer).where(
                AssistantAnswer.user_id == receipt.user_id, AssistantAnswer.receipt_id == receipt.id))
            deleted_drafts = set()
            for draft in session.scalars(select(Draft).where(Draft.user_id == receipt.user_id)):
                if any(ref.get("id") == receipt_id for ref in draft.receipt_refs):
                    deleted_drafts.add(str(draft.id))
                    session.delete(draft)
            session.execute(delete(ReceiptRevision).where(ReceiptRevision.receipt_id == receipt.id))
            for record in session.scalars(select(IdempotencyKey).where(IdempotencyKey.user_id == receipt.user_id)):
                body = record.response_body
                if isinstance(body, dict) and isinstance(body.get("receipt"), dict) and body["receipt"].get("id") == receipt_id:
                    session.delete(record)
                elif isinstance(body, dict) and record.route == "POST /api/v1/drafts" and body.get("id") in deleted_drafts:
                    session.delete(record)
            session.delete(receipt)
        if path is not None:
            path.unlink(missing_ok=True)
            for preview in path.parent.glob(f"{path.name}.page-*.png"):
                preview.unlink(missing_ok=True)

    def edit_revision(self, user_id: str, receipt_id: str, expected_revision: int,
                      bill_data: dict, evidence: list[dict], issues: list[dict],
                      validation: dict, engine_version: str) -> dict:
        with self.Session.begin() as session:
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == uuid.UUID(receipt_id), Receipt.user_id == uuid.UUID(user_id)).with_for_update())
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.current_revision != expected_revision:
                raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена; обновите данные.",
                               details={"current_revision": receipt.current_revision})
            if receipt.status not in {"needs_review", "confirmed"}:
                raise ApiError(409, "INVALID_STATE", "Редактирование сейчас недоступно.")
            previous = session.get(ReceiptRevision, (receipt.id, expected_revision))
            if previous is None:
                raise ApiError(409, "INVALID_STATE", "Извлечение ещё не завершено.")
            new_revision = expected_revision + 1
            previous_validation = {
                (item.get("code"), item.get("path"), item.get("severity"))
                for item in previous.validation.get("errors", []) + previous.validation.get("warnings", [])
            }
            extraction_issues = [item for item in issues if (
                item.get("code"), item.get("path"), item.get("severity")) not in previous_validation]
            session.add(ReceiptRevision(receipt_id=receipt.id, revision=new_revision,
                                        bill_data=deepcopy(bill_data),
                                        extraction_meta={"field_evidence": deepcopy(evidence),
                                                         "issues": deepcopy(extraction_issues),
                                                         "outcome": receipt.extraction_outcome},
                                        validation=deepcopy(validation), confirmed_at=None,
                                        engine_version=engine_version))
            receipt.current_revision = new_revision
            receipt.status = "needs_review"
            receipt.updated_at = now()
            session.flush()
            return self._receipt_view(session, receipt)

    def confirm_revision(self, user_id: str, receipt_id: str, expected_revision: int,
                         warning_codes: list[str], key: str) -> dict:
        uid, rid, key_id = uuid.UUID(user_id), uuid.UUID(receipt_id), uuid.UUID(key)
        fingerprint = hashlib.sha256(json.dumps(
            [receipt_id, expected_revision, sorted(warning_codes)], separators=(",", ":")).encode()).hexdigest()
        route = f"POST /api/v1/receipts/{receipt_id}/confirm"
        with self.Session.begin() as session:
            profile = session.get(Profile, uid, with_for_update=True)
            if profile is None:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            existing = session.scalar(select(IdempotencyKey).where(
                IdempotencyKey.user_id == uid, IdempotencyKey.route == route,
                IdempotencyKey.key == key_id).with_for_update())
            if existing and aware(existing.expires_at) > now():
                if existing.fingerprint != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим запросом.")
                return deepcopy(existing.response_body)
            if existing:
                session.delete(existing)
                session.flush()
            receipt = session.scalar(select(Receipt).where(
                Receipt.id == rid, Receipt.user_id == uid).with_for_update())
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.current_revision != expected_revision:
                raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена; обновите данные.",
                               details={"current_revision": receipt.current_revision})
            if receipt.status != "needs_review":
                raise ApiError(409, "INVALID_STATE", "Подтверждение сейчас недоступно.")
            prior = session.get(ReceiptRevision, (rid, expected_revision))
            if prior is None:
                raise ApiError(409, "INVALID_STATE", "Извлечение ещё не завершено.")
            from housing_engine import BillData
            from app.services.engine_adapter import validation_json

            validation = validation_json(BillData.model_validate_json(json.dumps(prior.bill_data)))
            if not validation.get("can_confirm") or validation.get("errors"):
                raise ApiError(422, "VALIDATION_FAILED", "Исправьте ошибки в квитанции.",
                               details={"issues": validation.get("errors", [])})
            warnings = validation.get("warnings", []) + [
                issue for issue in prior.extraction_meta.get("issues", [])
                if issue.get("severity") == "warning"]
            required = {item["code"] for item in warnings}
            if not required.issubset(set(warning_codes)):
                raise ApiError(422, "VALIDATION_FAILED", "Подтвердите предупреждения.",
                               details={"unacknowledged_warning_codes": sorted(required - set(warning_codes))})
            created = now()
            session.add(ReceiptRevision(
                receipt_id=rid, revision=expected_revision + 1,
                bill_data=deepcopy(prior.bill_data), extraction_meta=deepcopy(prior.extraction_meta),
                validation=validation, confirmed_at=created,
                engine_version=prior.engine_version))
            receipt.current_revision = expected_revision + 1
            receipt.status = "confirmed"
            receipt.updated_at = created
            session.flush()
            result = self._receipt_view(session, receipt)
            session.add(IdempotencyKey(id=uuid.uuid4(), user_id=uid, route=route, key=key_id,
                                       fingerprint=fingerprint, status_code=200,
                                       response_body=deepcopy(result),
                                       expires_at=created + timedelta(hours=24)))
            return result

    def explanation_snapshot(self, user_id: str, receipt_id: str, revision: int) -> tuple[dict, datetime, str | None]:
        uid, rid = uuid.UUID(user_id), uuid.UUID(receipt_id)
        with self.Session() as session:
            receipt = session.scalar(select(Receipt).where(Receipt.id == rid, Receipt.user_id == uid))
            if receipt is None:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            if receipt.status != "confirmed" or receipt.current_revision != revision:
                raise ApiError(409, "REVISION_CONFLICT", "Нужна подтверждённая текущая версия.",
                               details={"current_revision": receipt.current_revision})
            snapshot = session.get(ReceiptRevision, (rid, revision))
            if snapshot is None or snapshot.confirmed_at is None:
                raise ApiError(409, "INVALID_STATE", "Версия ещё не подтверждена.")
            profile = session.get(Profile, uid)
            return deepcopy(snapshot.bill_data), aware(snapshot.confirmed_at), profile.territory_id if profile else None

    def job(self, user_id: str, job_id: str) -> dict:
        with self.Session() as session:
            job = session.scalar(select(Job).where(Job.id == uuid.UUID(job_id), Job.user_id == uuid.UUID(user_id)))
            if not job:
                raise ApiError(404, "NOT_FOUND", "Задание не найдено.")
            return {"id": str(job.id), "kind": job.kind, "state": job.state, "stage": job.stage,
                    "receipt_id": str(job.resource_id),
                    "error": {"code": job.error_code, "message": "Обработка не удалась.", "retryable": False}
                    if job.error_code else None, "updated_at": stamp(job.updated_at)}

    def ready(self) -> bool:
        with self.Session() as session:
            session.execute(text("SELECT 1"))
            version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            worker = session.get(WorkerHeartbeat, "worker")
            return version == "e3_assistant" and bool(worker and aware(worker.updated_at) > now() - timedelta(seconds=90))
