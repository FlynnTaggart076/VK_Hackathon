# C — E4 isolated synthetic city preview data

- Branch: `agent-c/e4-synthetic-city-contract`.
- Base SHA: `ea24d1f3fd52363220eab08c86bc2fabc7703751` (`origin/main` at checkout creation).
- Fixture, contract and test SHA: `8f637cfb0db3a212cc61e52886cac688e31690e9` (pushed).
- Follow-up task: `tasks/e4/synthetic-city-preview.md` on main; C contract: `tasks/e4/agent-c-synthetic-city.md`.

## Delivered

Four invented BillData snapshots are in `fixtures/receipts/`:

| Fixture ID | City / territory | Period | Personal cold-water charge |
| --- | --- | --- | ---: |
| `city-moscow-water-2026-08` | `moskva` / `moscow` | 2026-08 | 200.00 RUB |
| `city-moscow-water-2026-09` | `moskva` / `moscow` | 2026-09 | 270.00 RUB |
| `city-lyubertsy-water-2026-08` | `lyubertsy` / `moscow-oblast` | 2026-08 | 190.00 RUB |
| `city-lyubertsy-water-2026-09` | `lyubertsy` / `moscow-oblast` | 2026-09 | 252.00 RUB |

Each has one `cold_water` / `individual` / null segment / `m3` line and invented issuer, account and address. The two months pair only within the same city. The existing generic `water-2026-08/09` fixtures were not changed and remain city-ineligible.

`fixtures/receipts/city-preview-cohort-v1.json` is a separate machine-readable preview cohort source. It has four exact city/month groups, each with five artificial quantity, tariff and charge entries. Expected charge means/medians: Moscow 256.00/240.00 (August), 342.00/315.00 (September); Lyubertsy 243.20/228.00 (August), 319.20/294.00 (September). These are illustrative values, not real city tariffs, residents or statistics. The personal demo charge equals the second artificial observation per group.

## Checks

- `python -m unittest discover -s packages/housing_engine/tests -q`: 63 passed, including 3 new fixture/schema/arithmetic tests.
- `python packages/housing_engine/verify_contract.py`: passed.
- `git diff --cached --check`: passed before commit.
- The new tests validate each BillData against the published JSON schema and Pydantic DTO, confirm line/total reconciliation, exact city/month/service keys, five observations and Decimal charge/aggregate arithmetic, and preserve generic citylessness.

## Handoff and limits

B owns the separate preview-only route, exact fixture import allowlist and job provenance check, owner/confirmation gates, numeric JSON loading and isolation from the real cohort table. A owns the clearly labeled preview UI and matching previous-month flow. A and B received the fixture IDs, response contract and pushed code SHA.

No backend, web, VM, MAX or real user cohort was changed by this C commit. Acceptance still requires integrated API/UI tests and preview deployment from an accepted release SHA; real city statistics remain governed by the separate opted-in real-cohort path.
