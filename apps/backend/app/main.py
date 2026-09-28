"""E1 development API. PostgreSQL implementation is connected separately."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
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
    preview_auth_enabled: bool = False
    demo_access_code: str | None = None
    max_bot_token: str | None = None
    max_webhook_secret: str | None = None
    max_web_app: str | None = None
    max_api_base_url: str = "https://platform-api2.max.ru"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-flash"
    engine_mode: str = "stub"
    database_url: str | None = None
    storage_path: Path = Path(".local-storage")
    upload_max_bytes: int = 10_485_760
    pdf_max_pages: int = 3
    image_max_pixels: int = 25_000_000
    privacy_notice_version: str = "2.0"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mode=os.getenv("APP_MODE", "dev"),
            demo_auth_enabled=os.getenv("DEMO_AUTH_ENABLED", "false").lower() == "true",
            preview_auth_enabled=os.getenv("PREVIEW_AUTH_ENABLED", "false").lower() == "true",
            demo_access_code=os.getenv("DEMO_ACCESS_CODE"),
            max_bot_token=os.getenv("MAX_BOT_TOKEN"),
            max_webhook_secret=os.getenv("MAX_WEBHOOK_SECRET"),
            max_web_app=os.getenv("MAX_WEB_APP"),
            max_api_base_url=os.getenv("MAX_API_BASE_URL", "https://platform-api2.max.ru"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            engine_mode=os.getenv("ENGINE_MODE", "stub"),
            database_url=os.getenv("DATABASE_URL"),
            storage_path=Path(os.getenv("STORAGE_PATH", ".local-storage")),
        )

    def validate(self) -> None:
        if self.mode not in {"dev", "demo", "preview", "production"}:
            raise ValueError("APP_MODE must be dev, demo, preview or production")
        if self.engine_mode not in {"real", "stub"}:
            raise ValueError("ENGINE_MODE must be real or stub")
        if self.mode == "production" and (self.demo_auth_enabled or self.engine_mode == "stub"):
            raise ValueError("Production forbids demo auth and engine stub")
        if self.preview_auth_enabled != (self.mode == "preview"):
            raise ValueError("Preview auth requires explicit APP_MODE=preview and PREVIEW_AUTH_ENABLED=true")
        if self.mode == "preview" and (self.demo_auth_enabled or self.max_bot_token or
                                       self.max_webhook_secret or self.max_web_app):
            raise ValueError("Preview forbids demo auth and MAX credentials")
        if self.mode != "dev" and self.engine_mode == "stub":
            raise ValueError("Engine stub is dev-only")
        if self.mode == "production" and (not self.max_bot_token or not self.max_webhook_secret):
            raise ValueError("Production requires MAX bot token and webhook secret")
        if self.mode == "production" and not self.max_web_app:
            raise ValueError("Production requires MAX_WEB_APP for the mini-app button")
        if self.max_webhook_secret and not re.fullmatch(r"[A-Za-z0-9_-]{5,256}", self.max_webhook_secret):
            raise ValueError("MAX_WEBHOOK_SECRET must match MAX subscription format")
        if self.max_web_app and not re.fullmatch(
                r"(?:[A-Za-z][A-Za-z0-9_]{2,63}|https://max\.ru/[A-Za-z][A-Za-z0-9_]{2,63})",
                self.max_web_app):
            raise ValueError("MAX_WEB_APP must be a MAX bot username or max.ru bot link")
        if self.deepseek_model not in {"deepseek-flash", "deepseek-v4-pro"}:
            raise ValueError("DEEPSEEK_MODEL must be an official supported model")
        api_url = urlsplit(self.max_api_base_url)
        if api_url.scheme != "https" or not api_url.hostname or api_url.username or api_url.password or \
                api_url.query or api_url.fragment or api_url.path not in {"", "/"}:
            raise ValueError("MAX_API_BASE_URL must be an HTTPS origin")
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
                "aggregate_opt_in": False,
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

    def logout(self, token: str) -> None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            if digest not in self.sessions:
                raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
            del self.sessions[digest]

    def profile(self, user_id: str) -> dict:
        with self.lock:
            return deepcopy(self.profiles[user_id])

    def update_profile(self, user_id: str, body: dict) -> dict:
        from app.services.assistant_store import knowledge

        territories = {item["id"] for item in knowledge().territories}
        if body.get("role") not in {"owner", "tenant", "other"} or body.get("territory_id") not in territories:
            raise ApiError(422, "VALIDATION_FAILED", "Выберите доступную роль и территорию.")
        if body.get("privacy_notice_version") != self.settings.privacy_notice_version or body.get("privacy_acknowledged") is not True:
            raise ApiError(422, "PRIVACY_NOTICE_REQUIRED", "Подтвердите актуальное уведомление.")
        if set(body) != {"role", "territory_id", "privacy_notice_version", "privacy_acknowledged"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неизвестные поля профиля.")
        with self.lock:
            value = {"role": body["role"], "territory_id": body["territory_id"],
                     "onboarding_completed": True, "privacy_notice_version": body["privacy_notice_version"],
                     "privacy_acknowledged_at": stamp(now()), "aggregate_opt_in": False}
            self.profiles[user_id] = value
            return deepcopy(value)

    def upload(self, user_id: str, key: str, content: bytes, mime: str, pages: int,
               dataset_kind: str = "user_provided") -> dict:
        digest = hashlib.sha256(content).hexdigest()
        fingerprint = hashlib.sha256(f"{mime}:{digest}:{dataset_kind}".encode()).hexdigest()
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
                "dataset_kind": dataset_kind, "extraction_outcome": None,
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
    from app.db.store import SqlStore
    from app.services.assistant_store import knowledge

    trusted_catalog = knowledge()  # Fail startup if the installed catalog is invalid.
    if settings.database_url:
        store = SqlStore(settings)
    else:
        if settings.mode != "dev":
            raise RuntimeError("MemoryStore is dev-only")
        store = MemoryStore(settings)
    app = FastAPI(title="MAX ЖКХ backend", version="1.0.0-e2-dev", root_path=os.getenv("APP_ROOT_PATH", "/team/zhkh"))
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
        return {"api_version": "1.0", "engine_version": "0.1.0" if settings.engine_mode == "real" else None,
                "knowledge_version": trusted_catalog.version if settings.engine_mode == "real" else None,
                "mode": settings.mode,
                "limits": {"upload_max_bytes": settings.upload_max_bytes, "pdf_max_pages": settings.pdf_max_pages,
                           "receipt_retention_days": 120, "source_retention_days": 7},
                "features": {"voice": False, "external_submission": False,
                             "receipt_ocr": settings.engine_mode == "real",
                             "comparison": settings.engine_mode == "real" and bool(settings.database_url),
                             "engine_stub": settings.engine_mode == "stub",
                             "demo_auth": settings.demo_auth_enabled},
                "privacy_notice": {"version": settings.privacy_notice_version,
                                   "text": "Исходные документы хранятся 7 дней, подтверждённые данные квитанций — 120 дней. Для ответа выбранный текст вопроса и обезличенные расчётные факты могут передаваться внешнему сервису DeepSeek; исходные документы, адрес и номер счёта не передаются. Городская статистика использует подтверждённые квитанции только после отдельного согласия; его можно отозвать."}}

    @app.post("/api/v1/auth/demo")
    async def auth_demo(request: Request):
        if settings.mode == "preview":
            raise ApiError(403, "DEMO_DISABLED", "Демовход выключен в preview.")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"identity", "access_code"}:
            raise ApiError(422, "VALIDATION_FAILED", "Неверный запрос демовхода.")
        if not isinstance(body["identity"], str) or not isinstance(body["access_code"], str):
            raise ApiError(422, "VALIDATION_FAILED", "Неверный запрос демовхода.")
        return await run_in_threadpool(store.authenticate_demo, body["identity"], body["access_code"])

    @app.post("/api/v1/auth/preview")
    async def auth_preview(request: Request):
        if settings.mode != "preview" or not settings.preview_auth_enabled:
            raise ApiError(403, "PREVIEW_DISABLED", "Учебный вход недоступен.")
        body = await request.body()
        if body:
            try:
                if json.loads(body) != {}:
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                raise ApiError(422, "VALIDATION_FAILED", "Учебный вход не принимает данные пользователя.") from None
        return await run_in_threadpool(store.authenticate_preview)

    @app.post("/api/v1/auth/max")
    async def auth_max(request: Request):
        if settings.mode == "preview":
            raise ApiError(403, "MAX_DISABLED", "MAX выключен в preview.")
        if not settings.max_bot_token or not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Вход MAX не настроен.", retryable=False)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"init_data"} or not isinstance(body["init_data"], str):
            raise ApiError(422, "VALIDATION_FAILED", "Укажите стартовые данные MAX.")
        from app.services.max_auth import validate_init_data

        max_user_id = validate_init_data(body["init_data"], settings.max_bot_token)
        return await run_in_threadpool(store.authenticate_max, max_user_id)

    @app.post("/integrations/max/webhook")
    async def max_webhook(request: Request,
                          max_secret: str | None = Header(default=None, alias="X-Max-Bot-Api-Secret")):
        if settings.mode == "preview":
            raise ApiError(403, "MAX_DISABLED", "MAX выключен в preview.")
        if not settings.max_webhook_secret or not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Webhook MAX не настроен.", retryable=True)
        if not max_secret or not hmac.compare_digest(max_secret, settings.max_webhook_secret):
            raise ApiError(403, "FORBIDDEN", "Доступ запрещён.")
        raw = await request.body()
        if len(raw) > 65_536:
            raise ApiError(413, "FILE_TOO_LARGE", "Событие слишком велико.")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректное событие MAX.") from None
        from sqlalchemy.exc import SQLAlchemyError

        from app.services.max_queue import enqueue_update, normalize_update

        update = normalize_update(body)
        try:
            await run_in_threadpool(enqueue_update, store, update)
        except SQLAlchemyError:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Очередь webhook недоступна.", retryable=True) from None
        return {"accepted": True}

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        store.logout(authorization[7:])
        return Response(status_code=204)

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

    @app.put("/api/v1/me/aggregate-consent")
    async def update_aggregate_consent(request: Request, user_id: str = Depends(current_user)):
        if not isinstance(store, SqlStore):
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Городская статистика пока недоступна.")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"enabled"} or type(body["enabled"]) is not bool:
            raise ApiError(422, "VALIDATION_FAILED", "Укажите enabled: true или false.")
        from app.services.cohort_store import set_aggregate_consent

        return await run_in_threadpool(set_aggregate_consent, store, user_id, body["enabled"])

    @app.get("/api/v1/catalog")
    def catalog(user_id: str = Depends(current_user)):
        from typing import get_args

        from housing_engine.dto import ServiceCode, Unit

        return {"territories": [{"id": item["id"], "label": item["label"],
                                  "is_synthetic": item["is_synthetic"]}
                                 for item in trusted_catalog.territories],
                "organizations": [{"id": item["id"], "label": item["name"],
                                   "territory_id": item["territory_id"],
                                   "is_synthetic": item["is_synthetic"]}
                                  for item in trusted_catalog.organizations],
                "topics": [{"id": item["id"], "label": item["title"]}
                           for item in trusted_catalog.topics],
                "service_codes": list(get_args(ServiceCode)), "units": list(get_args(Unit)),
                "document_kinds": [],
                "demo_receipts": [
                    {"fixture_id": "water-2026-08", "label": "Вода, август", "description": "Синтетическая квитанция"},
                    {"fixture_id": "water-2026-09", "label": "Вода, сентябрь", "description": "Синтетическая квитанция"},
                ]}

    @app.post("/api/v1/assistant/answers")
    async def create_answer(request: Request, user_id: str = Depends(current_user)):
        if not settings.database_url or settings.engine_mode != "real":
            raise ApiError(503, "ENGINE_UNAVAILABLE", "Ответы пока недоступны.", retryable=True)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        context_fields = {"territory_id", "role", "topic_id", "organization_id",
                          "service_code", "document_kind", "receipt_id", "receipt_revision"}
        if not isinstance(body, dict) or set(body) != {"question", "context"} or \
                not isinstance(body["question"], str) or not 1 <= len(body["question"].strip()) <= 2000 or \
                not isinstance(body["context"], dict) or set(body["context"]) != context_fields:
            raise ApiError(422, "VALIDATION_FAILED", "Проверьте вопрос и контекст.")
        context = body["context"]
        if (context["receipt_id"] is None) != (context["receipt_revision"] is None):
            raise ApiError(422, "VALIDATION_FAILED", "Укажите квитанцию и её ревизию вместе.")
        refs = []
        if context["receipt_id"] is not None:
            try:
                uuid.UUID(context["receipt_id"])
            except (TypeError, ValueError):
                raise ApiError(422, "VALIDATION_FAILED", "Некорректный ID квитанции.") from None
            if type(context["receipt_revision"]) is not int or context["receipt_revision"] < 1:
                raise ApiError(422, "VALIDATION_FAILED", "Некорректная ревизия квитанции.")
            refs = [{"id": context["receipt_id"], "revision": context["receipt_revision"]}]
        from pydantic import ValidationError
        from housing_engine import EngineError

        from app.services.assistant_adapter import answer_json
        from app.services.assistant_store import knowledge, owner_receipt_pair, receipt_snapshots, save_answer
        from app.services.cohort_store import city_comparison

        snapshots, profile = await run_in_threadpool(receipt_snapshots, store, user_id, refs)
        if context["role"] != profile["role"] or context["territory_id"] != profile["territory_id"]:
            raise ApiError(409, "PROFILE_CHANGED", "Профиль изменился; обновите страницу.")
        try:
            bundle = await run_in_threadpool(knowledge)
            personal, _ = await run_in_threadpool(owner_receipt_pair, store, user_id,
                                                  refs[0]["id"] if refs else None)
            result = await run_in_threadpool(
                answer_json, body["question"], context, snapshots, profile, bundle,
                api_key=settings.deepseek_api_key if profile.get("privacy_notice_version") ==
                settings.privacy_notice_version else None,
                model=settings.deepseek_model, personal_snapshots=personal,
                allow_receipt_model=profile.get("privacy_notice_version") == settings.privacy_notice_version,
                city_lookup=lambda rid, code, metric: city_comparison(
                    store, user_id, rid, code, metric))
        except (EngineError, ValidationError) as exc:
            if isinstance(exc, EngineError) and exc.retryable:
                raise ApiError(503, exc.code, exc.message, retryable=True) from None
            raise ApiError(422, "VALIDATION_FAILED", "Некорректный контекст вопроса.") from None
        selected = snapshots or personal if result.get("receipt_ref") else []
        kind = selected[0]["dataset_kind"] if selected else \
            "synthetic" if profile["territory_id"] == "demo-territory" else "public_reference"
        return await run_in_threadpool(save_answer, store, user_id, body["question"],
                                       result, result.get("receipt_ref"), kind)

    @app.get("/api/v1/assistant/answers/{answer_id}")
    def read_answer(answer_id: uuid.UUID, user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "История ответов недоступна.")
        from app.services.assistant_store import get_answer, knowledge

        return get_answer(store, user_id, str(answer_id), knowledge().version)

    @app.post("/api/v1/drafts", status_code=201)
    async def create_draft(request: Request, idempotency_key: str = Header(alias="Idempotency-Key"),
                           user_id: str = Depends(current_user)):
        if not settings.database_url or settings.engine_mode != "real":
            raise ApiError(503, "ENGINE_UNAVAILABLE", "Черновики пока недоступны.", retryable=True)
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"topic_id", "organization_id", "receipt_refs",
                                                       "line_id", "user_question"} or \
                not isinstance(body["topic_id"], str) or not body["topic_id"] or \
                not isinstance(body["receipt_refs"], list) or len(body["receipt_refs"]) > 2 or \
                not isinstance(body["user_question"], str) or len(body["user_question"]) > 2000 or \
                (body["organization_id"] is not None and not isinstance(body["organization_id"], str)):
            raise ApiError(422, "VALIDATION_FAILED", "Проверьте данные черновика.")
        for ref in body["receipt_refs"]:
            if not isinstance(ref, dict) or set(ref) != {"id", "revision"} or \
                    type(ref["revision"]) is not int or ref["revision"] < 1:
                raise ApiError(422, "VALIDATION_FAILED", "Некорректная ссылка на квитанцию.")
            try:
                uuid.UUID(ref["id"])
            except (TypeError, ValueError):
                raise ApiError(422, "VALIDATION_FAILED", "Некорректный ID квитанции.") from None
        if body["line_id"] is not None:
            try:
                uuid.UUID(body["line_id"])
            except (TypeError, ValueError):
                raise ApiError(422, "VALIDATION_FAILED", "Некорректный ID строки.") from None
        from pydantic import ValidationError
        from housing_engine import EngineError

        from app.services.assistant_adapter import draft_json
        from app.services.assistant_store import draft_replay, knowledge, receipt_snapshots, save_draft

        replay = await run_in_threadpool(draft_replay, store, user_id, idempotency_key, body)
        if replay is not None:
            return replay

        snapshots, profile = await run_in_threadpool(receipt_snapshots, store, user_id, body["receipt_refs"])
        try:
            bundle = await run_in_threadpool(knowledge)
            result = await run_in_threadpool(draft_json, body, snapshots, profile, bundle)
        except (EngineError, ValidationError) as exc:
            if isinstance(exc, EngineError) and exc.retryable:
                raise ApiError(503, exc.code, exc.message, retryable=True) from None
            raise ApiError(422, "VALIDATION_FAILED", "Некорректные данные черновика.") from None
        return await run_in_threadpool(save_draft, store, user_id, idempotency_key, body, result)

    @app.get("/api/v1/drafts/{draft_id}")
    def read_draft(draft_id: uuid.UUID, user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "История черновиков недоступна.")
        from app.services.assistant_store import get_draft

        return get_draft(store, user_id, str(draft_id))

    @app.put("/api/v1/drafts/{draft_id}")
    async def update_draft(draft_id: uuid.UUID, request: Request,
                           user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Черновики недоступны.")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"expected_revision", "text"} or \
                type(body["expected_revision"]) is not int or body["expected_revision"] < 1 or \
                not isinstance(body["text"], str) or len(body["text"]) > 5000:
            raise ApiError(422, "VALIDATION_FAILED", "Проверьте ревизию и текст черновика.")
        from app.services.assistant_store import edit_draft

        return await run_in_threadpool(edit_draft, store, user_id, str(draft_id),
                                       body["expected_revision"], body["text"])

    @app.delete("/api/v1/drafts/{draft_id}", status_code=204)
    def remove_draft(draft_id: uuid.UUID, user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Черновики недоступны.")
        from app.services.assistant_store import delete_draft

        delete_draft(store, user_id, str(draft_id))
        return Response(status_code=204)

    @app.post("/api/v1/comparisons")
    async def compare_receipts_http(request: Request, user_id: str = Depends(current_user)):
        if not settings.database_url or settings.engine_mode != "real":
            raise ApiError(503, "ENGINE_UNAVAILABLE", "Сравнение пока недоступно.", retryable=True)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"left", "right", "identity_acknowledged"} or \
                type(body["identity_acknowledged"]) is not bool:
            raise ApiError(422, "VALIDATION_FAILED", "Проверьте запрос сравнения.")
        refs = []
        for field in ("left", "right"):
            ref = body[field]
            if not isinstance(ref, dict) or set(ref) != {"id", "revision"} or \
                    not isinstance(ref["id"], str) or type(ref["revision"]) is not int or ref["revision"] < 1:
                raise ApiError(422, "VALIDATION_FAILED", "Укажите обе версии квитанций.")
            try:
                uuid.UUID(ref["id"])
            except ValueError:
                raise ApiError(422, "VALIDATION_FAILED", "Некорректный ID квитанции.") from None
            refs.append(ref)
        from app.services.comparison_adapter import compare_json
        from housing_engine import EngineError

        snapshots, territory = await run_in_threadpool(store.comparison_snapshots, user_id, refs)
        try:
            return await run_in_threadpool(compare_json, snapshots, territory, body["identity_acknowledged"])
        except EngineError as exc:
            status = 409 if exc.code == "INCOMPARABLE_RECEIPTS" else 503 if exc.retryable else 422
            raise ApiError(status, exc.code, exc.message, retryable=exc.retryable) from None

    @app.get("/api/v1/receipts/{receipt_id}/city-comparison")
    async def city_comparison_http(receipt_id: uuid.UUID, service_code: str, metric: str,
                                   user_id: str = Depends(current_user)):
        if not isinstance(store, SqlStore) or settings.engine_mode != "real":
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Городская статистика пока недоступна.")
        from app.services.cohort_store import city_comparison

        return await run_in_threadpool(city_comparison, store, user_id, str(receipt_id),
                                       service_code, metric)

    @app.post("/api/v1/receipts", status_code=202)
    async def upload_receipt(file: UploadFile, idempotency_key: str = Header(alias="Idempotency-Key"),
                             demo_sample_id: str | None = Form(default=None),
                             user_id: str = Depends(current_user)):
        if settings.mode == "preview":
            await file.close()
            raise ApiError(403, "PREVIEW_SYNTHETIC_ONLY", "В preview доступны только учебные квитанции из каталога.")
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        content = await file.read(settings.upload_max_bytes + 1)
        await file.close()
        mime, pages = inspect_document(content, file.content_type or "", settings)
        from app.services.demo_samples import dataset_kind

        kind = dataset_kind(content, mime, demo_sample_id)
        return await run_in_threadpool(store.upload, user_id, idempotency_key, content, mime, pages, kind)

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

    @app.post("/api/v1/receipts/manual", status_code=201)
    async def create_manual_receipt(request: Request,
                                    idempotency_key: str = Header(alias="Idempotency-Key"),
                                    user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для ручного ввода нужна постоянная БД.")
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"bill_data"}:
            raise ApiError(422, "VALIDATION_FAILED", "Укажите данные квитанции.")
        from app.services.engine_adapter import bill_from_client, validation_json
        from app.services.revision_logic import rebase_evidence

        bill = bill_from_client(body["bill_data"], manual=True)
        data = bill.model_dump(mode="json")
        evidence = rebase_evidence({}, data, [])
        return await run_in_threadpool(store.create_manual, user_id, idempotency_key,
                                       data, evidence, validation_json(bill))

    @app.get("/api/v1/receipts/{receipt_id}")
    def get_receipt(receipt_id: uuid.UUID, user_id: str = Depends(current_user)):
        return store.receipt(user_id, str(receipt_id))

    @app.get("/api/v1/receipts")
    def list_receipts(cursor: str | None = None, limit: int = 20,
                      user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для списка квитанций нужна постоянная БД.")
        return store.list_receipts(user_id, cursor, limit)

    @app.get("/api/v1/receipts/{receipt_id}/source")
    def get_receipt_source(receipt_id: uuid.UUID, user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для хранения документа нужна постоянная БД.")
        content, mime = store.source(user_id, str(receipt_id))
        suffix = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[mime]
        return Response(content=content, media_type=mime,
                        headers={"Content-Disposition": f'attachment; filename="receipt.{suffix}"',
                                 "Cache-Control": "no-store"})

    @app.get("/api/v1/receipts/{receipt_id}/pages/{page}")
    def get_receipt_page(receipt_id: uuid.UUID, page: int,
                         user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для страницы нужна постоянная БД.")
        return Response(content=store.page(user_id, str(receipt_id), page),
                        media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.delete("/api/v1/receipts/{receipt_id}", status_code=204)
    def delete_receipt(receipt_id: uuid.UUID, user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для удаления нужна постоянная БД.")
        store.delete_receipt(user_id, str(receipt_id))
        return Response(status_code=204)

    @app.put("/api/v1/receipts/{receipt_id}/draft")
    async def edit_receipt(receipt_id: uuid.UUID, request: Request,
                           user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для правки нужна постоянная БД.")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"expected_revision", "bill_data"} or \
                type(body["expected_revision"]) is not int or body["expected_revision"] < 1:
            raise ApiError(422, "VALIDATION_FAILED", "Укажите версию и данные квитанции.")
        from app.services.engine_adapter import bill_from_client, validation_json
        from app.services.revision_logic import rebase_evidence

        previous = store.receipt(user_id, str(receipt_id))
        if previous["revision"] != body["expected_revision"]:
            raise ApiError(409, "REVISION_CONFLICT", "Квитанция изменена; обновите данные.",
                           details={"current_revision": previous["revision"]})
        canonical = bill_from_client(body["bill_data"], previous["bill_data"])
        data = canonical.model_dump(mode="json")
        validation = validation_json(canonical)
        evidence = rebase_evidence(previous["bill_data"], data, previous["field_evidence"])
        return await run_in_threadpool(
            store.edit_revision, user_id, str(receipt_id), body["expected_revision"], data,
            evidence, previous["issues"], validation, previous["engine_version"] or "manual-v1",
        )

    @app.post("/api/v1/receipts/{receipt_id}/confirm")
    async def confirm_receipt(receipt_id: uuid.UUID, request: Request,
                              idempotency_key: str = Header(alias="Idempotency-Key"),
                              user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для подтверждения нужна постоянная БД.")
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"expected_revision", "acknowledged_warning_codes"} or \
                type(body["expected_revision"]) is not int or body["expected_revision"] < 1 or \
                not isinstance(body["acknowledged_warning_codes"], list) or \
                any(not isinstance(code, str) or not code for code in body["acknowledged_warning_codes"]) or \
                len(set(body["acknowledged_warning_codes"])) != len(body["acknowledged_warning_codes"]):
            raise ApiError(422, "VALIDATION_FAILED", "Проверьте версию и предупреждения.")
        return await run_in_threadpool(
            store.confirm_revision, user_id, str(receipt_id), body["expected_revision"],
            body["acknowledged_warning_codes"], idempotency_key,
        )

    @app.post("/api/v1/receipts/{receipt_id}/retry", status_code=202)
    async def retry_receipt(receipt_id: uuid.UUID, request: Request,
                            idempotency_key: str = Header(alias="Idempotency-Key"),
                            user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для повтора нужна постоянная БД.")
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", "Idempotency-Key должен быть UUID.") from None
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_REQUEST", "Некорректный JSON.") from None
        if not isinstance(body, dict) or set(body) != {"expected_revision"} or \
                type(body["expected_revision"]) is not int or body["expected_revision"] < 1:
            raise ApiError(422, "VALIDATION_FAILED", "Укажите текущую версию.")
        return await run_in_threadpool(store.retry_receipt, user_id, str(receipt_id),
                                       body["expected_revision"], idempotency_key)

    @app.get("/api/v1/receipts/{receipt_id}/explanation")
    def explain_receipt(receipt_id: uuid.UUID, revision: int,
                        user_id: str = Depends(current_user)):
        if not settings.database_url:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Для объяснения нужна постоянная БД.")
        if revision < 1:
            raise ApiError(422, "VALIDATION_FAILED", "Версия должна быть положительной.")
        from app.services.engine_adapter import explain_json
        from housing_engine import EngineError

        bill, confirmed_at, territory = store.explanation_snapshot(user_id, str(receipt_id), revision)
        try:
            return explain_json(receipt_id, revision, bill, confirmed_at, territory)
        except EngineError as exc:
            raise ApiError(503 if exc.retryable else 422, exc.code, exc.message, retryable=exc.retryable) from None

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
