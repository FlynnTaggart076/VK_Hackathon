"""Run persisted jobs using short leases and an explicit dev-only result.

The E1 worker does no OCR. User uploads become manual_required with empty fields;
an explicitly imported synthetic demo fixture may be copied into a revision.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select

from app.db.models import Job, Receipt, ReceiptRevision, WorkerHeartbeat
from app.db.store import SqlStore, aware, now
from app.main import Settings, empty_bill


def fixture_root(module_file: Path, configured: str | None) -> Path:
    if configured:
        candidate = Path(configured)
        if candidate.is_dir():
            return candidate
        raise RuntimeError("FIXTURE_ROOT does not name a readable fixture directory")
    for parent in module_file.resolve().parents:
        candidate = parent / "fixtures" / "receipts"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Fixture directory not found; set FIXTURE_ROOT")


FIXTURE_ROOT = fixture_root(Path(__file__), os.environ.get("FIXTURE_ROOT"))
DEMO_FIXTURES = {"water-2026-08", "water-2026-09"}


def heartbeat(store: SqlStore) -> None:
    with store.Session.begin() as session:
        row = session.get(WorkerHeartbeat, "worker", with_for_update=True)
        if row:
            row.updated_at = now()
        else:
            session.add(WorkerHeartbeat(name="worker", updated_at=now()))


def claim(store: SqlStore) -> tuple[uuid.UUID, uuid.UUID] | None:
    moment = now()
    with store.Session.begin() as session:
        exhausted = session.scalars(select(Job).where(
            Job.state == "running", Job.lease_until < moment, Job.attempt >= 3
        ).with_for_update(skip_locked=True)).all()
        for job in exhausted:
            job.state = "failed"
            job.error_code = "RETRY_EXHAUSTED"
            job.stage = None
            job.lease_token = None
            job.lease_until = None
            job.updated_at = moment
            receipt = session.get(Receipt, job.resource_id)
            if receipt and receipt.status == "processing":
                receipt.status = "failed"
                receipt.updated_at = moment
        job = session.scalar(select(Job).where(
            Job.attempt < 3,
            or_(and_(Job.state == "queued", Job.run_after <= moment),
                and_(Job.state == "running", Job.lease_until < moment)),
        ).order_by(Job.created_at, Job.id).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        token = uuid.uuid4()
        job.state = "running"
        job.stage = "dev_stub"
        job.attempt += 1
        job.lease_token = token
        job.lease_until = moment + timedelta(seconds=180)
        job.updated_at = moment
        receipt = session.get(Receipt, job.resource_id)
        if receipt and receipt.status in {"queued", "processing"}:
            receipt.status = "processing"
            receipt.updated_at = moment
        return job.id, token


def finish(store: SqlStore, job_id: uuid.UUID, token: uuid.UUID) -> None:
    if store.settings.mode != "dev" or store.settings.engine_mode != "stub":
        raise RuntimeError("E1 fixture worker is allowed only in dev stub mode")
    with store.Session.begin() as session:
        job = session.get(Job, job_id, with_for_update=True)
        if not job or job.state != "running" or job.lease_token != token or job.lease_until is None or aware(job.lease_until) <= now():
            return  # an expired or replaced lease cannot write a result
        receipt = session.get(Receipt, job.resource_id, with_for_update=True)
        if not receipt or receipt.status != "processing":
            job.state = "failed"
            job.error_code = "RESOURCE_REMOVED"
            job.stage = None
            job.lease_token = None
            job.lease_until = None
            job.updated_at = now()
            return
        if session.get(ReceiptRevision, (receipt.id, 1)) is not None:
            job.state = "succeeded"  # prior committed result; never insert a second revision
            job.stage = None
            job.lease_token = None
            job.lease_until = None
            job.updated_at = now()
            return
        if job.kind == "demo_import" and receipt.dataset_kind == "synthetic":
            fixture_id = job.operation_key.split(":", 2)[1]
            if fixture_id not in DEMO_FIXTURES:
                raise ValueError("unsupported demo fixture")
            bill_data = json.loads((FIXTURE_ROOT / f"{fixture_id}.json").read_text(encoding="utf-8"))
            outcome = "recognized"
            issues = [{"code": "SYNTHETIC_DEMO", "severity": "info", "path": None,
                       "message": "Учебные данные; не реальная квитанция."}]
        else:
            bill_data = empty_bill()
            outcome = "manual_required"
            issues = [{"code": "DEV_STUB_NO_OCR", "severity": "warning", "path": None,
                       "message": "OCR ещё не подключён; заполните поля вручную."}]
        session.add(ReceiptRevision(receipt_id=receipt.id, revision=1,
                                    bill_data=bill_data,
                                    extraction_meta={"field_evidence": [], "issues": issues, "outcome": outcome},
                                    validation={"can_confirm": False, "errors": [], "warnings": issues},
                                    confirmed_at=None, engine_version="dev-stub-e1"))
        receipt.status = "needs_review"
        receipt.extraction_outcome = outcome
        receipt.updated_at = now()
        job.state = "succeeded"
        job.stage = None
        job.error_code = None
        job.lease_token = None
        job.lease_until = None
        job.updated_at = now()


def fail_or_retry(store: SqlStore, job_id: uuid.UUID, token: uuid.UUID, *, retryable: bool) -> None:
    with store.Session.begin() as session:
        job = session.get(Job, job_id, with_for_update=True)
        if not job or job.state != "running" or job.lease_token != token:
            return
        job.lease_token = None
        job.lease_until = None
        job.updated_at = now()
        receipt = session.get(Receipt, job.resource_id)
        if retryable and job.attempt < 3:
            job.state = "queued"
            job.stage = None
            job.run_after = now() + timedelta(seconds=2 ** job.attempt)
            if receipt and receipt.status == "processing":
                receipt.status = "queued"
                receipt.updated_at = now()
        else:
            job.state = "failed"
            job.stage = None
            job.error_code = "ENGINE_UNAVAILABLE" if retryable else "DEV_FIXTURE_INVALID"
            if receipt and receipt.status == "processing":
                receipt.status = "failed"
                receipt.updated_at = now()


def run_once(store: SqlStore) -> bool:
    if store.settings.mode != "dev" or store.settings.engine_mode != "stub":
        raise RuntimeError("E1 fixture worker is allowed only in dev stub mode")
    heartbeat(store)
    selected = claim(store)
    if selected is None:
        return False
    job_id, token = selected
    try:
        finish(store, job_id, token)
    except (ValueError, FileNotFoundError):
        fail_or_retry(store, job_id, token, retryable=False)
    except Exception:
        fail_or_retry(store, job_id, token, retryable=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one claim cycle and exit")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    if not settings.database_url:
        raise RuntimeError("Worker requires persisted DATABASE_URL")
    store = SqlStore(settings)
    if args.once:
        run_once(store)
        return
    while True:
        ran = run_once(store)
        if not ran:
            time.sleep(1)


if __name__ == "__main__":
    main()
