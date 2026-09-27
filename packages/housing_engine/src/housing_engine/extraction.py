"""One synthetic bill layout, read from bytes. No filename-based fixture lookup."""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid5

import pypdfium2
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

from .dto import BillData, DocumentInput, ExtractionConfig, ExtractionResult, FieldEvidence, Issue
from .errors import EngineError
from .receipts import validate_bill


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ENGINE_VERSION = "0.1.0"
TEMPLATE_ID = "demo-bill-v1"
AMOUNT = r"-?(?:0|[1-9][0-9]{0,8})\.[0-9]{2}"
DECIMAL = r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?"
ROW_RE = re.compile(rf"^Cold water\s*\(m3\)\s*(?:\|\s*)?({DECIMAL})\s*(?:\|\s*)?({DECIMAL})\s*(?:\|\s*)?({AMOUNT})\s*$", re.I)


def _empty_bill() -> BillData:
    return BillData(
        schema_version="1.0", period=None, currency="RUB", issuer_name=None,
        provider_id=None, account_number=None, address_text=None,
        template_id=None, template_version=None, services=[], adjustments=[],
        settlement={
            "formula_kind": "unsupported", "opening_balance": None,
            "payments_credited": None, "penalties": None,
            "other_account_changes": None, "document_closing_balance": None,
        },
        document_current_charges=None, document_total_due=None,
    )


def _manual(code: str, message: str) -> ExtractionResult:
    return ExtractionResult(
        outcome="manual_required", bill_data=_empty_bill(), field_evidence=[],
        issues=[Issue(code=code, severity="warning", path=None, message=message)],
        template_id=None, engine_version=ENGINE_VERSION,
    )


def _check_document(document: DocumentInput) -> None:
    if not document.content or len(document.content) > MAX_DOCUMENT_BYTES:
        raise EngineError("RESOURCE_LIMIT", "Размер документа вне допустимого предела.")
    if hashlib.sha256(document.content).hexdigest() != document.sha256:
        raise EngineError("CORRUPT_DOCUMENT", "Контрольная сумма документа не совпадает.")
    signatures = {
        "application/pdf": document.content.startswith(b"%PDF-"),
        "image/png": document.content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": document.content.startswith(b"\xff\xd8\xff"),
    }
    if not signatures[document.mime_type]:
        raise EngineError("CORRUPT_DOCUMENT", "Формат файла не соответствует заявленному типу.")


def _pdf_text(document: DocumentInput, config: ExtractionConfig) -> tuple[list[str], int]:
    try:
        reader = PdfReader(io.BytesIO(document.content), strict=False)
        if reader.is_encrypted:
            raise EngineError("ENCRYPTED_PDF", "Загрузите PDF без пароля.")
        page_count = len(reader.pages)
        if not 1 <= page_count <= config.max_pages:
            raise EngineError("RESOURCE_LIMIT", "Превышен предел страниц PDF.")
        return [(page.extract_text() or "")[:100_000] for page in reader.pages], page_count
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError("CORRUPT_DOCUMENT", "Не удалось прочитать PDF.") from exc


def _image_from_bytes(document: DocumentInput, config: ExtractionConfig) -> Image.Image:
    try:
        with Image.open(io.BytesIO(document.content)) as image:
            expected_format = "PNG" if document.mime_type == "image/png" else "JPEG"
            if image.format != expected_format:
                raise EngineError("CORRUPT_DOCUMENT", "Формат изображения не совпадает с типом файла.")
            if image.width * image.height > config.max_pixels_per_page:
                raise EngineError("RESOURCE_LIMIT", "Изображение превышает предел пикселей.")
            image.load()
            return ImageOps.exif_transpose(image).convert("RGB")
    except EngineError:
        raise
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise EngineError("CORRUPT_DOCUMENT", "Не удалось прочитать изображение.") from exc


def _pdf_images(content: bytes, config: ExtractionConfig):
    try:
        with pypdfium2.PdfDocument(content) as pdf:
            for page in pdf:
                width, height = page.get_size()
                scale = 150 / 72
                if int(width * scale) * int(height * scale) > config.max_pixels_per_page:
                    raise EngineError("RESOURCE_LIMIT", "Страница PDF превышает предел пикселей.")
                yield page.render(scale=scale).to_pil().convert("RGB")
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError("CORRUPT_DOCUMENT", "Не удалось подготовить страницу PDF для OCR.") from exc


def _ocr(image: Image.Image, config: ExtractionConfig, remaining_seconds: float) -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise EngineError("INTERNAL_ENGINE_ERROR", "OCR недоступен: требуется Tesseract 5 с языками rus и eng.")
    workspace = Path(config.workspace)
    if not workspace.is_dir():
        raise EngineError("INTERNAL_ENGINE_ERROR", "Рабочий каталог OCR недоступен.")
    if remaining_seconds <= 0:
        raise EngineError("OCR_TIMEOUT", "Превышено время распознавания.", retryable=False)
    with tempfile.TemporaryDirectory(prefix="housing-ocr-", dir=workspace) as directory:
        image_path = Path(directory) / "page.png"
        image.save(image_path, format="PNG")
        try:
            process = subprocess.run(
                [executable, str(image_path), "stdout", "-l", "rus+eng", "--psm", "6"],
                cwd=directory, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=remaining_seconds, check=False, shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineError("OCR_TIMEOUT", "Превышено время распознавания.", retryable=False) from exc
        except OSError as exc:
            raise EngineError("INTERNAL_ENGINE_ERROR", "Не удалось запустить OCR.") from exc
    if process.returncode != 0:
        raise EngineError("INTERNAL_ENGINE_ERROR", "OCR завершился ошибкой; проверьте Tesseract и языковые данные.")
    return process.stdout[:100_000]


def _field(lines: list[str], label: str, pattern: str | None = None) -> tuple[str | None, str | None]:
    expression = re.compile(rf"^{re.escape(label)}:\s*(.*?)\s*$", re.I)
    for line in lines:
        match = expression.fullmatch(line.strip())
        if match:
            value = match.group(1).strip()
            if value and (pattern is None or re.fullmatch(pattern, value)):
                return value, line[:500]
    return None, None


def _parse(text: str, receipt_id, source: str) -> ExtractionResult:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    upper = text.upper()
    has_table_header = any(all(word in line.upper() for word in ("SERVICE", "QTY", "TARIFF", "CHARGE")) for line in lines)
    if "DEMO-BILL-V1" not in upper or not has_table_header:
        return _manual("TEMPLATE_UNKNOWN", "Учебный макет не распознан; проверьте квитанцию вручную.")
    evidence: list[FieldEvidence] = []

    def add(path: str, original: str | None, *, default: bool = False) -> None:
        if original is not None or default:
            evidence.append(FieldEvidence(
                path=path, source="template_default" if default else source,
                page_number=None if default else 1, bbox=None,
                source_text=None if default else original,
                needs_review=source == "ocr" and not default,
                reason="Подтвердите распознанное значение." if source == "ocr" and not default else None,
            ))

    period, period_line = _field(lines, "PERIOD", r"[0-9]{4}-(?:0[1-9]|1[0-2])")
    issuer, issuer_line = _field(lines, "ISSUER")
    account, account_line = _field(lines, "ACCOUNT")
    address, address_line = _field(lines, "ADDRESS")
    for path, line in (("/period", period_line), ("/issuer_name", issuer_line), ("/account_number", account_line), ("/address_text", address_line)):
        add(path, line)
    row = next(((match, line) for line in lines if (match := ROW_RE.fullmatch(line))), None)
    services = []
    if row is not None:
        match, row_text = row
        line_id = uuid5(receipt_id, "demo-bill-v1:service:0")
        services.append({
            "line_id": line_id, "raw_name": "Cold water (m3)", "service_code": "cold_water",
            "scope": "individual", "unit": "m3", "unit_label": None,
            "quantity": match.group(1), "tariff": match.group(2),
            "charge_amount": match.group(3), "supplier_key": "demo-provider",
            "segment_key": None, "calculation_kind": "simple_product",
        })
        for name in ("raw_name", "service_code", "unit", "quantity", "tariff", "charge_amount", "calculation_kind"):
            add(f"/services/0/{name}", row_text)
        for name in ("scope", "supplier_key"):
            add(f"/services/0/{name}", None, default=True)
    values = {}
    for key, label in (
        ("opening_balance", "OPENING BALANCE"), ("payments_credited", "PAYMENTS CREDITED"),
        ("penalties", "PENALTIES"), ("other_account_changes", "OTHER ACCOUNT CHANGES"),
        ("document_closing_balance", "CLOSING BALANCE"),
    ):
        values[key], original = _field(lines, label, AMOUNT)
        add(f"/settlement/{key}", original)
    current, current_line = _field(lines, "CURRENT CHARGES", AMOUNT)
    total, total_line = _field(lines, "TOTAL DUE", AMOUNT)
    add("/document_current_charges", current_line)
    add("/document_total_due", total_line)
    add("/currency", None, default=True)
    add("/provider_id", None, default=True)
    add("/template_id", None, default=True)
    add("/template_version", None, default=True)
    add("/settlement/formula_kind", None, default=True)
    bill = BillData(
        schema_version="1.0", period=period, currency="RUB", issuer_name=issuer,
        provider_id="demo-provider", account_number=account, address_text=address,
        template_id=TEMPLATE_ID, template_version="1.0", services=services,
        adjustments=[], settlement={"formula_kind": "signed_balance_v1", **values},
        document_current_charges=current, document_total_due=total,
    )
    validation = validate_bill(bill)
    issues = validation.errors + validation.warnings
    outcome = "recognized" if validation.can_confirm and validation.reconciliation_status == "matched" and not issues else ("partial" if period or services else "manual_required")
    if source == "ocr":
        issues.append(Issue(code="OCR_REVIEW_REQUIRED", severity="warning", path=None, message="Проверьте все распознанные значения перед подтверждением."))
    return ExtractionResult(
        outcome=outcome, bill_data=bill, field_evidence=evidence, issues=issues,
        template_id=TEMPLATE_ID, engine_version=ENGINE_VERSION,
    )


def extract_receipt(document: DocumentInput, config: ExtractionConfig) -> ExtractionResult:
    _check_document(document)
    if TEMPLATE_ID not in config.enabled_templates:
        return _manual("TEMPLATE_DISABLED", "Поддерживаемый макет не включён; используйте ручной ввод.")
    start = time.monotonic()
    if document.mime_type == "application/pdf":
        pages, _ = _pdf_text(document, config)
        text = "\n".join(pages)
        useful = "DEMO-BILL-V1" in text.upper() and any("SERVICE" in line.upper() and "QTY" in line.upper() for line in text.splitlines()) and any(char.isdigit() for char in text)
        if useful:
            return _parse(text, document.receipt_id, "pdf_text")
        meaningful_lines = [line for line in text.splitlines() if any(ch.isalpha() for ch in line) and any(ch.isdigit() for ch in line)]
        if len(text.strip()) >= 50 and len(meaningful_lines) >= 3:
            return _manual("TEMPLATE_UNKNOWN", "Текстовый PDF не соответствует учебному макету; используйте ручной ввод.")
        recognized = []
        for image in _pdf_images(document.content, config):
            recognized.append(_ocr(image, config, config.timeout_seconds - (time.monotonic() - start)))
        return _parse("\n".join(recognized), document.receipt_id, "ocr")
    image = _image_from_bytes(document, config)
    text = _ocr(image, config, config.timeout_seconds - (time.monotonic() - start))
    return _parse(text, document.receipt_id, "ocr")
