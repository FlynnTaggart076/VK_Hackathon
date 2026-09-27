"""Score the coordinator's frozen E4 synthetic FAQ set without changing gold."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from housing_engine import answer_question, load_knowledge
from housing_engine.dto import QuestionContext, QuestionRequest


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "fixtures/questions/e4-postfix-holdout.json"
EVAL_NOW = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)


def main() -> int:
    corpus = json.loads(GOLD.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    assert len(cases) == 25
    assert Counter(case["id"][0] for case in cases) == {"S": 15, "A": 3, "U": 7}
    assert len({case["id"] for case in cases}) == len(cases)
    knowledge = load_knowledge(str(ROOT / "knowledge"), EVAL_NOW)
    counts = {group: {"correct": 0, "total": 0} for group in "SAU"}
    failures = []
    for case in cases:
        context = QuestionContext(**corpus["default_context"])
        answer = answer_question(QuestionRequest(question=case["question"], context=context,
                                                 receipt=None, now=EVAL_NOW), knowledge)
        actual = {"topic_id": answer.topic_id, "status": answer.status,
                  "clarification_field": answer.clarification.field if answer.clarification else None}
        expected = case["expected"]
        safe = answer.status != "unsupported" or (not answer.sources and
                not any(action.type == "open_link" for action in answer.actions))
        group = case["id"][0]
        counts[group]["total"] += 1
        if all(actual[key] == value for key, value in expected.items()) and safe:
            counts[group]["correct"] += 1
        else:
            failures.append({"id": case["id"], "expected": expected, "actual": actual,
                             "unsafe_unsupported": not safe})
    for group, count in counts.items():
        print(f"{group}: {count['correct']}/{count['total']}")
    print(f"overall: {sum(value['correct'] for value in counts.values())}/25")
    for failure in failures:
        print(f"FAIL {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
