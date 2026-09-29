"""Load, run and persist one dialogue turn. External calls happen outside database transactions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from app.db.models import AssistantAnswer, DialogState, Profile
from app.db.store import SqlStore, now
from app.errors import ApiError
from app.services.dialog import CHANNELS, MEMORY_TTL, SERVICE_NAMES, DialogDeps, public_reply, step


@dataclass
class Turn:
    user_id: uuid.UUID
    channel: str
    version: int
    state: dict
    reply: dict
    effects: dict = field(default_factory=dict)
    answer: dict | None = None
    dataset_kind: str = "public_reference"


def _consent(profile: Profile, state: dict | None, settings) -> bool:
    if (state or {}).get("llm_declined"):
        return False
    return profile.chat_llm_consent_at is not None or \
        profile.privacy_notice_version == settings.privacy_notice_version


def compute_turn(store: SqlStore, user_id: str, channel: str, text: str | None, choice: str | None,
                 receipt_ref: dict | None = None, *, lookup=None, extract=None) -> Turn:
    """Read state and profile, run one dialogue step. No database transaction is held meanwhile."""
    from app.services.assistant_adapter import answer_json
    from app.services.assistant_store import knowledge, owner_receipt_pair, receipt_snapshots
    from app.services.cohort_store import city_comparison
    from app.services.deepseek import extract as model_extract
    from app.services.house_lookup import lookup_for

    if channel not in CHANNELS:
        raise ValueError("unknown dialogue channel")
    uid = uuid.UUID(user_id)
    settings = store.settings
    with store.Session() as session:
        profile = session.get(Profile, uid)
        if profile is None:
            raise ApiError(401, "AUTH_REQUIRED", "Войдите в приложение.")
        row = session.get(DialogState, (uid, channel))
        raw_state = dict(row.state) if row is not None else None
        version = row.version if row is not None else 0
        session.expunge(profile)
    snapshots = []
    if receipt_ref is not None:
        snapshots, _ = receipt_snapshots(store, user_id, [receipt_ref])
    personal, _ = owner_receipt_pair(store, user_id, receipt_ref["id"] if receipt_ref else None)
    consent = _consent(profile, raw_state, settings)
    api_key = settings.deepseek_api_key if consent else None
    privacy_ok = profile.privacy_notice_version == settings.privacy_notice_version
    bundle = knowledge()

    def answer(question: str, context: dict, intent: str | None) -> dict:
        return answer_json(question, context, snapshots,
                           {"role": profile.role, "territory_id": profile.territory_id}, bundle,
                           api_key=api_key, model=settings.deepseek_model,
                           personal_snapshots=personal,
                           allow_receipt_model=privacy_ok,
                           city_lookup=lambda rid, code, metric: city_comparison(store, user_id, rid, code, metric),
                           intent=intent)

    if extract is None and api_key:
        def extract(message: str, summary: dict) -> dict:
            return model_extract(message, summary, bundle.topics, dict(SERVICE_NAMES), api_key,
                                 settings.deepseek_model)
    deps = DialogDeps(knowledge=bundle, answer=answer,
                      lookup=lookup if lookup is not None else lookup_for(store),
                      extract=extract if api_key else None,
                      llm_offer=bool(settings.deepseek_api_key) and not consent and
                      not (raw_state or {}).get("llm_declined"),
                      user_scope=user_id)
    state, reply = step(raw_state, text, choice, deps)
    if "consent" in deps.effects:
        state["llm_declined"] = not deps.effects["consent"]
    record = reply.get("_answer")
    kind = "public_reference"
    if record and record["result"].get("receipt_ref"):
        selected = snapshots or personal
        kind = selected[0]["dataset_kind"] if selected else kind
    elif profile.territory_id == "demo-territory" and not state["memory"].get("territory_id"):
        kind = "synthetic"
    reply["dataset_kind"] = kind
    return Turn(uid, channel, version, state, public_reply(reply), dict(deps.effects), record, kind)


def commit_turn(session, turn: Turn) -> bool:
    """Persist the new state if nobody else advanced this dialogue meanwhile. Returns False on conflict."""
    moment = now()
    row = session.get(DialogState, (turn.user_id, turn.channel), with_for_update=True)
    if (row.version if row is not None else 0) != turn.version:
        return False
    if row is None:
        session.add(DialogState(user_id=turn.user_id, channel=turn.channel, state=turn.state, version=1,
                                updated_at=moment, expires_at=moment + MEMORY_TTL))
    else:
        row.state = turn.state
        row.version += 1
        row.updated_at = moment
        row.expires_at = moment + MEMORY_TTL
    if "consent" in turn.effects:
        profile = session.get(Profile, turn.user_id)
        if profile is not None:
            profile.chat_llm_consent_at = moment if turn.effects["consent"] else None
    if turn.answer is not None:
        result = turn.answer["result"]
        ref = result.get("receipt_ref")
        session.add(AssistantAnswer(id=uuid.uuid4(), user_id=turn.user_id, question=turn.answer["question"],
                                    result=result, receipt_id=uuid.UUID(ref["id"]) if ref else None,
                                    receipt_revision=ref["revision"] if ref else None,
                                    dataset_kind=turn.dataset_kind, created_at=moment,
                                    expires_at=moment + timedelta(days=30)))
    return True


def run_web_turn(store: SqlStore, user_id: str, text: str | None, choice: str | None,
                 receipt_ref: dict | None = None) -> dict:
    turn = compute_turn(store, user_id, "web", text, choice, receipt_ref)
    with store.Session.begin() as session:
        if not commit_turn(session, turn):
            raise ApiError(409, "REVISION_CONFLICT", "Диалог изменён в другой вкладке. Повторите сообщение.")
    return turn.reply


def purge_expired(session) -> None:
    from sqlalchemy import delete

    from app.db.models import ExternalUsage

    moment = now()
    session.execute(delete(DialogState).where(DialogState.expires_at <= moment))
    session.execute(delete(ExternalUsage).where(
        ExternalUsage.day < (moment - timedelta(days=7)).date().isoformat()))

