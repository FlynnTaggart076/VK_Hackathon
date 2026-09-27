"""Generate the complete HTTP comparison example from the engine's public API."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.comparison_adapter import compare_json


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "fixtures" / "receipts"
OUTPUT = ROOT / "contracts" / "http" / "examples" / "comparison-complete.json"


def main() -> None:
    snapshots = []
    for index, period in enumerate(("2026-08", "2026-09"), start=1):
        snapshots.append({
            "id": uuid.UUID(f"10000000-0000-4000-8000-{index:012d}"),
            "revision": 3,
            "bill_data": json.loads((INPUT / f"water-{period}.json").read_text(encoding="utf-8")),
            "confirmed_at": datetime(2026, 9, 27, tzinfo=timezone.utc),
            "dataset_kind": "synthetic",
        })
    result = compare_json(snapshots, None, False)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
