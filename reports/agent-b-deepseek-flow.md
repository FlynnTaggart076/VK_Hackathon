# B — E4 DeepSeek / private receipt flow

## Checkpoint 1: model adapter and private monthly comparison

Base: `9b58db6`. Branch: `agent-b/e4-deepseek-flow`. This checkpoint is reviewable but **not E4 acceptance**.

Implemented:

- Server-only `DEEPSEEK_API_KEY`, default `deepseek-flash`, official Chat Completions JSON mode, 8-second timeout, bounded output, exact classification schema, fallback on absent key or invalid/empty/truncated response. Common phone/email/account/address spans are redacted before sending questions. No credential or raw document logging.
- Free-text topic classification while an explicit selected topic wins. Catalog prose may be shortened by the model; any numeric token not in the authoritative card rejects the generated text. Personal receipt arithmetic and comparison are deterministic.
- Owner-scoped latest confirmed receipt and **exact previous calendar month** for the same nonempty account and provider. One receipt gives current charges and states the missing prior month. MAX text and mini-app use this owner selection. Confirmed revisions only.
- Bounded MAX clarification continuation (same owner, last 15 minutes); model failure does not block later `/help`. `/start` and `/help` disclose external text processing. The separate `/llm_on` and `/llm_off` chat consent is persisted by migration; existing v1 profiles cannot silently transmit chat text.
- Privacy notice v2.0 and 120-day structured receipt retention; source bytes remain 7 days. Existing v1.0 profile must acknowledge v2.0 before mini-app DeepSeek text is sent. Production and preview API containers receive a model egress network; no new host ports.

Evidence:

- Backend suite: `38 passed, 4 skipped` (local Python 3.13, SQLite tests). New tests cover malformed model fallback, fake numeric claim rejection, redaction, account/provider/owner/month isolation, MAX clarification, explicit old-profile consent and timeout recovery.
- Live DeepSeek synthetic question returned valid JSON from `deepseek-flash` with the current `thinking` option. Local private key was read from `DST.txt`; token and raw user/receipt data were not printed or committed.
- `git diff --check` clean; Compose files parse with PyYAML. The network assertion and Compose workflows include `integration/e4-deepseek`. Docker is unavailable on this Windows checkout, so `docker compose config`, PostgreSQL 17 and container DNS/TLS remain unverified at this checkpoint.

Required follow-up before E4 acceptance:

1. Add PII-free projected confirmed receipt facts to model phrasing with numeric guard; current personal receipt text is deterministic, and EX main-table parser integration depends on C's accepted contract. Show all relevant EX rows or top charges with a stated truncation.
2. Implement profile aggregate opt-in, derived PostgreSQL city/service/scope/segment/unit observations, min-five distinct real contributors, deletion and revocation, and two-month trend only when both cohorts qualify. Current city response explicitly says unavailable; do not claim city comparison ready.
3. Add cohort API schema/OpenAPI, PG17 two-owner/consent/retention tests and `integration/e4-deepseek` CI branch trigger. Test `docker compose config` and API-container egress before VM deployment from coordinator-accepted release SHA.
4. Refactor MAX model call out of the inbox DB transaction if model latency or row lock contention appears in PG17/load checks. Current call is bounded; provider errors fall back safely.

Official API reference: https://api-docs.deepseek.com/guides/json_mode/ and https://api-docs.deepseek.com/api/create-chat-completion/ . Private data handling reference: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html .
