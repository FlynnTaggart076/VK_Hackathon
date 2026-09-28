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

## Checkpoint 2: real city cohort and grounded EPD answers

Previous B code checkpoint: `bfc1d97`; preview retention CI fix: `85359a2`. The new code below remains a dependency checkpoint until coordinator integration, PG17/Compose CI, and VM/MAX acceptance.

Implemented:

- Explicit `PUT /api/v1/me/aggregate-consent` opt-in, derived city cohort migration, revocation and receipt deletion. Only confirmed `user_provided` rows from opted-in owners participate. Query matches exact city, calendar month, service, scope, segment and unit; C's cohort helper suppresses mean/median and sample size below five distinct contributors. Duplicate ambiguous contributor values suppress the cohort. Cross-owner receipt IDs return 404.
- `GET /api/v1/receipts/{id}/city-comparison` with `metric=charge_amount|tariff` and OpenAPI contract. Repeated service codes in a bill are ineligible until a line-specific contract is added; distinct hot-water carrier/energy and electricity segments are never averaged together.
- Catchall `other` service rows are never indexed or offered for city comparison; unrelated services with the same generic code/unit cannot enter one cohort.
- Mini-app assistant and MAX city-intent answers use that same owner-scoped query. Citywide trend is stated only when both exact calendar months qualify and the owner's line scope/segment/unit match. Otherwise the answer states insufficient/ambiguous data. City comparisons are derived locally; no other user's bill or cohort rows enter DeepSeek prompts.
- City numerical prose stays deterministic so the model cannot overstate a small sample. With consent, DeepSeek still classifies the city question; its generative phrasing is limited to verified FAQ and privacy-safe EPD lead-ins. A valid model FAQ classification takes precedence over a keyword heuristic, and an explicit selected topic remains authoritative.
- Accepted `mos-oblast-epd-v1` template enabled. A confirmed EPD's safe `project_receipt_facts` reaches DeepSeek only after v2 privacy acknowledgement. Model supplies a short numeric-free lead-in; deterministic server text carries amounts and all comparisons. Model output with invented numbers is rejected. The one-receipt answer shows top charges, total current charges, and the count of remaining rows.

Evidence:

- Local backend plus engine: `103 passed, 5 skipped` on Windows Python 3.13. The skipped PG17 case is configured in E2 Compose CI with an isolated PostgreSQL schema. Cohort test covers four vs five contributors, two-month trend threshold, different city/period suppression, duplicate line suppression, MAX inbox path, consent revocation, synthetic exclusion, and owner isolation. EPD model mock checks outbound facts exclude account, address and issuer and rejects fabricated amount.
- `scripts/check_http_contract.py`: OpenAPI 3.1, 31 operations, 25 JSON examples, engine fields linked. `git diff --check` clean.
- Private `EX.pdf` read-only parse through C engine: `partial`, `mos-oblast-epd-v1`, 19 billed service rows, four adjustments, period and printed charge/due totals present. No private field values printed or committed.

Remaining before release: verify actual PG17/Compose CI and API-container DNS/TLS, regenerate frontend OpenAPI types, exercise owner and MAX end-to-end on VM from accepted release SHA. EPD OCR is deterministic with user review; worker-side LLM candidate extraction for unresolved rows is not implemented yet. C's safe main-table projection strips source labels and turns corrupt numeric cells into null, so the model cannot safely recover an unknown label or missing printed number under the current contract. A backend-only allowlist projection for confirmed synthetic `demo-bill-v1` receipts now permits preview model phrasing after v2 acknowledgement; mocked outbound payload excludes raw name, address, account and issuer, but live preview remains unverified. No VM mutation was made from this branch.
