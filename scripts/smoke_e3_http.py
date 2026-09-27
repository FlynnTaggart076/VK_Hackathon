"""PG17 Compose HTTP comparison smoke using two synthetic PDF byte uploads.

BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=... \
  python scripts/smoke_e3_http.py
No token or access code is printed. Run against an isolated Compose project.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from smoke_e2_http import SmokeError, authenticate, request, wait_for_job


def error_code(base: str, path: str, token: str, body: dict) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    try:
        with urlopen(Request(base + path, data=data, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        }), timeout=15):
            raise SmokeError(f"{path}: expected rejection")
    except HTTPError as exc:
        result = json.loads(exc.read())
        return exc.code, result["error"]["code"]


def run(base: str, token: str, access_code: str) -> None:
    meta = request(base, "GET", "/api/v1/meta")
    if meta["features"]["engine_stub"] or not meta["features"]["comparison"]:
        raise SmokeError("real comparison feature unavailable")
    request(base, "PUT", "/api/v1/me/profile", token=token, body={
        "role": "tenant", "territory_id": "demo-territory",
        "privacy_notice_version": meta["privacy_notice"]["version"],
        "privacy_acknowledged": True,
    })
    root = Path(__file__).resolve().parents[1] / "fixtures" / "receipts"
    refs = []
    for period, total in (("08", "200.00"), ("09", "270.00")):
        queued = request(base, "POST", "/api/v1/receipts", token=token,
                         upload=(root / f"demo-bill-2026-{period}.pdf").read_bytes(),
                         idempotency=True)
        rid = queued["receipt"]["id"]
        wait_for_job(base, token, queued["job_id"])
        receipt = request(base, "GET", f"/api/v1/receipts/{rid}", token=token)
        if receipt["extraction_outcome"] != "recognized" or \
                receipt["bill_data"]["document_total_due"] != total:
            raise SmokeError(f"synthetic {period} PDF extraction mismatch")
        edited = request(base, "PUT", f"/api/v1/receipts/{rid}/draft", token=token,
                         body={"expected_revision": receipt["revision"],
                               "bill_data": receipt["bill_data"]})
        warnings = sorted({issue["code"] for issue in edited["issues"]
                           if issue["severity"] == "warning"})
        confirmed = request(base, "POST", f"/api/v1/receipts/{rid}/confirm", token=token,
                            idempotency=True, body={"expected_revision": edited["revision"],
                                                    "acknowledged_warning_codes": warnings})
        refs.append({"id": rid, "revision": confirmed["revision"]})
    comparison = {"left": refs[1], "right": refs[0], "identity_acknowledged": False}
    result = request(base, "POST", "/api/v1/comparisons", token=token, body=comparison)
    if (result["status"], result["delta_total_due"], result["dataset_kind"]) != \
            ("complete", "70.00", "user_provided"):
        raise SmokeError("comparison status/amount/dataset mismatch")
    matched = [line for line in result["lines"] if line["match_status"] == "matched"]
    if len(matched) != 1 or (matched[0]["quantity_effect"], matched[0]["tariff_effect"]) != \
            ("40.00", "30.00"):
        raise SmokeError("comparison quantity/tariff decomposition mismatch")
    other = request(base, "POST", "/api/v1/auth/demo", body={
        "identity": "reviewer_b", "access_code": access_code,
    })["access_token"]
    if error_code(base, "/api/v1/comparisons", other, comparison) != (404, "NOT_FOUND"):
        raise SmokeError("comparison owner isolation failed")
    newer = request(base, "GET", f"/api/v1/receipts/{refs[1]['id']}", token=token)
    request(base, "PUT", f"/api/v1/receipts/{refs[1]['id']}/draft", token=token,
            body={"expected_revision": newer["revision"], "bill_data": newer["bill_data"]})
    if error_code(base, "/api/v1/comparisons", token, comparison) != (409, "REVISION_CONFLICT"):
        raise SmokeError("stale revision was accepted")


def main() -> int:
    base = os.environ.get("BASE_URL", "").rstrip("/")
    code = os.environ.get("DEMO_ACCESS_CODE", "")
    if not base.startswith(("http://127.0.0.1:", "http://localhost:")) or not code:
        print("BASE_URL must be loopback HTTP and DEMO_ACCESS_CODE must be set", file=sys.stderr)
        return 2
    try:
        run(base, authenticate(base, code), code)
    except (SmokeError, OSError, KeyError, ValueError) as exc:
        print(f"E3 HTTP comparison smoke FAILED: {exc}", file=sys.stderr)
        return 1
    print("E3 HTTP comparison smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
