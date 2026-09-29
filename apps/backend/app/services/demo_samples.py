"""Explicit synthetic upload provenance; matching bytes still go through real OCR."""

import hashlib
import json
import os
from pathlib import Path

from app.errors import ApiError


FIXTURES = (Path(os.environ["FIXTURE_ROOT"]) if os.getenv("FIXTURE_ROOT") else
            next(parent / "fixtures" / "receipts" for parent in Path(__file__).resolve().parents
                 if (parent / "fixtures" / "receipts" / "manifest.json").is_file()))
ALLOWED_IDS = {"demo-bill-2026-08.pdf", "demo-bill-2026-09.pdf"}
CITY_PREVIEW_IDS = {
    "city-moscow-water-2026-08", "city-moscow-water-2026-09",
    "city-lyubertsy-water-2026-08", "city-lyubertsy-water-2026-09",
}
DEMO_FIXTURES = {"water-2026-08", "water-2026-09"} | CITY_PREVIEW_IDS


def dataset_kind(content: bytes, mime: str, demo_sample_id: str | None) -> str:
    if demo_sample_id is None:
        return "user_provided"
    if demo_sample_id not in ALLOWED_IDS:
        raise ApiError(422, "VALIDATION_FAILED", "Неизвестный демообразец.")
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    sample = next((row for row in manifest["samples"] if row["file"] == demo_sample_id), None)
    if not sample or not sample["is_synthetic"] or sample["media_type"] != mime or \
            sample["bytes"] != len(content) or sample["sha256"] != hashlib.sha256(content).hexdigest():
        raise ApiError(422, "VALIDATION_FAILED", "Байты не соответствуют демообразцу.")
    return "synthetic"
