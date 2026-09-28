"""Validate the E0 HTTP OpenAPI, engine links and synthetic examples.

From the repository root after installing scripts/requirements-contracts.txt:
    python scripts/make_http_examples.py
    python scripts/check_http_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_spec_url
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "contracts/http/openapi.yaml"
EXAMPLES = SPEC.parent / "examples"
ENGINE = ROOT / "contracts/engine/v1"

REQUIRED_OPERATIONS = {
    ("get", "/api/v1/meta"),
    ("post", "/api/v1/auth/max"), ("post", "/api/v1/auth/demo"),
    ("post", "/api/v1/auth/preview"),
    ("post", "/api/v1/auth/logout"), ("get", "/api/v1/me"),
    ("put", "/api/v1/me/profile"), ("get", "/api/v1/catalog"),
    ("post", "/api/v1/assistant/answers"), ("get", "/api/v1/assistant/answers/{id}"),
    ("post", "/api/v1/receipts"), ("get", "/api/v1/receipts"),
    ("post", "/api/v1/receipts/manual"), ("post", "/api/v1/receipts/demo"),
    ("get", "/api/v1/receipts/{id}"), ("delete", "/api/v1/receipts/{id}"),
    ("put", "/api/v1/receipts/{id}/draft"),
    ("post", "/api/v1/receipts/{id}/confirm"),
    ("post", "/api/v1/receipts/{id}/retry"),
    ("get", "/api/v1/receipts/{id}/explanation"),
    ("get", "/api/v1/receipts/{id}/source"),
    ("get", "/api/v1/receipts/{id}/pages/{page}"),
    ("get", "/api/v1/jobs/{id}"),
    ("post", "/api/v1/comparisons"), ("post", "/api/v1/drafts"),
    ("get", "/api/v1/drafts/{id}"), ("put", "/api/v1/drafts/{id}"),
    ("delete", "/api/v1/drafts/{id}"),
    ("post", "/integrations/max/webhook"),
}

EXAMPLE_SCHEMAS = {
    "meta-dev": "Meta", "me": "UserAndProfile", "catalog": "Catalog",
    "receipt-confirmed": "ReceiptView", "receipt-queued": "ReceiptQueued",
    "receipt-manual-required": "ReceiptView",
    "receipt-list": "ReceiptList", "job-queued": "Job",
    "answer-unsupported": "AnswerView", "answer-clarification": "AnswerView",
    "comparison-partial": "ComparisonView", "comparison-identity": "ComparisonView",
    "comparison-complete": "ComparisonView",
    "explanation-incomplete": "../engine/v1/ReceiptExplanation.schema.json",
    "draft": "DraftView",
    **{name: "ErrorEnvelope" for name in [
        "error-401", "error-409", "error-413", "error-422", "error-429",
        "error-503", "error-415", "error-410", "error-409-incomparable", "error-409-preview",
    ]},
}

ENGINE_FIELDS = {
    "AnswerView": ("AnswerResult.schema.json", {"id", "created_at", "stale", "stale_reasons", "dataset_kind"}),
    "ComparisonView": ("ComparisonResult.schema.json", {"dataset_kind"}),
}


def validate_examples(doc: dict) -> None:
    base_uri = SPEC.resolve().as_uri()

    def retrieve(uri: str) -> Resource:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError(f"Only local schema references are allowed: {uri}")
        path = Path(url2pathname(parsed.path)).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError(f"Schema reference escapes checkout: {uri}")
        if path.suffix != ".json":
            raise ValueError(f"Expected engine JSON Schema: {uri}")
        return Resource.from_contents(json.loads(path.read_text(encoding="utf-8")), default_specification=DRAFT202012)

    registry = Registry(retrieve=retrieve).with_resource(
        base_uri, Resource.from_contents(doc, default_specification=DRAFT202012)
    )
    for name, schema_name in EXAMPLE_SCHEMAS.items():
        value = json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
        schema = {"$ref": (f"{base_uri}#/components/schemas/{schema_name}"
                           if not schema_name.startswith("../") else urljoin(base_uri, schema_name))}
        validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        errors = list(validator.iter_errors(value))
        if errors:
            first = sorted(errors, key=lambda e: str(e.path))[0]
            raise AssertionError(f"{name}: {list(first.path)}: {first.message}")


def main() -> None:
    doc = yaml.safe_load(SPEC.read_text(encoding="utf-8-sig"))
    validate_spec_url(SPEC.resolve().as_uri())
    actual = {(method, path) for path, item in doc["paths"].items()
              for method in item if method in {"get", "post", "put", "delete", "patch"}}
    assert actual == REQUIRED_OPERATIONS, f"operation drift: missing={REQUIRED_OPERATIONS - actual}, extra={actual - REQUIRED_OPERATIONS}"
    assert any(server["url"] == "/team/zhkh" for server in doc["servers"])
    assert not any("Pending" in name for name in doc["components"]["schemas"])
    def linked_examples(node: object) -> set[str]:
        if isinstance(node, dict):
            own = {node["externalValue"]} if "externalValue" in node else set()
            return own | set().union(*(linked_examples(value) for value in node.values()))
        if isinstance(node, list):
            return set().union(*(linked_examples(value) for value in node))
        return set()

    for link in linked_examples(doc):
        path = (SPEC.parent / link).resolve()
        assert path.is_relative_to(EXAMPLES) and path.is_file(), f"broken canonical example link: {link}"
        assert path.stem in EXAMPLE_SCHEMAS, f"unvalidated linked example: {link}"
    for view, (filename, backend_fields) in ENGINE_FIELDS.items():
        engine_schema = json.loads((ENGINE / filename).read_text(encoding="utf-8"))
        model = doc["components"]["schemas"][view]
        assert set(model["properties"]) == set(engine_schema["properties"]) | backend_fields, view
        assert set(model["required"]) == set(engine_schema["required"]) | backend_fields, view
        for field in engine_schema["properties"]:
            assert model["properties"][field]["$ref"] == f"../engine/v1/{filename}#/properties/{field}", (view, field)
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            assert "responses" in operation and operation["responses"], (method, path)
            if method == "post" and (path.startswith("/api/v1/receipts") or path == "/api/v1/drafts"):
                if path.endswith("/retry") or path.endswith("/confirm") or path in {
                    "/api/v1/receipts", "/api/v1/receipts/manual", "/api/v1/receipts/demo", "/api/v1/drafts"
                }:
                    assert any(p.get("$ref") == "#/components/parameters/IdempotencyKey"
                               for p in operation.get("parameters", [])), (method, path)
    validate_examples(doc)
    print(f"OK: OpenAPI 3.1; {len(actual)} operations; {len(EXAMPLE_SCHEMAS)} JSON examples; engine fields linked")


if __name__ == "__main__":
    main()
