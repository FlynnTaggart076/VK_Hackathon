"""One receipt extraction in a disposable process. Protocol is private JSON on pipes."""

from __future__ import annotations

import base64
import json
import sys
import uuid

from housing_engine import BillData, EngineError

from app.services.engine_adapter import extract_json, validation_json


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read(15_000_000))
        content = base64.b64decode(payload["content"], validate=True)
        result = extract_json(uuid.UUID(payload["receipt_id"]), content,
                              payload["mime_type"], payload["workspace"])
        validation = validation_json(BillData.model_validate_json(json.dumps(result["bill_data"])))
        response = {"result": result, "validation": validation}
    except EngineError as exc:
        response = {"error": {"code": exc.code, "message": exc.message,
                              "retryable": exc.retryable}}
    except Exception:
        response = {"error": {"code": "INTERNAL_ENGINE_ERROR",
                              "message": "Обработка документа недоступна.", "retryable": True}}
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
