"""Explicit synthetic upload provenance; matching bytes still go through real OCR."""

import hashlib
import json
from pathlib import Path

from app.errors import ApiError


ROOT = Path(__file__).resolve().parents[4]
ALLOWED_IDS = {"demo-bill-2026-08.pdf", "demo-bill-2026-09.pdf"}


def dataset_kind(content: bytes, mime: str, demo_sample_id: str | None) -> str:
    if demo_sample_id is None:
        return "user_provided"
    if demo_sample_id not in ALLOWED_IDS:
        raise ApiError(422, "VALIDATION_FAILED", "Неизвестный демообразец.")
    manifest = json.loads((ROOT / "fixtures" / "receipts" / "manifest.json").read_text(encoding="utf-8"))
    sample = next((row for row in manifest["samples"] if row["file"] == demo_sample_id), None)
    if not sample or not sample["is_synthetic"] or sample["media_type"] != mime or \
            sample["bytes"] != len(content) or sample["sha256"] != hashlib.sha256(content).hexdigest():
        raise ApiError(422, "VALIDATION_FAILED", "Байты не соответствуют демообразцу.")
    return "synthetic"
