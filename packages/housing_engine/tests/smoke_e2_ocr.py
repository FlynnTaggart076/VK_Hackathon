"""Opt-in real Tesseract smoke for the six synthetic raster controls."""

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from housing_engine import DocumentInput, ExtractionConfig, extract_receipt


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "receipts"
CASES = (
    ("demo-bill-2026-08.png", "recognized", "200.00"),
    ("demo-bill-2026-09.jpg", "recognized", "270.00"),
    ("demo-bill-2026-09-adjustment.png", "recognized", "220.00"),
    ("demo-bill-2026-09-debt-payment.jpg", "recognized", "290.00"),
    ("demo-bill-2026-09-credit.png", "recognized", "0.00"),
    ("demo-bill-2026-09-unknown-service.jpg", "partial", "270.00"),
    ("demo-bill-2026-08-scan.pdf", "recognized", "200.00"),
)


def main() -> None:
    executable = shutil.which("tesseract")
    if executable is None:
        raise SystemExit("Tesseract 5 with eng+rus is required for this opt-in smoke")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    languages = subprocess.run([executable, "--list-langs"], capture_output=True, text=True, check=True).stdout
    if not version.startswith(("tesseract 5", "tesseract v5")) or not {"eng", "rus"}.issubset(set(languages.splitlines())):
        raise SystemExit(f"Unsupported Tesseract setup: {version}; languages={languages!r}")
    config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
    for name, expected_outcome, expected_due in CASES:
        payload = (FIXTURES / name).read_bytes()
        mime = "application/pdf" if name.endswith(".pdf") else ("image/jpeg" if name.endswith(".jpg") else "image/png")
        document = DocumentInput(receipt_id=UUID("10000000-0000-4000-8000-000000000001"), content=payload, mime_type=mime, sha256=hashlib.sha256(payload).hexdigest())
        result = extract_receipt(document, config)
        assert (result.outcome, result.bill_data.document_total_due) == (expected_outcome, expected_due), (name, result.outcome, result.bill_data.document_total_due)
        assert all(item.needs_review for item in result.field_evidence if item.source == "ocr")
        assert any(item.code == "OCR_REVIEW_REQUIRED" for item in result.issues)
        print(name, result.outcome, result.bill_data.period, result.bill_data.document_total_due)
    print(f"Synthetic OCR smoke OK: {version}, eng+rus; no real bill quality claim")


if __name__ == "__main__":
    main()
