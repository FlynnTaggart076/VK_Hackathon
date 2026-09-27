"""Score frozen E4 synthetic OCR gold from document bytes, including failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from uuid import UUID

from housing_engine import EngineError, extract_receipt
from housing_engine.dto import DocumentInput, ExtractionConfig


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "fixtures" / "receipts" / "e4-holdout" / "gold.json"
OCR_KINDS = {"png", "jpeg", "image_only_pdf"}


def value_at(bill, path: str):
    current = bill
    for part in path.strip("/").split("/"):
        if part == "count":
            current = len(current)
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            current = getattr(current, part)
    return current


def run() -> dict:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    clean = gold["clean"]
    assert gold["scoring"]["denominator"] == sum(len(case["critical_fields"]) for case in clean)
    assert len(clean) == gold["scoring"]["document_count"] == 12
    assert all(len(case["critical_fields"]) == 11 for case in clean)
    config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
    result = {
        "gold_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        "groups": {name: {"correct": 0, "total": 0} for name in ("ocr", "pdf_text", "all_clean")},
        "outcomes": Counter(), "errors": [], "edge_results": [],
    }

    def extract(case: dict, index: int):
        path = GOLD.parent / case["file"]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == case["sha256"]
        assert len(data) == case["bytes"]
        document = DocumentInput(
            receipt_id=UUID(f"70000000-0000-4000-8000-{index:012d}"),
            content=data, mime_type=case["media_type"], sha256=case["sha256"],
        )
        return extract_receipt(document, config)

    for index, case in enumerate(clean, start=1):
        group = "ocr" if case["representation"] in OCR_KINDS else "pdf_text"
        expected = case["critical_fields"]
        try:
            extracted = extract(case, index)
            result["outcomes"][extracted.outcome] += 1
            if extracted.outcome != "recognized":
                result["errors"].append({"case": case["case_id"], "kind": "clean_outcome",
                                         "expected": "recognized", "actual": extracted.outcome})
            actual = {path: value_at(extracted.bill_data, path) for path in expected}
            source = "ocr" if group == "ocr" else "pdf_text"
            evidence = {item.path: item for item in extracted.field_evidence}
            for field_path in expected:
                if field_path.endswith("/count"):
                    continue
                field_evidence = evidence.get(field_path)
                if field_evidence is None or field_evidence.source != source or (group == "ocr" and not field_evidence.needs_review):
                    result["errors"].append({
                        "case": case["case_id"], "kind": "source_evidence", "path": field_path,
                        "expected": source, "actual": field_evidence.source if field_evidence else None,
                        "needs_review": field_evidence.needs_review if field_evidence else None,
                    })
            if group == "ocr" and not any(issue.code == "OCR_REVIEW_REQUIRED" for issue in extracted.issues):
                result["errors"].append({"case": case["case_id"], "kind": "missing_ocr_review"})
        except (EngineError, AttributeError, IndexError, ValueError) as exc:
            actual = {}
            result["outcomes"][f"error:{exc.code}" if isinstance(exc, EngineError) else "harness_error"] += 1
            result["errors"].append({"case": case["case_id"], "kind": "extraction_error", "code": getattr(exc, "code", type(exc).__name__)})
        for path, wanted in expected.items():
            got = actual.get(path)
            for category in (group, "all_clean"):
                result["groups"][category]["total"] += 1
                if got == wanted:
                    result["groups"][category]["correct"] += 1
            if got != wanted:
                result["errors"].append({"case": case["case_id"], "kind": "critical_field", "path": path,
                                         "expected": wanted, "actual": got})

    for index, case in enumerate(gold["edge_controls"], start=101):
        try:
            extracted = extract(case, index)
            outcome = extracted.outcome
            fields = {path: value_at(extracted.bill_data, path) for path in case["expected_fields"]}
            issue_codes = [item.code for item in extracted.issues]
        except EngineError as exc:
            outcome = f"error:{exc.code}"
            fields = {}
            issue_codes = []
        good = outcome == case["expected_outcome"] and fields == case["expected_fields"]
        result["edge_results"].append({"file": case["file"], "passed": good, "expected_outcome": case["expected_outcome"],
                                       "actual_outcome": outcome, "expected_fields": case["expected_fields"],
                                       "actual_fields": fields, "issue_codes": issue_codes})
    result["outcomes"] = dict(result["outcomes"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    result = run()
    if args.json_out:
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, score in result["groups"].items():
        print(f"{name}: {score['correct']}/{score['total']} ({100 * score['correct'] / score['total']:.2f}%)")
    print(f"edge controls: {sum(item['passed'] for item in result['edge_results'])}/{len(result['edge_results'])}")
    print(f"outcomes: {result['outcomes']}")
    for error in result["errors"]:
        print(f"ERROR {error}")
    for edge in result["edge_results"]:
        if not edge["passed"]:
            print(f"EDGE ERROR {edge}")
    return 0 if not result["errors"] and all(item["passed"] for item in result["edge_results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
