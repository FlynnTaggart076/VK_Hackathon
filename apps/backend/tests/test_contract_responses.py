"""Validate actual E1 JSON against the accepted E0 OpenAPI and engine refs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from test_dev_api import accept_privacy, client, headers, image_bytes, login, upload


ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "contracts/http/openapi.yaml"


def validate_response(schema_name: str, body: dict) -> None:
    doc = yaml.safe_load(SPEC.read_text(encoding="utf-8-sig"))
    base_uri = SPEC.resolve().as_uri()

    def retrieve(uri: str) -> Resource:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError(f"Unexpected remote schema: {uri}")
        path = Path(url2pathname(parsed.path)).resolve()
        if not path.is_relative_to(ROOT / "contracts"):
            raise ValueError(f"Schema escapes accepted contracts: {uri}")
        return Resource.from_contents(json.loads(path.read_text(encoding="utf-8")),
                                      default_specification=DRAFT202012)

    registry = Registry(retrieve=retrieve).with_resource(
        base_uri, Resource.from_contents(doc, default_specification=DRAFT202012))
    schema = {"$ref": f"{base_uri}#/components/schemas/{schema_name}"}
    errors = list(Draft202012Validator(schema, registry=registry,
                                       format_checker=FormatChecker()).iter_errors(body))
    assert not errors, f"{schema_name}: {errors[0].json_path}: {errors[0].message}" if errors else ""


def test_live_e1_response_shapes(client):
    meta = client.get("/api/v1/meta")
    validate_response("Meta", meta.json())

    invalid = client.get("/api/v1/me")
    assert invalid.status_code == 401
    validate_response("ErrorEnvelope", invalid.json())

    auth = login(client, "reviewer_a")
    validate_response("AuthResponse", auth)
    token = auth["access_token"]
    validate_response("UserAndProfile", client.get("/api/v1/me", headers=headers(token)).json())
    accept_privacy(client, token)
    validate_response("UserAndProfile", client.get("/api/v1/me", headers=headers(token)).json())
    validate_response("Catalog", client.get("/api/v1/catalog", headers=headers(token)).json())

    queued = upload(client, token, str(uuid.uuid4()))
    assert queued.status_code == 202
    validate_response("ReceiptQueued", queued.json())
    receipt_id, job_id = queued.json()["receipt"]["id"], queued.json()["job_id"]
    validate_response("ReceiptView", client.get(f"/api/v1/receipts/{receipt_id}",
                                                headers=headers(token)).json())
    validate_response("Job", client.get(f"/api/v1/jobs/{job_id}", headers=headers(token)).json())

    conflict = upload(client, token, str(uuid.uuid4()), mime="application/pdf", data=image_bytes())
    assert conflict.status_code == 415
    validate_response("ErrorEnvelope", conflict.json())
