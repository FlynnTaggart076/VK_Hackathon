"""Live evaluation of the DeepSeek assistant router on fixtures/assistant/router_cases.json.

Spends real DeepSeek tokens; never runs in CI. Needs DEEPSEEK_API_KEY (and optionally DEEPSEEK_MODEL)
in the environment. Prints only case texts, outcomes and totals — never the key.

    PYTHONPATH="apps/backend;packages/housing_engine/src" python scripts/eval_assistant_router.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from app.services.capabilities import validate_decision
from app.services.deepseek import ModelUnavailable, route

ROOT = Path(__file__).resolve().parents[1]


def outcome(decision: dict | None) -> str:
    if decision is None:
        return "invalid"
    if decision["kind"] != "run":
        return decision["kind"]
    action = decision["action"]
    parts = ["run", action["function"]]
    value = action["params"].get("topic") or action["params"].get("service")
    return ":".join(parts + ([value] if value else []))


def matches(got: str, expected: list[str]) -> bool:
    return any(got == item or got.startswith(item + ":") for item in expected)


def main() -> int:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    cases = json.loads((ROOT / "fixtures/assistant/router_cases.json").read_text(encoding="utf-8"))
    passed, timings = 0, []
    for case in cases:
        state = {"awaiting": None, "pending_question": None, "buttons_shown": [], "topic": None, "service": None,
                 "city": None, "house_known": False, "confirmed_receipt_months": [],
                 "receipt_upload_allowed_here": True}
        started = time.monotonic()
        try:
            raw = route(case["text"], state, case.get("history", []), key, model)
            decision = validate_decision(raw, case["text"])
        except ModelUnavailable:
            raw, decision = None, None
        timings.append(time.monotonic() - started)
        got = outcome(decision)
        ok = matches(got, case["expect"])
        passed += ok
        extra = ""
        if decision and decision["kind"] in {"clarify", "answer", "offtopic"}:
            extra = f" | {decision['text'][:90]}" + (
                f" | {[item['label'] for item in decision['options']]}" if decision["options"] else "")
        print(f"{'OK ' if ok else 'BAD'} {case['text'][:48]:<48} -> {got}{extra}")
    timings.sort()
    print(f"\n{passed}/{len(cases)} matched; median {timings[len(timings) // 2]:.1f}s, "
          f"max {timings[-1]:.1f}s")
    return 0 if passed >= 0.9 * len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
