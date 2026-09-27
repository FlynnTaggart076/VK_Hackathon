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

from app.db.models import Document, IdempotencyKey, Job, Profile, Receipt, ReceiptRevision, SessionToken, User, WorkerHeartbeat
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

    def profile(self, user_id: str) -> dict:
        with self.Session() as session:
            profile = session.get(Profile, uuid.UUID(user_id))
            if not profile:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            return self._profile_value(profile)

    def update_profile(self, user_id: str, body: dict) -> dict:
        if body.get("role") not in {"owner", "tenant", "other"} or body.get("territory_id") != "demo-territory":
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

    def upload(self, user_id: str, key: str, content: bytes, mime: str, pages: int) -> dict:
        uid, key_id = uuid.UUID(user_id), uuid.UUID(key)
        digest = hashlib.sha256(content).hexdigest()
        fingerprint = hashlib.sha256(f"{mime}:{digest}".encode()).hexdigest()
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
                                    status="queued", current_revision=1, dataset_kind="user_provided",
                                    created_at=created, updated_at=created))
                session.add(Job(id=job_id, user_id=uid, kind="receipt_ocr", resource_id=receipt_id,
                                operation_key=f"receipt-ocr:{receipt_id}", state="queued", stage=None,
                                attempt=0, run_after=created, created_at=created, updated_at=created))
                result = {"receipt": {
                    "id": str(receipt_id), "status": "queued", "revision": 1,
                    "created_at": stamp(created), "updated_at": stamp(created),
                    "dataset_kind": "user_provided", "extraction_outcome": None,
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

    def _receipt_view(self, session: Session, receipt: Receipt) -> dict:
        document = session.get(Document, receipt.document_id) if receipt.document_id else None
        job = session.scalar(select(Job).where(Job.resource_id == receipt.id)
                             .order_by(Job.created_at.desc()))
        revision = session.get(ReceiptRevision, (receipt.id, receipt.current_revision))
        available = bool(document and document.deleted_at is None and aware(document.expires_at) > now()
                         and (self.settings.storage_path / document.storage_key).is_file())
        evidence = revision.extraction_meta.get("field_evidence", []) if revision else []
        issues = revision.extraction_meta.get("issues", []) if revision else []
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

    def delete_receipt(self, user_id: str, receipt_id: str) -> None:
        path = None
        with self.Session.begin() as session:
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
            session.execute(delete(ReceiptRevision).where(ReceiptRevision.receipt_id == receipt.id))
            for record in session.scalars(select(IdempotencyKey).where(IdempotencyKey.user_id == receipt.user_id)):
                body = record.response_body
                if isinstance(body, dict) and isinstance(body.get("receipt"), dict) and body["receipt"].get("id") == receipt_id:
                    session.delete(record)
            session.delete(receipt)
        if path is not None:
            path.unlink(missing_ok=True)

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
            if receipt.status != "needs_review":
                raise ApiError(409, "INVALID_STATE", "Редактирование сейчас недоступно.")
            previous = session.get(ReceiptRevision, (receipt.id, expected_revision))
            if previous is None:
                raise ApiError(409, "INVALID_STATE", "Извлечение ещё не завершено.")
            new_revision = expected_revision + 1
            session.add(ReceiptRevision(receipt_id=receipt.id, revision=new_revision,
                                        bill_data=deepcopy(bill_data),
                                        extraction_meta={"field_evidence": deepcopy(evidence),
                                                         "issues": deepcopy(issues),
                                                         "outcome": receipt.extraction_outcome},
                                        validation=deepcopy(validation), confirmed_at=None,
                                        engine_version=engine_version))
            receipt.current_revision = new_revision
            receipt.updated_at = now()
            session.flush()
            return self._receipt_view(session, receipt)

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
            return version == "e1_initial" and bool(worker and aware(worker.updated_at) > now() - timedelta(seconds=90))
