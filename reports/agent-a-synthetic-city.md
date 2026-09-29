# A · E4 synthetic city preview UI

Code pushed to `origin/agent-a/e4-synthetic-city`: `3f899d28f88fda177d8c0197e76983229d586983`. Base `origin/main` at `ea24d1f3fd52363220eab08c86bc2fabc7703751`. Frontend schema was generated from B's pushed preview OpenAPI contract `dc72ab3df5054e9dc005c32e184e0156aacf22f6`; city fixture expectations came from C's pushed contract `8f637cfb0db3a212cc61e52886cac688e31690e9`.

## Delivered

- A confirmed synthetic receipt on the preview build calls only `GET /api/v1/preview/receipts/{id}/city-comparison`. The production build still uses the existing real city endpoint and retains its `confirmed_opted_in_real_receipts`, five-contributor and separate-consent numeric gate. The preview result requires `synthetic_preview_cohort`, five artificial entries and all numeric fields before it renders numbers.
- The preview screen displays the server's owned receipt value, synthetic mean and median, signed absolute and percentage deviation, metric/unit, month, city label, and artificial record count. It never calculates a tariff or cohort in the browser. It labels the source `Синтетическая учебная выборка — не данные жителей Москвы/МО` and explains that these are fixed training observations.
- A previous-month preview result is rendered only when both responses are complete and have consecutive months plus matching city, service, scope, segment, unit and metric. An ineligible, ambiguous or insufficient result has no cohort numbers and links to the sample catalog. Network/API errors preserve selections and offer `Повторить сравнение`.
- History, receipt review, receipt explanation and the selected-receipt assistant link to the training comparison. A link also appears after an answer to a city question, so the question flow reaches the numeric result. Generic synthetic examples can return a clear `ineligible` result and a link to city-tagged samples.

## Verification

- `npm run build` in production mode: pass. `VITE_PREVIEW_MODE=true VITE_APP_BASE=/team/zhkh-preview/ npm run build`: pass. `npm test`: 4 files, 22 tests pass. Unit cases cover wrong provenance, incomplete or under-five synthetic sample, and exact previous-month dimensions. `node --check` of the browser script and `git diff --check`: pass.
- `npm run test:browser:e4:synthetic-city-preview-mock` against local Vite real mode with preview flags and intercepted API: pass at 360 px, document width 360 px. It imports and confirms the August and September Moscow city fixtures, opens the September receipt from History, asks whether the rise is citywide, follows the answer link, receives one injected HTTP 503, retries, sees September `270.00` versus synthetic mean `342.00` and August `200.00` versus `256.00`, then repeats via the direct History link. A synthetic `insufficient_data` response hides cohort numbers and the previous-month panel. Five preview API queries, zero real cohort queries, no unexpected routes or page errors.
- `npm run test:browser:e4:clarifications` in production-style mock mode: pass at 360 px, including the existing synthetic receipt block on the real city screen. No token, personal receipt or private PDF was read or committed by A.

## Remaining integration acceptance

The complete browser run used intercepted API responses and is frontend evidence, not a PostgreSQL, preview VM or MAX result. Docker CLI is unavailable in A's Windows checkout. After integration, run the preview Compose/PG17 CI and browser path against the accepted release SHA, then deploy only the preview instance through B's controlled VM procedure. Confirm both Moscow and Lyubertsy fixtures and production 403/real cohort isolation on the backend; E5 still requires actual MAX client acceptance.
