"""Isolated Compose HTTP smoke. No token or access code is written or printed.

BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=... \
  python scripts/smoke_e2_http.py start --state /tmp/e2-smoke-state.json
docker compose ... restart api worker
BASE_URL=... DEMO_ACCESS_CODE=... \
  python scripts/smoke_e2_http.py verify --state /tmp/e2-smoke-state.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SmokeError(Exception):
    pass


def request(base: str, method: str, path: str, *, token: str | None = None,
            body: dict | None = None, upload: bytes | None = None,
            idempotency: bool = False) -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if upload is not None:
        boundary = "zhkhsmoke" + uuid.uuid4().hex
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                "filename=\"synthetic.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").encode() + \
               upload + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    try:
        with urlopen(Request(base + path, data=data, method=method, headers=headers), timeout=15) as response:
            status = response.status
            value = json.loads(response.read())
    except HTTPError as exc:
        try:
            code = json.loads(exc.read()).get("error", {}).get("code", "UNKNOWN")
        except (ValueError, UnicodeDecodeError):
            code = "NON_JSON_ERROR"
        raise SmokeError(f"{method} {path}: HTTP {exc.code} {code}") from None
    except (URLError, TimeoutError) as exc:
        raise SmokeError(f"{method} {path}: network {type(exc).__name__}") from None
    expected = 202 if path == "/api/v1/receipts" and method == "POST" else 200
    if status != expected:
        raise SmokeError(f"{method} {path}: HTTP {status}, expected {expected}")
    return value


def authenticate(base: str, access_code: str) -> str:
    result = request(base, "POST", "/api/v1/auth/demo",
                     body={"identity": "reviewer_a", "access_code": access_code})
    return result["access_token"]


def confirm_state(base: str, token: str, receipt_id: str, revision: int) -> None:
    receipt = request(base, "GET", f"/api/v1/receipts/{receipt_id}", token=token)
    if receipt["status"] != "confirmed" or receipt["revision"] != revision or \
            receipt["bill_data"]["document_total_due"] != "200.00":
        raise SmokeError("confirmed receipt changed after restart")
    explanation = request(base, "GET", f"/api/v1/receipts/{receipt_id}/explanation?revision={revision}",
                          token=token)
    if explanation["calculated_total_due"] != "200.00" or \
            explanation["reconciliation_status"] != "matched" or explanation["sources"] != []:
        raise SmokeError("persisted explanation is invalid")
    if not any(item["code"] == "ARITHMETIC_ONLY" for item in explanation["issues"]):
        raise SmokeError("arithmetic-only boundary missing")


def start(base: str, token: str, state_path: Path) -> None:
    meta = request(base, "GET", "/api/v1/meta")
    if meta["features"]["engine_stub"] or not meta["features"]["receipt_ocr"]:
        raise SmokeError("real engine feature flags are not active")
    request(base, "PUT", "/api/v1/me/profile", token=token,
            body={"role": "tenant", "territory_id": "demo-territory",
                  "privacy_notice_version": meta["privacy_notice"]["version"],
                  "privacy_acknowledged": True})
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "receipts" / "demo-bill-2026-08.pdf"
    queued = request(base, "POST", "/api/v1/receipts", token=token,
                     upload=fixture.read_bytes(), idempotency=True)
    receipt_id, job_id = queued["receipt"]["id"], queued["job_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = request(base, "GET", f"/api/v1/jobs/{job_id}", token=token)
        if job["state"] == "succeeded":
            break
        if job["state"] == "failed":
            raise SmokeError(f"worker failed: {job['error']['code'] if job['error'] else 'UNKNOWN'}")
        time.sleep(1)
    else:
        raise SmokeError("worker timeout")
    receipt = request(base, "GET", f"/api/v1/receipts/{receipt_id}", token=token)
    if receipt["extraction_outcome"] != "recognized" or receipt["bill_data"]["document_total_due"] != "200.00":
        raise SmokeError("bytes extraction did not recognize the synthetic bill")
    edited_bill = dict(receipt["bill_data"], issuer_name="Smoke reviewed issuer")
    edited = request(base, "PUT", f"/api/v1/receipts/{receipt_id}/draft", token=token,
                     body={"expected_revision": receipt["revision"], "bill_data": edited_bill})
    warnings = sorted({item["code"] for item in edited["issues"] if item["severity"] == "warning"})
    confirmed = request(base, "POST", f"/api/v1/receipts/{receipt_id}/confirm", token=token,
                        idempotency=True,
                        body={"expected_revision": edited["revision"],
                              "acknowledged_warning_codes": warnings})
    confirm_state(base, token, receipt_id, confirmed["revision"])
    temporary = state_path.with_name(state_path.name + ".tmp")
    temporary.write_text(json.dumps({"receipt_id": receipt_id, "revision": confirmed["revision"]}), encoding="utf-8")
    temporary.replace(state_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["start", "verify"])
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    base = os.environ.get("BASE_URL", "").rstrip("/")
    access_code = os.environ.get("DEMO_ACCESS_CODE", "")
    if not base.startswith(("http://127.0.0.1:", "http://localhost:")) or not access_code:
        print("BASE_URL must be loopback HTTP and DEMO_ACCESS_CODE must be set", file=sys.stderr)
        return 2
    try:
        token = authenticate(base, access_code)
        if args.phase == "start":
            start(base, token, args.state)
        else:
            state = json.loads(args.state.read_text(encoding="utf-8"))
            confirm_state(base, token, state["receipt_id"], state["revision"])
    except (SmokeError, OSError, KeyError, ValueError) as exc:
        print(f"E2 HTTP smoke {args.phase} FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"E2 HTTP smoke {args.phase} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
