"""Freeze synthetic DEMO-BILL-V1 documents and gold without calling the engine."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pypdfium2
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
EXISTING = HERE.parent
VALUES = (
    ("2026-01", 3, 32, "96.00", "text_pdf"),
    ("2026-02", 4, 33, "132.00", "text_pdf"),
    ("2026-03", 5, 34, "170.00", "text_pdf"),
    ("2026-04", 6, 35, "210.00", "png"),
    ("2026-05", 7, 36, "252.00", "png"),
    ("2026-06", 8, 37, "296.00", "png"),
    ("2026-07", 9, 38, "342.00", "jpeg"),
    ("2026-08", 10, 39, "390.00", "jpeg"),
    ("2026-09", 11, 40, "440.00", "jpeg"),
    ("2026-10", 12, 41, "492.00", "image_only_pdf"),
    ("2026-11", 13, 42, "546.00", "image_only_pdf"),
    ("2026-12", 14, 43, "602.00", "image_only_pdf"),
)
EDGE_FILES = (
    ("demo-bill-cropped.pdf", "partial", {"/period": "2026-09", "/document_total_due": None}),
    ("demo-bill-unreadable.png", "manual_required", {}),
    ("unknown-layout.pdf", "manual_required", {}),
    ("corrupt.pdf", "error:CORRUPT_DOCUMENT", {}),
    ("demo-bill-2026-09-adjustment.png", "recognized", {
        "/adjustments/0/amount": "-50.00", "/document_current_charges": "220.00", "/document_total_due": "220.00"}),
    ("demo-bill-2026-09-debt-payment.jpg", "recognized", {
        "/settlement/opening_balance": "100.00", "/settlement/payments_credited": "80.00", "/document_total_due": "290.00"}),
    ("demo-bill-2026-09-credit.png", "recognized", {
        "/settlement/opening_balance": "-300.00", "/settlement/document_closing_balance": "-30.00", "/document_total_due": "0.00"}),
    ("demo-bill-2026-09-unknown-service.jpg", "partial", {
        "/services/0/service_code": "other", "/document_total_due": "270.00"}),
)


def pdf_bytes(period: str, quantity: int, tariff: int, charge: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=(595, 842), invariant=1, pageCompression=0)
    page.setTitle("Synthetic E4 demo bill")
    page.setAuthor("VK Hackathon synthetic fixture")
    page.setFont("Helvetica-Bold", 16)
    page.drawString(50, 790, "DEMO-BILL-V1")
    page.setFont("Helvetica", 12)
    lines = (
        f"PERIOD: {period}",
        "ISSUER: Demo Housing Organization",
        "ACCOUNT: 000123",
        "ADDRESS: Demo City, Example Street 1, Flat 1",
        "SERVICE | QTY | TARIFF | CHARGE",
        f"Cold water (m3) | {quantity}.000000 | {tariff}.000000 | {charge}",
        f"CURRENT CHARGES: {charge}",
        "OPENING BALANCE: 0.00",
        "PAYMENTS CREDITED: 0.00",
        "PENALTIES: 0.00",
        "OTHER ACCOUNT CHANGES: 0.00",
        f"CLOSING BALANCE: {charge}",
        f"TOTAL DUE: {charge}",
    )
    for index, line in enumerate(lines):
        page.drawString(50, 755 - index * 36, line)
    page.save()
    return buffer.getvalue()


def render_bytes(source: bytes, representation: str) -> bytes:
    with pypdfium2.PdfDocument(source) as document:
        image = document[0].render(scale=2).to_pil().convert("RGB")
    if representation == "image_only_pdf":
        buffer = io.BytesIO()
        page = canvas.Canvas(buffer, pagesize=(595, 842), invariant=1, pageCompression=0)
        page.setTitle("Synthetic E4 image-only scan")
        page.setAuthor("VK Hackathon synthetic fixture")
        page.drawImage(ImageReader(image), 0, 0, width=595, height=842)
        page.save()
        return buffer.getvalue()
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG" if representation == "jpeg" else "PNG",
               quality=95, subsampling=0, optimize=False)
    return buffer.getvalue()


def record(name: str, data: bytes, representation: str, media_type: str) -> dict:
    return {
        "file": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "representation": representation,
        "media_type": media_type,
        "template_id": "demo-bill-v1" if representation in ("text_pdf", "png", "jpeg", "image_only_pdf") else None,
        "is_synthetic": True,
    }


def main() -> None:
    clean = []
    for index, (period, quantity, tariff, charge, representation) in enumerate(VALUES, start=1):
        source = pdf_bytes(period, quantity, tariff, charge)
        data = source if representation == "text_pdf" else render_bytes(source, representation)
        extension = ".jpg" if representation == "jpeg" else (".png" if representation == "png" else ".pdf")
        name = f"clean-{index:02d}{extension}"
        (HERE / name).write_bytes(data)
        media_type = "image/jpeg" if representation == "jpeg" else ("image/png" if representation == "png" else "application/pdf")
        clean.append({
            **record(name, data, representation, media_type),
            "case_id": f"C{index:02d}",
            "critical_fields": {
                "/period": period,
                "/services/count": 1,
                "/services/0/raw_name": "Cold water (m3)",
                "/services/0/charge_amount": charge,
                "/document_current_charges": charge,
                "/settlement/opening_balance": "0.00",
                "/settlement/payments_credited": "0.00",
                "/settlement/penalties": "0.00",
                "/settlement/other_account_changes": "0.00",
                "/settlement/document_closing_balance": charge,
                "/document_total_due": charge,
            },
        })
    edges = []
    for name, outcome, expected_fields in EDGE_FILES:
        data = (EXISTING / name).read_bytes()
        media_type = "image/jpeg" if name.endswith(".jpg") else ("image/png" if name.endswith(".png") else "application/pdf")
        edges.append({
            **record(f"../{name}", data, "existing_synthetic_edge", media_type),
            "template_id": "demo-bill-v1" if name.startswith("demo-bill-") and name != "demo-bill-unreadable.png" else None,
            "expected_outcome": outcome,
            "expected_fields": expected_fields,
        })
    gold = {
        "schema_version": "1.0",
        "provenance": "Generator-defined numeric and printed-field gold for the English DEMO-BILL-V1 educational layout; created before any E4 engine evaluation",
        "created_at": "2026-09-27",
        "scoring": {
            "population": "clean only; each path in critical_fields is a separate critical field",
            "critical_fields_per_document": 11,
            "document_count": len(clean),
            "denominator": sum(len(item["critical_fields"]) for item in clean),
            "errors_in_denominator": True,
            "ocr_representations": ["png", "jpeg", "image_only_pdf"],
            "pdf_text_reported_separately": True,
        },
        "clean": clean,
        "edge_controls": edges,
    }
    (HERE / "gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
