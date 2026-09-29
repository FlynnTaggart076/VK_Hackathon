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
from .epd import EPD_TEMPLATE_ID, is_epd, parse_epd_text
from .errors import EngineError
from .receipts import validate_bill


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ENGINE_VERSION = "0.1.0"
TEMPLATE_ID = "demo-bill-v1"
AMOUNT = r"-?(?:0|[1-9][0-9]{0,8})\.[0-9]{2}"
DECIMAL = r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?"
ROW_RE = re.compile(rf"^(?P<name>[A-Za-z][A-Za-z0-9 ()/_-]*?)\s*\|\s*(?P<quantity>{DECIMAL})\s*\|\s*(?P<tariff>{DECIMAL})\s*\|\s*(?P<charge>{AMOUNT})\s*$", re.I)
ADJUSTMENT_RE = re.compile(rf"^ADJUSTMENT\s*\|\s*(?P<amount>{AMOUNT})(?:\s*\|\s*(?P<period>[0-9]{{4}}-(?:0[1-9]|1[0-2])))?\s*$", re.I)


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


def _page_positions(content: bytes, pages: list[str]) -> dict[str, tuple[int, tuple[float, float, float, float] | None]]:
    """Locate exact text lines. Missing positions remain null, never estimated."""
    positions: dict[str, tuple[int, tuple[float, float, float, float] | None]] = {}
    try:
        with pypdfium2.PdfDocument(content) as pdf:
            for page_index, text in enumerate(pages):
                page = pdf[page_index]
                width, height = page.get_size()
                text_page = page.get_textpage()
                for line in text.splitlines():
                    key = line.strip()
                    if not key or key in positions:
                        continue
                    bbox = None
                    searcher = text_page.search(key)
                    found = searcher.get_next()
                    if found is not None:
                        start, count = found
                        boxes = [text_page.get_charbox(char_index) for char_index in range(start, start + count)]
                        boxes = [box for box in boxes if box[2] > box[0] and box[3] > box[1]]
                        if boxes:
                            left = min(box[0] for box in boxes)
                            bottom = min(box[1] for box in boxes)
                            right = max(box[2] for box in boxes)
                            top = max(box[3] for box in boxes)
                            bbox = (max(0.0, left / width), max(0.0, 1 - top / height), min(1.0, right / width), min(1.0, 1 - bottom / height))
                    positions[key] = (page_index + 1, bbox)
    except Exception:
        return {line.strip(): (index + 1, None) for index, text in enumerate(pages) for line in text.splitlines() if line.strip()}
    return positions


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


def _parse(text: str, receipt_id, source: str, positions: dict[str, tuple[int, tuple[float, float, float, float] | None]] | None = None) -> ExtractionResult:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    upper = text.upper()
    has_table_header = any(all(word in line.upper() for word in ("SERVICE", "QTY", "TARIFF", "CHARGE")) for line in lines)
    if "DEMO-BILL-V1" not in upper or not has_table_header:
        return _manual("TEMPLATE_UNKNOWN", "Учебный макет не распознан; проверьте квитанцию вручную.")
    evidence: list[FieldEvidence] = []

    def add(path: str, original: str | None, *, default: bool = False, review: bool = False) -> None:
        if original is not None or default:
            location = (positions or {}).get(original.strip(), (1, None)) if original is not None else (None, None)
            evidence.append(FieldEvidence(
                path=path, source="template_default" if default else source,
                page_number=None if default else location[0], bbox=None if default else location[1],
                source_text=None if default else original,
                needs_review=(source == "ocr" or review) and not default,
                reason="Подтвердите распознанное значение или классификацию." if (source == "ocr" or review) and not default else None,
            ))

    period, period_line = _field(lines, "PERIOD", r"[0-9]{4}-(?:0[1-9]|1[0-2])")
    issuer, issuer_line = _field(lines, "ISSUER")
    account, account_line = _field(lines, "ACCOUNT")
    address, address_line = _field(lines, "ADDRESS")
    for path, line in (("/period", period_line), ("/issuer_name", issuer_line), ("/account_number", account_line), ("/address_text", address_line)):
        add(path, line)
    services = []
    parser_issues: list[Issue] = []
    for row_text in lines:
        match = ROW_RE.fullmatch(row_text)
        if match is None:
            continue
        index = len(services)
        line_id = uuid5(receipt_id, f"demo-bill-v1:service:{index}")
        raw_name = match.group("name").strip()
        unit_match = re.search(r"\(([A-Za-z0-9]+)\)$", raw_name)
        unit_label = unit_match.group(1) if unit_match else None
        known = raw_name.casefold() == "cold water (m3)"
        if not known:
            parser_issues.append(Issue(code="SERVICE_UNMAPPED", severity="warning", path=f"/services/{index}/service_code", message="Название услуги не опознано и сохранено как «Прочее»; выберите вид услуги вручную."))
        services.append({
            "line_id": line_id, "raw_name": raw_name, "service_code": "cold_water" if known else "other",
            "scope": "individual" if known else "unspecified", "unit": "m3" if unit_label == "m3" else ("other" if unit_label else None), "unit_label": None if unit_label == "m3" else unit_label,
            "quantity": match.group("quantity"), "tariff": match.group("tariff"),
            "charge_amount": match.group("charge"), "supplier_key": "demo-provider",
            "segment_key": None, "calculation_kind": "simple_product",
        })
        for name in ("raw_name", "service_code", "unit", "quantity", "tariff", "charge_amount", "calculation_kind"):
            add(f"/services/{index}/{name}", row_text, review=name == "service_code" and not known)
        for name in ("scope", "supplier_key"):
            add(f"/services/{index}/{name}", None, default=True)
    adjustments = []
    for line in lines:
        match = ADJUSTMENT_RE.fullmatch(line)
        if match is None:
            continue
        index = len(adjustments)
        adjustments.append({
            "adjustment_id": uuid5(receipt_id, f"demo-bill-v1:adjustment:{index}"),
            "label": "Перерасчёт", "amount": match.group("amount"),
            "service_line_id": services[0]["line_id"] if services else None,
            "related_period": match.group("period"),
        })
        add(f"/adjustments/{index}/amount", line)
        if match.group("period") is not None:
            add(f"/adjustments/{index}/related_period", line)
        add(f"/adjustments/{index}/label", line)
        add(f"/adjustments/{index}/service_line_id", None, default=True)
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
        adjustments=adjustments, settlement={"formula_kind": "signed_balance_v1", **values},
        document_current_charges=current, document_total_due=total,
    )
    validation = validate_bill(bill)
    issues = parser_issues + validation.errors + validation.warnings
    outcome = "recognized" if validation.can_confirm and validation.reconciliation_status == "matched" and not issues else ("partial" if period or services else "manual_required")
    if source == "ocr":
        issues.append(Issue(code="OCR_REVIEW_REQUIRED", severity="warning", path=None, message="Проверьте все распознанные значения перед подтверждением."))
    return ExtractionResult(
        outcome=outcome, bill_data=bill, field_evidence=evidence, issues=issues,
        template_id=TEMPLATE_ID, engine_version=ENGINE_VERSION,
    )


def extract_receipt(document: DocumentInput, config: ExtractionConfig) -> ExtractionResult:
    _check_document(document)
    if not ({TEMPLATE_ID, EPD_TEMPLATE_ID} & set(config.enabled_templates)):
        return _manual("TEMPLATE_DISABLED", "Поддерживаемый макет не включён; используйте ручной ввод.")
    start = time.monotonic()
    if document.mime_type == "application/pdf":
        pages, _ = _pdf_text(document, config)
        text = "\n".join(pages)
        useful = "DEMO-BILL-V1" in text.upper() and any("SERVICE" in line.upper() and "QTY" in line.upper() for line in text.splitlines()) and any(char.isdigit() for char in text)
        if useful and TEMPLATE_ID in config.enabled_templates:
            return _parse(text, document.receipt_id, "pdf_text", _page_positions(document.content, pages))
        if len(pages) == 1 and EPD_TEMPLATE_ID in config.enabled_templates and is_epd(text):
            try:
                layout = PdfReader(io.BytesIO(document.content), strict=False).pages[0].extract_text(extraction_mode="layout") or ""
            except Exception:
                layout = ""
            if is_epd(layout):
                return parse_epd_text(layout, document.receipt_id, engine_version=ENGINE_VERSION)
        meaningful_lines = [line for line in text.splitlines() if any(ch.isalpha() for ch in line) and any(ch.isdigit() for ch in line)]
        if len(text.strip()) >= 50 and len(meaningful_lines) >= 3:
            return _manual("TEMPLATE_UNKNOWN", "Текстовый PDF не соответствует учебному макету; используйте ручной ввод.")
        recognized = []
        positions = {}
        for page_number, image in enumerate(_pdf_images(document.content, config), start=1):
            page_text = _ocr(image, config, config.timeout_seconds - (time.monotonic() - start))
            recognized.append(page_text)
            for line in page_text.splitlines():
                positions.setdefault(line.strip(), (page_number, None))
        return _parse("\n".join(recognized), document.receipt_id, "ocr", positions)
    image = _image_from_bytes(document, config)
    text = _ocr(image, config, config.timeout_seconds - (time.monotonic() - start))
    return _parse(text, document.receipt_id, "ocr")
