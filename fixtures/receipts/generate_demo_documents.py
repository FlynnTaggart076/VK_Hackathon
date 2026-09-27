"""Regenerate deterministic synthetic PDF and raster of the same layout."""

import hashlib
import json
from pathlib import Path

import pypdfium2
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
PDF = HERE / "demo-bill-2026-08.pdf"
PNG = HERE / "demo-bill-2026-08.png"
SCAN_PDF = HERE / "demo-bill-2026-08-scan.pdf"
SEPTEMBER_PDF = HERE / "demo-bill-2026-09.pdf"
MANIFEST = HERE / "manifest.json"


def write_pdf(path: Path, lines: list[str]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1, pageCompression=0)
    pdf.setTitle("Synthetic demo bill v1")
    pdf.setAuthor("VK Hackathon synthetic fixture")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 790, "DEMO-BILL-V1")
    pdf.setFont("Helvetica", 12)
    for index, line in enumerate(lines):
        pdf.drawString(50, 755 - index * 36, line)
    pdf.save()


def rasterize(pdf_path: Path, image_path: Path) -> None:
    with pypdfium2.PdfDocument(pdf_path.read_bytes()) as document:
        image = document[0].render(scale=2).to_pil().convert("RGB")
        if image_path.suffix == ".jpg":
            image.save(image_path, format="JPEG", quality=95, subsampling=0)
        else:
            image.save(image_path, format="PNG", optimize=False)


def main() -> None:
    pdf = canvas.Canvas(str(PDF), pagesize=(595, 842), invariant=1, pageCompression=0)
    pdf.setTitle("Synthetic demo bill v1")
    pdf.setAuthor("VK Hackathon synthetic fixture")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 790, "DEMO-BILL-V1")
    pdf.setFont("Helvetica", 12)
    lines = [
        "PERIOD: 2026-08",
        "ISSUER: Demo Housing Organization",
        "ACCOUNT: 000123",
        "ADDRESS: Demo City, Example Street 1, Flat 1",
        "SERVICE | QTY | TARIFF | CHARGE",
        "Cold water (m3) | 5.000000 | 40.000000 | 200.00",
        "CURRENT CHARGES: 200.00",
        "OPENING BALANCE: 0.00",
        "PAYMENTS CREDITED: 0.00",
        "PENALTIES: 0.00",
        "OTHER ACCOUNT CHANGES: 0.00",
        "CLOSING BALANCE: 200.00",
        "TOTAL DUE: 200.00",
    ]
    for index, line in enumerate(lines):
        pdf.drawString(50, 755 - index * 36, line)
    pdf.save()
    september = canvas.Canvas(str(SEPTEMBER_PDF), pagesize=(595, 842), invariant=1, pageCompression=0)
    september.setTitle("Synthetic demo bill v1")
    september.setAuthor("VK Hackathon synthetic fixture")
    september.setFont("Helvetica-Bold", 16)
    september.drawString(50, 790, "DEMO-BILL-V1")
    september.setFont("Helvetica", 12)
    september_lines = [line.replace("2026-08", "2026-09").replace("5.000000 | 40.000000 | 200.00", "6.000000 | 45.000000 | 270.00").replace(": 200.00", ": 270.00") for line in lines]
    for index, line in enumerate(september_lines):
        september.drawString(50, 755 - index * 36, line)
    september.save()
    variants = {
        "adjustment": [line.replace("CURRENT CHARGES: 270.00", "ADJUSTMENT | -50.00 | 2026-08\nCURRENT CHARGES: 220.00").replace("CLOSING BALANCE: 270.00", "CLOSING BALANCE: 220.00").replace("TOTAL DUE: 270.00", "TOTAL DUE: 220.00") for line in september_lines],
        "debt-payment": [line.replace("OPENING BALANCE: 0.00", "OPENING BALANCE: 100.00").replace("PAYMENTS CREDITED: 0.00", "PAYMENTS CREDITED: 80.00").replace("CLOSING BALANCE: 270.00", "CLOSING BALANCE: 290.00").replace("TOTAL DUE: 270.00", "TOTAL DUE: 290.00") for line in september_lines],
        "credit": [line.replace("OPENING BALANCE: 0.00", "OPENING BALANCE: -300.00").replace("CLOSING BALANCE: 270.00", "CLOSING BALANCE: -30.00").replace("TOTAL DUE: 270.00", "TOTAL DUE: 0.00") for line in september_lines],
        "unknown-service": [line.replace("Cold water (m3)", "Mystery service (m3)") for line in september_lines],
    }
    variants["adjustment"] = [part for line in variants["adjustment"] for part in line.split("\n")]
    generated = []
    for kind, variant_lines in variants.items():
        path = HERE / f"demo-bill-2026-09-{kind}.pdf"
        image_path = HERE / f"demo-bill-2026-09-{kind}{'.jpg' if kind in ('debt-payment', 'unknown-service') else '.png'}"
        write_pdf(path, variant_lines)
        rasterize(path, image_path)
        expected_due = {"adjustment": "220.00", "debt-payment": "290.00", "credit": "0.00", "unknown-service": "270.00"}[kind]
        generated.extend(((path.name, "application/pdf", "text_pdf", "2026-09", expected_due, f"Generated synthetic {kind} DEMO-BILL-V1 layout"), (image_path.name, "image/jpeg" if image_path.suffix == ".jpg" else "image/png", "raster_of_text_pdf", "2026-09", expected_due, f"Rendered synthetic {kind} text PDF by pypdfium2")))
    september_jpeg = HERE / "demo-bill-2026-09.jpg"
    rasterize(SEPTEMBER_PDF, september_jpeg)
    unreadable = HERE / "demo-bill-unreadable.png"
    from PIL import Image
    Image.new("RGB", (1000, 1400), "white").save(unreadable, format="PNG", optimize=False)
    cropped = HERE / "demo-bill-cropped.pdf"
    write_pdf(cropped, september_lines[:6])
    mismatch = HERE / "demo-bill-2026-09-mismatch.pdf"
    write_pdf(mismatch, [line.replace("TOTAL DUE: 270.00", "TOTAL DUE: 271.00") for line in september_lines])
    unknown = HERE / "unknown-layout.pdf"
    write_pdf(unknown, ["OTHER DOCUMENT", "PERIOD: 2026-09", "AMOUNT: 270.00"])
    corrupt = HERE / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-not-a-document")
    with pypdfium2.PdfDocument(PDF.read_bytes()) as document:
        image = document[0].render(scale=2).to_pil()
        image.save(PNG, format="PNG", optimize=False)
        scan = canvas.Canvas(str(SCAN_PDF), pagesize=(595, 842), invariant=1, pageCompression=0)
        scan.setTitle("Synthetic image-only demo bill v1")
        scan.drawImage(ImageReader(image.convert("RGB")), 0, 0, width=595, height=842)
        scan.save()
    samples = []
    for name, media_type, representation, period, charge, origin in (
        (PDF.name, "application/pdf", "text_pdf", "2026-08", "200.00", "Generated by generate_demo_documents.py from the English DEMO-BILL-V1 test layout"),
        (SEPTEMBER_PDF.name, "application/pdf", "text_pdf", "2026-09", "270.00", "Generated by generate_demo_documents.py from the English DEMO-BILL-V1 test layout with synthetic quantity and tariff changes"),
        (september_jpeg.name, "image/jpeg", "raster_of_text_pdf", "2026-09", "270.00", "Rendered from synthetic September text PDF by pypdfium2"),
        *generated,
        (PNG.name, "image/png", "raster_of_text_pdf", "2026-08", "200.00", "Rendered from demo-bill-2026-08.pdf by pypdfium2; synthetic scan, not a phone photo"),
        (SCAN_PDF.name, "application/pdf", "image_only_pdf", "2026-08", "200.00", "Image-only PDF made from the synthetic raster; no text layer"),
        (unreadable.name, "image/png", "unreadable_raster", None, None, "Generated blank synthetic page for manual_required control"),
        (cropped.name, "application/pdf", "cropped_text_pdf", "2026-09", None, "Generated synthetic template header and service without totals"),
        (mismatch.name, "application/pdf", "text_pdf", "2026-09", "270.00", "Generated synthetic September document with printed total 271.00 versus calculated 270.00"),
        (unknown.name, "application/pdf", "unknown_layout", None, None, "Generated synthetic unrelated text document"),
        (corrupt.name, "application/pdf", "corrupt_pdf", None, None, "Generated invalid PDF signature for error control"),
        ("water-2026-08.json", "application/json", "canonical_bill_data", "2026-08", "200.00", "TECHNICAL_SPEC.md section 7.7 canonical BillData"),
        ("water-2026-09.json", "application/json", "canonical_bill_data", "2026-09", "270.00", "TECHNICAL_SPEC.md section 7.7 September modification"),
        ("water-comparison.json", "application/json", "expected_comparison", None, None, "TECHNICAL_SPEC.md sections 7.7 and 9.7 mathematical expectation"),
    ):
        data = (HERE / name).read_bytes()
        samples.append({
            "file": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "media_type": media_type, "representation": representation,
            "template_id": "demo-bill-v1" if representation in ("text_pdf", "raster_of_text_pdf", "image_only_pdf", "cropped_text_pdf") else None,
            "expected_fields": ({"period": period, **({"charge_amount": charge} if charge is not None else {})} if period else ({
                "delta_current_charges": "70.00", "quantity_effect": "40.00", "tariff_effect": "30.00"
            } if name == "water-comparison.json" else {})),
            "origin": origin, "is_synthetic": True,
        })
    MANIFEST.write_text(json.dumps({"schema_version": "1.0", "samples": samples}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
