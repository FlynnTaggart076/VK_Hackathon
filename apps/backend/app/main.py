"""E1 development API. PostgreSQL implementation is connected separately."""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import secrets
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from app.errors import ApiError


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Settings:
    mode: str = "dev"
    demo_auth_enabled: bool = False
    demo_access_code: str | None = None
    engine_mode: str = "stub"
    database_url: str | None = None
    storage_path: Path = Path(".local-storage")
    upload_max_bytes: int = 10_485_760
    pdf_max_pages: int = 3
    image_max_pixels: int = 25_000_000
    privacy_notice_version: str = "1.0"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mode=os.getenv("APP_MODE", "dev"),
            demo_auth_enabled=os.getenv("DEMO_AUTH_ENABLED", "false").lower() == "true",
            demo_access_code=os.getenv("DEMO_ACCESS_CODE"),
            engine_mode=os.getenv("ENGINE_MODE", "stub"),
            database_url=os.getenv("DATABASE_URL"),
            storage_path=Path(os.getenv("STORAGE_PATH", ".local-storage")),
        )

    def validate(self) -> None:
        if self.mode not in {"dev", "demo", "production"}:
            raise ValueError("APP_MODE must be dev, demo or production")
        if self.engine_mode not in {"real", "stub"}:
            raise ValueError("ENGINE_MODE must be real or stub")
        if self.mode == "production" and (self.demo_auth_enabled or self.engine_mode == "stub"):
            raise ValueError("Production forbids demo auth and engine stub")
        if self.mode != "dev":
            raise ValueError("E1 backend supports dev mode only; MAX and real engine are not integrated")
        if self.demo_auth_enabled and not self.demo_access_code:
            raise ValueError("DEMO_ACCESS_CODE required when demo auth is enabled")
        if self.mode != "dev" and not self.database_url:
            raise ValueError("Persistent DATABASE_URL required outside dev")
        if self.database_url and not self.database_url.startswith("postgresql+psycopg://"):
            if not (self.mode == "dev" and self.database_url.startswith("sqlite:///")):
                raise ValueError("PostgreSQL psycopg URL required outside isolated dev tests")


def error_response(request: Request, error: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    headers = {"X-Request-ID": request_id}
    if error.status == 429:
        headers["Retry-After"] = "30"
    return JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": error.message,
                           "retryable": error.retryable, "fields": [], "details": error.details},
                 "request_id": request_id},
        headers=headers,
    )


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


def inspect_document(content: bytes, declared_mime: str, settings: Settings) -> tuple[str, int]:
    if not content:
        raise ApiError(400, "INVALID_DOCUMENT", "Пустой файл.")
    if len(content) > settings.upload_max_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", "Файл превышает лимит загрузки.")
    if declared_mime not in {"application/pdf", "image/jpeg", "image/png"}:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Поддерживаются PDF, JPEG и PNG.")
    if content.startswith(b"%PDF-"):
        actual = "application/pdf"
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ApiError(400, "INVALID_DOCUMENT", "Зашифрованный PDF не поддерживается.")
            page_count = len(reader.pages)
            if page_count < 1:
                raise ApiError(400, "INVALID_DOCUMENT", "PDF без страниц.")
            if page_count > settings.pdf_max_pages:
                raise ApiError(413, "PAGE_LIMIT_EXCEEDED", "Слишком много страниц.")
            for page in reader.pages:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                if width <= 0 or height <= 0 or width * height * (150 / 72) ** 2 > settings.image_max_pixels:
                    raise ApiError(413, "IMAGE_TOO_LARGE", "Размер страницы превышает лимит.")
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, "INVALID_DOCUMENT", "PDF повреждён или не поддерживается.") from None
    else:
        try:
            with Image.open(io.BytesIO(content)) as image:
                actual = {"JPEG": "image/jpeg", "PNG": "image/png"}.get(image.format)
                if not actual:
                    raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Поддерживаются PDF, JPEG и PNG.")
                if image.width * image.height > settings.image_max_pixels:
                    raise ApiError(413, "IMAGE_TOO_LARGE", "Изображение превышает лимит.")
                image.verify()
            page_count = 1
        except ApiError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
            raise ApiError(400, "INVALID_DOCUMENT", "Изображение повреждено.") from None
    if actual != declared_mime:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Тип файла не совпадает с содержимым.")
    return actual, page_count


class MemoryStore:
    """Explicit dev-only adapter for early API integration; never used in production."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.users: dict[str, str] = {}
        self.profiles: dict[str, dict] = {}
        self.sessions: dict[str, tuple[str, datetime]] = {}
        self.receipts: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, dict, datetime]] = {}
        settings.storage_path.mkdir(parents=True, exist_ok=True)

    def authenticate_demo(self, identity: str, access_code: str) -> dict:
        if not self.settings.demo_auth_enabled or self.settings.mode == "production":
            raise ApiError(403, "DEMO_DISABLED", "Демовход выключен.")
        if identity not in {"reviewer_a", "reviewer_b"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неизвестная демо-учётная запись.")
        if not hmac.compare_digest(access_code, self.settings.demo_access_code or ""):
            raise ApiError(401, "AUTH_REQUIRED", "Неверный код доступа.")
        with self.lock:
            user_id = self.users.setdefault(identity, str(uuid.uuid4()))
            profile = self.profiles.setdefault(user_id, {
                "role": "other", "territory_id": None, "onboarding_completed": False,
                "privacy_notice_version": None, "privacy_acknowledged_at": None,
            })
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (user_id, now() + timedelta(hours=1))
            return {"access_token": token, "token_type": "bearer", "expires_in": 3600,
                    "user": {"id": user_id}, "profile": deepcopy(profile)}

    def user_for_token(self, token: str) -> str:
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            record = self.sessions.get(digest)
            if not record:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            if record[1] <= now():
                del self.sessions[digest]
                raise ApiError(401, "SESSION_EXPIRED", "Срок сессии истёк.")
            return record[0]

    def profile(self, user_id: str) -> dict:
        with self.lock:
            return deepcopy(self.profiles[user_id])

    def update_profile(self, user_id: str, body: dict) -> dict:
        if body.get("role") not in {"owner", "tenant", "other"} or body.get("territory_id") != "demo-territory":
            raise ApiError(422, "VALIDATION_FAILED", "Выберите доступную роль и территорию.")
        if body.get("privacy_notice_version") != self.settings.privacy_notice_version or body.get("privacy_acknowledged") is not True:
            raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
        if set(body) != {"role", "territory_id", "privacy_notice_version", "privacy_acknowledged"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неизвестные поля профиля.")
        with self.lock:
            value = {"role": body["role"], "territory_id": body["territory_id"],
                     "onboarding_completed": True, "privacy_notice_version": body["privacy_notice_version"],
                     "privacy_acknowledged_at": stamp(now())}
            self.profiles[user_id] = value
            return deepcopy(value)

    def upload(self, user_id: str, key: str, content: bytes, mime: str, pages: int) -> dict:
        digest = hashlib.sha256(content).hexdigest()
        fingerprint = hashlib.sha256(f"{mime}:{digest}".encode()).hexdigest()
        idem_key = (user_id, "POST /api/v1/receipts", key)
        with self.lock:
            profile = self.profiles[user_id]
            if profile["privacy_notice_version"] != self.settings.privacy_notice_version:
                raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
            prior = self.idempotency.get(idem_key)
            if prior and prior[2] > now():
                if prior[0] != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим файлом.")
                return deepcopy(prior[1])
            pending = sum(1 for job in self.jobs.values() if job["user_id"] == user_id and job["state"] in {"queued", "running"})
            if pending >= 2:
                raise ApiError(429, "QUEUE_LIMIT_REACHED", "Дождитесь обработки предыдущей квитанции.", retryable=True)
            if sum(job["state"] == "queued" for job in self.jobs.values()) >= 20:
                raise ApiError(429, "QUEUE_LIMIT_REACHED", "Очередь занята.", retryable=True)
            receipt_id, job_id, document_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            storage_key = secrets.token_hex(24)
            path = self.settings.storage_path / storage_key
            with open(path, "xb") as destination:
                destination.write(content)
            created = now()
            receipt = {
                "id": receipt_id, "status": "queued", "revision": 1,
                "created_at": stamp(created), "updated_at": stamp(created),
                "dataset_kind": "user_provided", "extraction_outcome": None,
                "bill_data": empty_bill(), "field_evidence": [], "issues": [],
                "document": {"available": True, "mime_type": mime, "page_count": pages,
                             "expires_at": stamp(created + timedelta(days=7))},
                "job": {"id": job_id, "state": "queued", "stage": None},
                "confirmed_at": None, "engine_version": None,
                "_user_id": user_id, "_document_id": document_id, "_storage_key": storage_key,
                "_sha256": digest,
            }
            self.receipts[receipt_id] = receipt
            self.jobs[job_id] = {"id": job_id, "kind": "receipt_ocr", "state": "queued", "stage": None,
                                 "receipt_id": receipt_id, "error": None, "updated_at": stamp(created),
                                 "user_id": user_id}
            result = {"receipt": self._public_receipt(receipt), "job_id": job_id}
            self.idempotency[idem_key] = (fingerprint, deepcopy(result), created + timedelta(hours=24))
            return result

    def import_demo(self, user_id: str, key: str, fixture_id: str) -> dict:
        if fixture_id not in {"water-2026-08", "water-2026-09"}:
            raise ApiError(404, "NOT_FOUND", "Демообразец не найден.")
        fingerprint = hashlib.sha256(f"demo:{fixture_id}".encode()).hexdigest()
        idem_key = (user_id, "POST /api/v1/receipts/demo", key)
        with self.lock:
            if self.profiles[user_id]["privacy_notice_version"] != self.settings.privacy_notice_version:
                raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
            prior = self.idempotency.get(idem_key)
            if prior and prior[2] > now():
                if prior[0] != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим образцом.")
                return deepcopy(prior[1])
            created = now()
            receipt_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
            receipt = {"id": receipt_id, "status": "queued", "revision": 1,
                       "created_at": stamp(created), "updated_at": stamp(created),
                       "dataset_kind": "synthetic", "extraction_outcome": None,
                       "bill_data": empty_bill(), "field_evidence": [], "issues": [],
                       "document": {"available": False, "mime_type": None, "page_count": None, "expires_at": None},
                       "job": {"id": job_id, "state": "queued", "stage": None},
                       "confirmed_at": None, "engine_version": None,
                       "_user_id": user_id, "_fixture_id": fixture_id}
            self.receipts[receipt_id] = receipt
            self.jobs[job_id] = {"id": job_id, "kind": "demo_import", "state": "queued", "stage": None,
                                 "receipt_id": receipt_id, "error": None, "updated_at": stamp(created),
                                 "user_id": user_id}
            result = {"receipt": self._public_receipt(receipt), "job_id": job_id}
            self.idempotency[idem_key] = (fingerprint, deepcopy(result), created + timedelta(hours=24))
            return result

    @staticmethod
    def _public_receipt(receipt: dict) -> dict:
        return {key: deepcopy(value) for key, value in receipt.items() if not key.startswith("_")}

    def receipt(self, user_id: str, receipt_id: str) -> dict:
        with self.lock:
            receipt = self.receipts.get(receipt_id)
            if not receipt or receipt["_user_id"] != user_id:
                raise ApiError(404, "NOT_FOUND", "Квитанция не найдена.")
            return self._public_receipt(receipt)

    def job(self, user_id: str, job_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["user_id"] != user_id:
                raise ApiError(404, "NOT_FOUND", "Задание не найдено.")
            return {key: deepcopy(value) for key, value in job.items() if key != "user_id"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    if settings.database_url:
        from app.db.store import SqlStore
        store = SqlStore(settings)
    else:
        if settings.mode != "dev":
            raise RuntimeError("MemoryStore is dev-only")
        store = MemoryStore(settings)
    app = FastAPI(title="MAX ЖКХ backend", version="1.0.0-e1-dev", root_path=os.getenv("APP_ROOT_PATH", "/team/zhkh"))
    app.state.store = store

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        fields = []
        for item in exc.errors():
            path = "/" + "/".join(str(part) for part in item.get("loc", ()))
            fields.append({"path": path, "message": item.get("msg", "Некорректное поле")})
        request_id = request.state.request_id
        return JSONResponse(status_code=422,
                            content={"error": {"code": "VALIDATION_FAILED", "message": "Проверьте поля запроса.",
                                               "retryable": False, "fields": fields, "details": {}},
                                     "request_id": request_id},
                            headers={"X-Request-ID": request_id})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        return error_response(request, ApiError(503, "SERVICE_UNAVAILABLE", "Сервис временно недоступен.", retryable=True))

    def current_user(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        return store.user_for_token(authorization[7:])

    @app.get("/api/v1/meta")
    def meta():
        return {"api_version": "1.0", "engine_version": None, "knowledge_version": None,
                "mode": settings.mode,
                "limits": {"upload_max_bytes": settings.upload_max_bytes, "pdf_max_pages": settings.pdf_max_pages,
                           "receipt_retention_days": 30, "source_retention_days": 7},
                "features": {"voice": False, "external_submission": False, "receipt_ocr": False,
                             "comparison": False, "engine_stub": settings.engine_mode == "stub",
                             "demo_auth": settings.demo_auth_enabled},
                "privacy_notice": {"version": settings.privacy_notice_version,
                                   "text": "Исходные документы хранятся 7 дней, данные квитанций — 30 дней."}}

    @app.post("/api/v1/auth/demo")
    async def auth_demo(request: Request):
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"identity", "access_code"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неверный запрос демовхода.")
        if not isinstance(body["identity"], str) or not isinstance(body["access_code"], str):
            raise ApiError(422, "VALIDATION_FAILED", "Неверный запрос демовхода.")
        return await run_in_threadpool(store.authenticate_demo, body["identity"], body["access_code"])

    @app.post("/api/v1/auth/max")
    def auth_max():
        raise ApiError(503, "SERVICE_UNAVAILABLE", "Вход MAX ещё не подключён.", retryable=False)

    @app.get("/api/v1/me")
    def me(user_id: str = Depends(current_user)):
        return {"user": {"id": user_id}, "profile": store.profile(user_id)}

    @app.put("/api/v1/me/profile")
    async def update_profile(request: Request, user_id: str = Depends(current_user)):
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict):
            raise ApiError(422, "VALIDATION_FAILED", "Неверный профиль.")
        return await run_in_threadpool(store.update_profile, user_id, body)

    @app.get("/api/v1/catalog")
    def catalog(user_id: str = Depends(current_user)):
        return {"territories": [{"id": "demo-territory", "label": "Учебная территория"}],
                "organizations": [], "topics": [], "service_codes": [], "units": [], "document_kinds": [],
                "demo_receipts": [
                    {"fixture_id": "water-2026-08", "label": "Вода, август", "description": "Синтетическая квитанция"},
                    {"fixture_id": "water-2026-09", "label": "Вода, сентябрь", "description": "Синтетическая квитанция"},
                ]}

    @app.post("/api/v1/receipts", status_code=202)
    async def upload_receipt(file: UploadFile, idempotency_key: str = Header(alias="Idempotency-Key"),
                             user_id: str = Depends(current_user)):
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        content = await file.read(settings.upload_max_bytes + 1)
        await file.close()
        mime, pages = inspect_document(content, file.content_type or "", settings)
        return await run_in_threadpool(store.upload, user_id, idempotency_key, content, mime, pages)

    @app.post("/api/v1/receipts/demo", status_code=202)
    async def import_demo(request: Request, idempotency_key: str = Header(alias="Idempotency-Key"),
                          user_id: str = Depends(current_user)):
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"fixture_id"} or not isinstance(body["fixture_id"], str):
            raise ApiError(422, "VALIDATION_FAILED", "Выберите демообразец.")
        return await run_in_threadpool(store.import_demo, user_id, idempotency_key, body["fixture_id"])

    @app.get("/api/v1/receipts/{receipt_id}")
    def get_receipt(receipt_id: uuid.UUID, user_id: str = Depends(current_user)):
        return store.receipt(user_id, str(receipt_id))

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: uuid.UUID, user_id: str = Depends(current_user)):
        return store.job(user_id, str(job_id))

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        if not settings.database_url or not store.ready():
            raise ApiError(503, "SERVICE_UNAVAILABLE", "БД или worker не готовы.", retryable=True)
        return {"status": "ready"}

    return app


app = create_app()
