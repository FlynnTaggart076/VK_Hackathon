"""Bounded retention sweep for private source bytes and derived receipts."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select

from app.db.models import AssistantAnswer, Document, Draft, IdempotencyKey, Job, Outbox, Receipt, User, WebhookInbox
from app.db.store import SqlStore, now


def run_retention_once(store: SqlStore) -> None:
    moment = now()
    with store.Session() as session:
        old_receipts = session.scalars(select(Receipt).where(
            Receipt.created_at <= moment - timedelta(days=120)
        ).order_by(Receipt.created_at, Receipt.id).limit(100)).all()
        targets = [(str(row.user_id), str(row.id)) for row in old_receipts]
    for user_id, receipt_id in targets:
        store.delete_receipt(user_id, receipt_id)

    while True:
        path = None
        document_id = None
        with store.Session.begin() as session:
            document = session.scalar(select(Document).where(
                Document.deleted_at.is_(None), Document.expires_at <= moment
            ).order_by(Document.expires_at, Document.id).with_for_update(skip_locked=True).limit(1))
            if document is None:
                break
            document.deleted_at = moment
            document_id = document.id
            path = store.settings.storage_path / document.storage_key
        # Release the document lock before touching jobs. Worker locks job -> receipt -> document.
        with store.Session.begin() as session:
            receipt = session.scalar(select(Receipt).where(Receipt.document_id == document_id))
            if receipt and receipt.status in {"queued", "processing"}:
                for job in session.scalars(select(Job).where(
                    Job.resource_id == receipt.id, Job.state.in_(["queued", "running"])
                ).order_by(Job.id).with_for_update()):
                    job.state = "failed"
                    job.error_code = "SOURCE_EXPIRED"
                    job.stage = None
                    job.lease_token = None
                    job.lease_until = None
                    job.updated_at = moment
                locked_receipt = session.scalar(select(Receipt).where(Receipt.id == receipt.id).with_for_update())
                if locked_receipt and locked_receipt.status in {"queued", "processing"}:
                    locked_receipt.status = "failed"
                    locked_receipt.updated_at = moment
        if path is not None:
            path.unlink(missing_ok=True)
            for preview in path.parent.glob(f"{path.name}.page-*.png"):
                preview.unlink(missing_ok=True)
    with store.Session.begin() as session:
        session.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at <= moment))
        session.execute(delete(WebhookInbox).where(WebhookInbox.expires_at <= moment))
        session.execute(delete(Outbox).where(Outbox.expires_at <= moment))
        session.execute(delete(AssistantAnswer).where(AssistantAnswer.expires_at <= moment))
        session.execute(delete(Draft).where(Draft.expires_at <= moment))
        from app.services.dialog_store import purge_expired

        purge_expired(session)
        for item in session.scalars(select(Outbox).where(
            Outbox.state == "sending", Outbox.run_after <= moment - timedelta(seconds=30)
        ).with_for_update(skip_locked=True)):
            item.state = "uncertain"

    # Search cache files contain the typed house address in their request URL; keep them 30 days.
    cache_dir = store.settings.house_cache_dir
    if cache_dir.is_dir():
        cutoff = (moment - timedelta(days=30)).timestamp()
        for path in cache_dir.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    if store.settings.mode == "preview":
        # Preview users are anonymous and only have one-hour sessions. Remove
        # their derived data after the documented 120-day receipt retention.
        with store.Session.begin() as session:
            stale = session.scalars(select(User).where(
                User.max_user_id.is_(None), User.demo_identity.like("preview-%"),
                User.created_at <= moment - timedelta(days=121)
            ).order_by(User.created_at, User.id).limit(100).with_for_update(skip_locked=True)).all()
            for user in stale:
                session.delete(user)
