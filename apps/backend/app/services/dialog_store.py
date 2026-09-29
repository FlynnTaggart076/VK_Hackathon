"""Load, run and persist one dialogue turn. External calls happen outside database transactions."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from app.db.models import AssistantAnswer, DialogState, Profile
from app.db.store import SqlStore, now
from app.errors import ApiError
from app.services.dialog import CHANNELS, MEMORY_TTL, DialogDeps, public_reply, step

log = logging.getLogger("app.dialog")


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


def llm_enabled(profile: Profile, state: dict | None, settings) -> bool:
    """DeepSeek reads free text by default; /llm_off or «Без нейросети» turns it off."""
    return bool(settings.deepseek_api_key) and profile.chat_llm_opt_out_at is None and \
        not (state or {}).get("llm_declined")


def compute_turn(store: SqlStore, user_id: str, channel: str, text: str | None, choice: str | None,
                 receipt_ref: dict | None = None, *, lookup=None, route=None) -> Turn:
    """Read state and profile, run one dialogue step. No database transaction is held meanwhile."""
    from app.services.assistant_adapter import answer_json
    from app.services.assistant_store import knowledge, owner_receipt_pair, receipt_snapshots
    from app.services.capabilities import validate_decision
    from app.services.cohort_store import city_comparison
    from app.services.deepseek import route as model_route
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
    bundle = knowledge()

    def answer(question: str, context: dict, intent: str | None) -> dict:
        # The router is the only model call of a turn: no classify()/phrase() here.
        return answer_json(question, context, snapshots,
                           {"role": profile.role, "territory_id": profile.territory_id}, bundle,
                           api_key=None, model=settings.deepseek_model, personal_snapshots=personal,
                           allow_receipt_model=False,
                           city_lookup=lambda rid, code, metric: city_comparison(store, user_id, rid, code, metric),
                           intent=intent)

    if route is None and llm_enabled(profile, raw_state, settings):
        def route(message: str, summary: dict, history: list) -> dict | None:
            decision = validate_decision(model_route(message, summary, history, settings.deepseek_api_key,
                                                     settings.deepseek_model), message)
            if decision is None:
                log.warning("router decision rejected")
            else:
                log.info("router kind=%s function=%s", decision["kind"],
                         (decision.get("action") or {}).get("function"))
            return decision
    periods = sorted({item["bill_data"].get("period") for item in (snapshots or personal)
                      if item["bill_data"].get("period")})
    deps = DialogDeps(knowledge=bundle, answer=answer,
                      lookup=lookup if lookup is not None else lookup_for(store),
                      route=route, user_scope=user_id,
                      facts={"confirmed_receipt_months": periods,
                             "receipt_upload_allowed_here": channel == "web"})
    state, reply = step(raw_state, text, choice, deps)
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
            enabled = turn.effects["consent"]
            profile.chat_llm_consent_at = moment if enabled else None
            profile.chat_llm_opt_out_at = None if enabled else moment
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

