"""Offline E3 question holdout; gold fixture is independent of engine output."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from housing_engine import EngineError, answer_question, load_knowledge
from housing_engine.dto import QuestionContext, QuestionRequest


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "questions" / "e3-qa-holdout.json"
EVAL_NOW = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
TOPICS = frozenset({
    "first_bill", "bill_terms", "bill_change", "meter_readings", "meter_deadline",
    "account_number", "management_contacts", "supplier_contacts", "payment_history",
    "arrears_or_credit", "adjustment", "request_breakdown", "service_issue",
    "housing_document", "new_resident",
})


def _read_gold() -> dict:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    ids = [case["id"] for case in cases]
    assert corpus["schema_version"] == "1.0"
    assert len(cases) == 75 and len(set(ids)) == 75
    assert Counter(id_[0] for id_ in ids) == {"S": 60, "A": 5, "U": 10}
    assert Counter(case["expected"]["topic_id"] for case in cases if case["id"].startswith("S")) == {topic: 4 for topic in TOPICS}
    assert all(case["expected"]["topic_id"] is None for case in cases if case["id"].startswith(("A", "U")))
    return corpus


def evaluate() -> dict:
    corpus = _read_gold()
    knowledge = load_knowledge(str(ROOT / "knowledge"), EVAL_NOW)
    by_group = {key: {"total": 0, "correct": 0} for key in ("S", "A", "U")}
    errors = []
    unsafe_unsupported = []
    for case in corpus["cases"]:
        context = {**corpus["default_context"], **case.get("context", {})}
        request = QuestionRequest(question=case["question"], context=QuestionContext(**context), receipt=None, now=EVAL_NOW)
        expected = case["expected"]
        try:
            actual_result = answer_question(request, knowledge)
            actual = {
                "topic_id": actual_result.topic_id,
                "status": actual_result.status,
                "clarification_field": actual_result.clarification.field if actual_result.clarification else None,
            }
            if actual_result.status == "unsupported" and (actual_result.sources or any(action.type == "open_link" for action in actual_result.actions)):
                unsafe_unsupported.append(case["id"])
        except EngineError as exc:
            actual = {"error": exc.code}
        group = case["id"][0]
        by_group[group]["total"] += 1
        correct = all(actual.get(key) == value for key, value in expected.items())
        if correct:
            by_group[group]["correct"] += 1
        else:
            errors.append({"id": case["id"], "question": case["question"], "expected": expected, "actual": actual})
    return {
        "corpus": str(CORPUS.relative_to(ROOT)).replace("\\", "/"),
        "eval_at": EVAL_NOW.isoformat(),
        "knowledge_version": knowledge.version,
        "by_group": by_group,
        "overall": {"total": 75, "correct": sum(group["correct"] for group in by_group.values())},
        "unsafe_unsupported": unsafe_unsupported,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, help="Optional path for machine-readable results")
    args = parser.parse_args()
    result = evaluate()
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key, value in result["by_group"].items():
        print(f"{key}: {value['correct']}/{value['total']}")
    print(f"overall: {result['overall']['correct']}/75; unsafe_unsupported: {len(result['unsafe_unsupported'])}")
    for error in result["errors"]:
        print(f"{error['id']}: expected={error['expected']} actual={error['actual']} | {error['question']}")
    return 0 if not result["errors"] and not result["unsafe_unsupported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
