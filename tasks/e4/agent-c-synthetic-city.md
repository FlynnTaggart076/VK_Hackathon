# E4 contract: numeric synthetic city comparison in isolated preview

This is an implementation contract for A (web) and B (API). It does not accept or merge synthetic data into the real city cohort. The owner permits synthetic results for preliminary testing. Current `water-2026-08/09` samples say **«Учебный город»**; they cannot truthfully represent Moscow or a Moscow Oblast city.

## Demo data and eligibility

- C supplies four explicitly synthetic receipt snapshots: `city-moscow-water-2026-08`, `city-moscow-water-2026-09`, `city-lyubertsy-water-2026-08`, `city-lyubertsy-water-2026-09` under `fixtures/receipts/`. B must add these exact IDs to the preview catalog/import allowlist and verify the import job operation key. Keep the existing generic samples unchanged. Moscow has city key `moskva` and territory `moscow`; Lyubertsy, Moscow Oblast, has key `lyubertsy` and territory `moscow-oblast`. Each has one `cold_water` / `individual` / `segment_key=null` / `m3` line. All identifiers and addresses in these files are invented for the demo; no real resident, account, source PDF or address enters the cohort fixture.
- Allow only an authenticated preview guest's **own confirmed** allowlisted synthetic receipt on the endpoint below. Require `APP_MODE=preview`, `dataset_kind=synthetic`, one eligible service line, a known month/city, and profile territory matching the receipt. Other receipts return `ineligible`; foreign receipt IDs return 404. Current generic «Учебный город» samples remain usable elsewhere but are `ineligible` for this Moscow/MO comparison.
- Fixed cohort records are *artificial entries*, not residents or five independent users. `fixtures/receipts/city-preview-cohort-v1.json` is the sole numeric source. It has `{schema_version:"1.0", kind:"synthetic_preview_cohort", groups:[...]}`; each group has `fixture_id`, `city`, `territory_id`, `period`, `service_code`, `scope`, `segment_key`, `unit`, and five `observations` with decimal-string `quantity`, `tariff`, `charge_amount`. Group keys are unique and match the four personal demo snapshots. Do not write these entries to `receipt_cohort_lines`, query real user rows, or alter real `summarize_cohort` filtering.

### Fixed synthetic cohort v1

Each row group has five artificial charge values (RUB), one for each fixed quantity; tariff is uniform within the group. All numbers are illustrative, not observed Moscow/MO tariffs or city averages.

| City key / display | Period | Quantities, m3 | Tariff, RUB/m3 | Charges, RUB | Average charge | Median charge |
| --- | --- | --- | ---: | --- | ---: | ---: |
| `moskva` / Москва (учебная выборка) | 2026-08 | 4, 5, 6, 7, 10 | 40.000000 | 160, 200, 240, 280, 400 | 256.00 | 240.00 |
| `moskva` / Москва (учебная выборка) | 2026-09 | 5, 6, 7, 8, 12 | 45.000000 | 225, 270, 315, 360, 540 | 342.00 | 315.00 |
| `lyubertsy` / Люберцы, МО (учебная выборка) | 2026-08 | 4, 5, 6, 7, 10 | 38.000000 | 152, 190, 228, 266, 380 | 243.20 | 228.00 |
| `lyubertsy` / Люберцы, МО (учебная выборка) | 2026-09 | 5, 6, 7, 8, 12 | 42.000000 | 210, 252, 294, 336, 504 | 319.20 | 294.00 |

For `tariff`, both average and median equal the listed six-decimal tariff. The personal demo row may use the second charge in its group (Moscow 200/270; Lyubertsy 190/252) so personal and synthetic cohort values are comparable by city, period, service and unit. Server arithmetic uses `Decimal` and rounds only at the display boundary. A missing/ambiguous key or fewer than five fixture records yields no numbers and no exact subthreshold count.

## Separate preview HTTP contract

`GET /api/v1/preview/receipts/{id}/city-comparison?service_code=cold_water&metric=charge_amount|tariff`

The path is disabled outside `APP_MODE=preview` or without `PREVIEW_AUTH_ENABLED=true` (403 `PREVIEW_DISABLED`). It uses the existing bearer session and owner lookup. B proves provenance with `Job.kind=demo_import` and an exact allowlisted `operation_key` for one of the four fixture IDs. Keep `GET /api/v1/receipts/{id}/city-comparison` unchanged: it continues to exclude synthetic receipts and to use only confirmed real, opted-in records.

Return a distinct `PreviewCityComparisonView` with exactly these fields:

| Field | Value |
| --- | --- |
| `status` | `available`, `insufficient_data`, `ambiguous_city`, or `ineligible` |
| `city`, `period`, `service_code`, `scope`, `segment_key`, `unit`, `metric` | Canonical city key, YYYY-MM, `cold_water`, `individual`, null segment, `m3`, `charge_amount` or `tariff` when eligible; nullable dimensions for unavailable cases |
| `city_label` | Display name `Москва` or `Люберцы (Московская область)`, never an unmarked statistical claim. |
| `sample_size`, `average`, `median` | `5` and formatted aggregate strings only for `available`; otherwise all `null` |
| `receipt_value`, `difference_from_average`, `difference_percent`, `comparison` | Own confirmed line value, own-minus-average amount, percent of average, and `above`/`equal`/`below` when comparable; otherwise `null`. The own value comes from the owned receipt, not from a cohort observation. |
| `explanation` | Short user-facing wording that explicitly says the figures are a synthetic training sample, not actual city residents or tariffs. |
| `provenance` | Constant `synthetic_preview_cohort` for every response, including unavailable states |

`sample_size` means *five artificial records*; it is never described as five people, five real receipts or five consenting residents. The response contains no source row, contributor key, user ID, account, address, receipt text or real cohort data. Use separate OpenAPI schema/TypeScript type; do not widen the real `CityComparisonView.provenance` constant `confirmed_opted_in_real_receipts`.

## A/B integration and checks

- B: implement the mode and owner gates, fixture allowlist, profile-city match, Decimal aggregate and separate response. Load only `city-preview-cohort-v1.json` as the preview numeric source. Tests cover both cities/months/metrics and expected averages/medians; 4 entries suppress count/values; unconfirmed/generic/manual/foreign receipt handling; disabled route in production; and no `ReceiptCohortLine` insertion or real-cohort result change. Keep `apps/backend/tests/test_e4_city_cohort.py` passing, especially synthetic exclusion and consent/deletion behavior.
- A: when `PREVIEW_MODE` and the selected receipt is synthetic, call only the preview endpoint. Show a persistent «Синтетическая учебная выборка — не данные жителей Москвы/МО» badge and label `sample_size` as «учебных записей»; keep prior-month comparison limited to the immediate preceding month, same city/service/unit/provenance. In production, synthetic preview provenance must not pass the numeric display gate. Test provenance gating, badge/copy, suppression and both-month mobile flow in `apps/web/src/ui/CityComparison.test.ts` and browser acceptance.
- The MAX/chat `_city_answer` path currently rejects synthetic receipts. This contract covers the **mini-app preview screen**; any synthetic chat response needs its own explicit preview-only wording and test before enabling it.
- B deploys only an accepted release SHA to isolated preview after CI and browser checks. A local contract or synthetic fixture is not VM/MAX acceptance.
