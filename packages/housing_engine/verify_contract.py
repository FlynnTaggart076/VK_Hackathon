"""Offline DTO/schema/fixture check. Run from repository root."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "housing_engine" / "src"))
from housing_engine import dto  # noqa: E402


MODELS = {
    name: getattr(dto, name)
    for name in (
        "BillData", "FieldEvidence", "Issue", "DocumentInput", "ExtractionConfig",
        "ExtractionResult", "ValidationResult", "ExplainRequest", "ReceiptExplanation",
        "CompareRequest", "ComparisonResult", "QuestionRequest", "AnswerResult",
        "DraftRequest", "DraftResult", "KnowledgeBundle",
    )
}
SCHEMAS = ROOT / "contracts" / "engine" / "v1"
FIXTURES = ROOT / "fixtures" / "receipts"


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def current_charges(bill: dict) -> Decimal:
    return sum((Decimal(line["charge_amount"]) for line in bill["services"]), Decimal(0)) + sum(
        (Decimal(item["amount"]) for item in bill["adjustments"]), Decimal(0)
    )


def verify() -> None:
    for name, model in MODELS.items():
        schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        if schema != model.model_json_schema(mode="validation"):
            raise AssertionError(f"Stale JSON Schema: {name}")

    comparison = json.loads((FIXTURES / "water-comparison.json").read_text(encoding="utf-8"))
    comparison_schema = json.loads((SCHEMAS / "water-comparison.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(comparison_schema)
    Draft202012Validator(comparison_schema).validate(comparison)
    assert comparison["schema_version"] == "1.0"
    bills = []
    for key in ("older_fixture", "newer_fixture"):
        name = comparison[key]
        if Path(name).name != name:
            raise AssertionError("Fixture path must be a basename")
        data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        Draft202012Validator(MODELS["BillData"].model_json_schema(mode="validation")).validate(data)
        MODELS["BillData"].model_validate_json(json.dumps(data))
        bills.append(data)
    old, new = bills
    expected = comparison["expected"]
    old_charges, new_charges = map(current_charges, bills)
    old_line, new_line = old["services"][0], new["services"][0]
    if len(old["services"]) != 1 or len(new["services"]) != 1:
        raise AssertionError("Reference pair must contain one service each")
    q_old, q_new = Decimal(old_line["quantity"]), Decimal(new_line["quantity"])
    t_old, t_new = Decimal(old_line["tariff"]), Decimal(new_line["tariff"])
    delta = new_charges - old_charges
    quantity_effect = Decimal(money((q_new - q_old) * t_old))
    tariff_effect = Decimal(money(q_new * (t_new - t_old)))
    actual = {
        "older_current_charges": money(old_charges),
        "newer_current_charges": money(new_charges),
        "delta_current_charges": money(delta),
        "delta_total_due": money(Decimal(new["document_total_due"]) - Decimal(old["document_total_due"])),
        "quantity_effect": money(quantity_effect),
        "tariff_effect": money(tariff_effect),
        "rounding_effect": money(delta - quantity_effect - tariff_effect),
    }
    assert actual == expected, f"Expected {expected}; got {actual}"
    assert actual == {
        "older_current_charges": "200.00", "newer_current_charges": "270.00",
        "delta_current_charges": "70.00", "delta_total_due": "70.00",
        "quantity_effect": "40.00", "tariff_effect": "30.00", "rounding_effect": "0.00",
    }
    print("Engine v1 schemas and synthetic 200 -> 270 fixtures: OK")


if __name__ == "__main__":
    if "--write-schemas" in sys.argv:
        SCHEMAS.mkdir(parents=True, exist_ok=True)
        for name, model in MODELS.items():
            (SCHEMAS / f"{name}.schema.json").write_text(
                json.dumps(model.model_json_schema(mode="validation"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    verify()
