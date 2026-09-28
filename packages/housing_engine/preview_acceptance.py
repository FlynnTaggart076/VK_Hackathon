"""Synthetic HTTP acceptance of the isolated, passwordless browser preview.

Run from this repository with PREVIEW_BASE_URL=https://host/team/zhkh-preview/
python packages/housing_engine/preview_acceptance.py. This script creates only
synthetic server-side sample receipts and removes its drafts and receipts.
It never prints bearer tokens or user identifiers.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
import hashlib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class AcceptanceError(Exception):
    pass


def check_base(value: str) -> str:
    parts = urlsplit(value)
    if parts.path.rstrip("/") != "/team/zhkh-preview" or parts.query or parts.fragment:
        raise AcceptanceError("PREVIEW_BASE_URL must end at /team/zhkh-preview/")
    if parts.scheme == "https" and parts.hostname:
        return value.rstrip("/")
    if parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}:
        return value.rstrip("/")
    raise AcceptanceError("Use HTTPS, or HTTP only on loopback")


class Client:
    def __init__(self, base: str, token: str | None = None):
        self.base = base
        self.token = token

    def request(self, method: str, path: str, *, body: dict | None = None,
                idempotent: bool = False, expect: int = 200) -> dict | None:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if idempotent:
            headers["Idempotency-Key"] = str(uuid.uuid4())
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(self.base + path, data=data, method=method,
                                 headers=headers), timeout=20) as response:
                status = response.status
                raw = response.read()
        except HTTPError as exc:
            try:
                code = json.loads(exc.read()).get("error", {}).get("code", "UNKNOWN")
            except (ValueError, UnicodeDecodeError):
                code = "NON_JSON_ERROR"
            if exc.code == expect:
                return {"error": {"code": code}}
            raise AcceptanceError(f"{method} {path}: HTTP {exc.code} {code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AcceptanceError(f"{method} {path}: network {type(exc).__name__}") from None
        if status != expect:
            raise AcceptanceError(f"{method} {path}: HTTP {status}, expected {expect}")
        if expect == 204:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise AcceptanceError(f"{method} {path}: invalid JSON") from None


def ensure(condition: bool, label: str) -> None:
    if not condition:
        raise AcceptanceError(label)


def guest(base: str) -> tuple[Client, str]:
    anonymous = Client(base)
    auth = anonymous.request("POST", "/api/v1/auth/preview", body={})
    ensure(isinstance(auth, dict) and isinstance(auth.get("access_token"), str),
           "passwordless preview auth did not issue a bearer")
    user_id = auth["user"]["id"]
    client = Client(base, auth["access_token"])
    ensure(client.request("GET", "/api/v1/me")["user"]["id"] == user_id,
           "guest identity was not preserved by /me")
    return client, user_id


def wait_for_sample(client: Client, queued: dict) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = client.request("GET", f"/api/v1/jobs/{queued['job_id']}")
        if job["state"] == "succeeded":
            return client.request("GET", f"/api/v1/receipts/{queued['receipt']['id']}")
        if job["state"] == "failed":
            raise AcceptanceError("synthetic import job failed")
        time.sleep(1)
    raise AcceptanceError("synthetic import job timed out")


def add_sample(client: Client, fixture_id: str, amount: str) -> dict:
    queued = client.request("POST", "/api/v1/receipts/demo", body={"fixture_id": fixture_id},
                            idempotent=True, expect=202)
    receipt = wait_for_sample(client, queued)
    ensure(receipt["dataset_kind"] == "synthetic" and
           receipt["bill_data"]["document_total_due"] == amount and
           receipt["status"] == "needs_review", f"{fixture_id}: sample facts/review state")
    edited = client.request("PUT", f"/api/v1/receipts/{receipt['id']}/draft", body={
        "expected_revision": receipt["revision"], "bill_data": receipt["bill_data"],
    })
    warnings = sorted({issue["code"] for issue in edited["issues"]
                       if issue["severity"] == "warning"})
    confirmed = client.request("POST", f"/api/v1/receipts/{receipt['id']}/confirm",
                               body={"expected_revision": edited["revision"],
                                     "acknowledged_warning_codes": warnings}, idempotent=True)
    ensure(confirmed["status"] == "confirmed" and
           confirmed["dataset_kind"] == "synthetic", f"{fixture_id}: confirmation")
    return confirmed


def reject_raw_upload(client: Client) -> None:
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "receipts"
    sample = fixture_dir / "demo-bill-2026-08.pdf"
    content = sample.read_bytes()
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    row = next(item for item in manifest["samples"] if item["file"] == sample.name)
    ensure(row["is_synthetic"] and len(content) == row["bytes"] and
           hashlib.sha256(content).hexdigest() == row["sha256"],
           "synthetic upload fixture does not match its manifest")
    boundary = "preview-acceptance-" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{sample.name}\"\r\nContent-Type: application/pdf\r\n\r\n").encode() + \
           content + f"\r\n--{boundary}--\r\n".encode()
    request = Request(client.base + "/api/v1/receipts", data=body, method="POST", headers={
        "Authorization": f"Bearer {client.token}",
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urlopen(request, timeout=20) as response:
            raise AcceptanceError(f"raw upload unexpectedly accepted: HTTP {response.status}")
    except HTTPError as exc:
        try:
            code = json.loads(exc.read())["error"]["code"]
        except (ValueError, KeyError, UnicodeDecodeError):
            code = "NON_JSON_ERROR"
        ensure((exc.code, code) == (403, "PREVIEW_SYNTHETIC_ONLY"),
               f"raw upload boundary: HTTP {exc.code} {code}")
    except (URLError, TimeoutError, OSError) as exc:
        raise AcceptanceError(f"raw upload boundary: network {type(exc).__name__}") from None


def context(topic: str | None, receipt: dict | None = None) -> dict:
    return {"territory_id": "moscow", "role": "tenant", "topic_id": topic,
            "organization_id": None, "service_code": None, "document_kind": None,
            "receipt_id": receipt["id"] if receipt else None,
            "receipt_revision": receipt["revision"] if receipt else None}


def run(base: str) -> list[str]:
    checks: list[str] = []
    anonymous = Client(base)
    meta = anonymous.request("GET", "/api/v1/meta")
    ensure(meta["mode"] == "preview" and not meta["features"]["engine_stub"] and
           not meta["features"]["external_submission"] and
           not meta["features"]["voice"], "preview mode/feature boundary")
    checks.append("preview mode and product boundary")
    a, a_id = guest(base)
    b, b_id = guest(base)
    ensure(a_id != b_id, "two anonymous visits share an identity")
    checks.append("two independent virtual guests")

    catalog = a.request("GET", "/api/v1/catalog")
    choices = {item["id"] for item in catalog["territories"]}
    ensure({"moscow", "moscow-oblast"} <= choices, "Moscow/MO first-run choices absent")
    for client, territory in ((a, "moscow"), (b, "moscow-oblast")):
        profile = client.request("PUT", "/api/v1/me/profile", body={
            "role": "tenant", "territory_id": territory,
            "privacy_notice_version": meta["privacy_notice"]["version"],
            "privacy_acknowledged": True,
        })
        ensure(profile["territory_id"] == territory and profile["onboarding_completed"],
               f"first-run profile {territory}")
    checks.append("Moscow/MO first-run and privacy confirmation")

    reject_raw_upload(a)
    checks.append("raw document upload blocked in preview")

    august = add_sample(a, "water-2026-08", "200.00")
    september = add_sample(a, "water-2026-09", "270.00")
    refs = [{"id": row["id"], "revision": row["revision"]}
            for row in (september, august)]
    checks.append("two synthetic imports, human review and confirmation")
    explanation = a.request("GET", f"/api/v1/receipts/{august['id']}/explanation"
                            f"?revision={august['revision']}")
    ensure(explanation["calculated_total_due"] == "200.00", "receipt explanation arithmetic")
    compared = a.request("POST", "/api/v1/comparisons", body={
        "left": refs[0], "right": refs[1], "identity_acknowledged": False,
    })
    matched = [line for line in compared["lines"] if line["match_status"] == "matched"]
    ensure(compared["status"] == "complete" and compared["dataset_kind"] == "synthetic" and
           compared["delta_total_due"] == "70.00" and len(matched) == 1 and
           matched[0]["quantity_effect"] == "40.00" and
           matched[0]["tariff_effect"] == "30.00", "200 -> 270 = 40 + 30 comparison")
    checks.append("200 to 270 comparison with 40/30 factors")

    known = a.request("POST", "/api/v1/assistant/answers", body={
        "question": "Где найти лицевой счёт?", "context": context("account_number"),
    })
    unknown = a.request("POST", "/api/v1/assistant/answers", body={
        "question": "xyzzy неизвестное", "context": context(None),
    })
    out_of_scope = a.request("POST", "/api/v1/assistant/answers", body={
        "question": "Напиши функцию сортировки списка на Python.", "context": context(None),
    })
    ensure(known["status"] == "answered" and
           unknown["status"] == out_of_scope["status"] == "unsupported" and
           not unknown["sources"] and not out_of_scope["sources"],
           "known/unknown/out-of-scope FAQ boundary")
    checks.append("known, unknown and out-of-scope questions")

    draft = a.request("POST", "/api/v1/drafts", body={
        "topic_id": "request_breakdown", "organization_id": None,
        "receipt_refs": [refs[0]],
        "line_id": september["bill_data"]["services"][0]["line_id"],
        "user_question": "Поясните начисление",
    }, idempotent=True, expect=201)
    ensure("270.00" in draft["text"] and draft["recipient"] is None and
           all(action["type"] != "send" for action in draft["actions"]),
           "copy-only draft facts")
    edited = a.request("PUT", f"/api/v1/drafts/{draft['id']}", body={
        "expected_revision": draft["revision"], "text": draft["text"] + " Проверю вручную.",
    })
    ensure(edited["revision"] == draft["revision"] + 1, "draft edit revision")
    checks.append("edit and copy-only draft, no recipient or sending")

    history = a.request("GET", "/api/v1/receipts")
    ensure({august["id"], september["id"]} <= {row["id"] for row in history["items"]},
           "A history lacks its samples")
    other_history = b.request("GET", "/api/v1/receipts")
    ensure(not {august["id"], september["id"]} &
           {row["id"] for row in other_history["items"]}, "B history leaks A samples")
    for path in (f"/api/v1/receipts/{august['id']}",
                 f"/api/v1/assistant/answers/{known['id']}",
                 f"/api/v1/drafts/{draft['id']}"):
        result = b.request("GET", path, expect=404)
        ensure(result["error"]["code"] == "NOT_FOUND", "cross-guest 404 contract")
    rejected = b.request("POST", "/api/v1/comparisons", body={
        "left": refs[0], "right": refs[1], "identity_acknowledged": False,
    }, expect=404)
    ensure(rejected["error"]["code"] == "NOT_FOUND", "cross-guest comparison isolation")
    checks.append("history and cross-guest owner isolation")

    a.request("DELETE", f"/api/v1/drafts/{draft['id']}", expect=204)
    for receipt in (august, september):
        a.request("DELETE", f"/api/v1/receipts/{receipt['id']}", expect=204)
        a.request("GET", f"/api/v1/receipts/{receipt['id']}", expect=404)
    checks.append("draft and receipt deletion")
    return checks


def main() -> int:
    try:
        base = check_base(os.environ.get("PREVIEW_BASE_URL", ""))
        checks = run(base)
    except (AcceptanceError, KeyError, TypeError, ValueError) as exc:
        print(f"Preview acceptance FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Preview acceptance OK: {len(checks)} synthetic checks")
    for item in checks:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
