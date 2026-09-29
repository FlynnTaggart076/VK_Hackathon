# B: isolated synthetic city comparison for preview

## Submitted code

- Branch: `agent-b/e4-synthetic-cohort`.
- B code SHA: `dc72ab3df5054e9dc005c32e184e0156aacf22f6`.
- B commit parent: `39b071b` is the cherry-pick of C fixtures/contract SHA `8f637cfb0db3a212cc61e52886cac688e31690e9`. Integrate C's original commit first, then cherry-pick only B's `dc72ab3`.
- Scope: `GET /api/v1/preview/receipts/{id}/city-comparison?service_code=cold_water&metric=charge_amount|tariff`, four preview-only catalog/import fixtures, fixed artificial cohort JSON packaged in the backend image, OpenAPI schema, HTTP and PG17 tests.

## Privacy and exact eligibility

- Route requires preview mode and preview auth, an authenticated owner, a confirmed synthetic receipt, exact allowlisted demo-import job provenance, matching profile territory/city/month, and one comparable service line. A foreign receipt is 404; production route is 403 and production import of city fixtures is 404.
- Reads only the fixed `city-preview-cohort-v1.json`; does not query or populate real `receipt_cohort_lines`. The unchanged real city endpoint continues to reject synthetic receipts.
- `provenance` is always `synthetic_preview_cohort`. `sample_size=5` denotes five **artificial records**, never five residents. With fewer than five or a mismatched key, all numeric result fields and sample size are null. Text explicitly states that values are training data rather than city statistics.
- Positive response adds `city_label`, `scope`, `segment_key`, `receipt_value`, own-minus-average difference, percentage and comparison. Mean, median and differences use `Decimal`; exact city/period/service/scope/segment/unit gates precede aggregation. Preview does not require aggregate opt-in because no user receipts enter the fixed sample.

## Verification

- Local Windows Python 3.13 isolated venv: `14 passed, 3 skipped` for `test_e4_preview_city.py`, existing `test_e4_city_cohort.py`, `test_preview_auth.py`, and C's synthetic fixture tests. Skips are tests that require disposable PostgreSQL 17 URLs.
- `python scripts/check_http_contract.py`: OpenAPI 3.1 valid, 32 operations, 25 JSON examples, engine fields linked. Positive and insufficient responses also validated against `PreviewCityComparisonView` in tests.
- `git diff --check` and Python compilation clean. Full import -> worker -> confirm -> comparison tested for Moscow and Lyubertsy, August and September, both charge and tariff; owner isolation, unavailable suppression and production gates tested.
- Added migrated PostgreSQL 17 route test to `.github/workflows/e4-preview-compose.yml`; CI result remains pending integration. Docker CLI is unavailable on this Windows host, so no local Compose image/build claim.

## Deployment and follow-up

- No VM changes or release deployment for this follow-up. Coordinator must accept combined C/B/A release and CI before preview-only rollout. Production keeps the previous release until a separate gate.
- MAX/chat does not expose synthetic city figures; its city path retains the real cohort gate. Browser preview and live MAX client acceptance remain outstanding.
