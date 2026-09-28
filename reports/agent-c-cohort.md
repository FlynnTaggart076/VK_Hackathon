# C — E4 city cohort arithmetic report

- Coordinator task SHA: `632a19b`.
- Branch base: `4220f49ae373cac8a28e665968706553492a48f2`.
- Code SHA: `9f03f6d93ce0a2758b21314c692406019bbc6f13`.
- Branch: `agent-c/e4-epd-parser`.

## Pure helper contract

Import `CohortKey`, `CohortObservation` and `summarize_cohort` from `housing_engine`. The key contains canonical city slug, period, service code, scope, segment, unit and metric (`charge_amount` or `tariff`). Each observation additionally contains an opaque contributor key, dataset kind (`real` or `synthetic`), Decimal or canonical decimal value, and confirmed/opted-in flags.

The helper filters exact cohort fields, real data, confirmation and opt-in. An identical repeated contributor value counts once; conflicting values for one contributor return `ambiguous_data` with no count or statistics. Fewer than five distinct contributors return `insufficient_data` with `sample_size`, average and median all `None`. Successful output includes sample size, average, median, month, metric, unit and fixed provenance. Only final displayed mean and median are rounded: two decimals for charge amount, six for tariff. It returns no source row, contributor key, user ID, account, address or receipt text.

B must supply an unambiguous canonical city slug. The helper rejects full-address text, but cannot determine whether a valid-looking slug names a city or a region. Scope `unspecified`, unit `other`, or missing segment for hot water/electricity suppresses the result as `ambiguous_data`.

## Checks

- `python -m unittest discover -s packages/housing_engine/tests -p 'test_*.py' -q`: 60 tests passed, including 9 new synthetic cohort tests.
- `python packages/housing_engine/verify_contract.py`: passed.
- Cases cover five contributors, four suppressed, identical/revised duplicates, conflicting duplicate values, other month/city/service/scope/segment/unit/metric, synthetic/unconfirmed/non-consenting exclusion, invalid decimal rejection, deletion recomputation and final rounding.

## Backend handoff and limits

B selects only current confirmed opted-in real receipt revisions in PostgreSQL, enforces ownership and deletion, maps a verified city to its slug, and passes one row per contributor where possible. Re-run the helper after deletion; do not cache a stale public count. Any model response can describe only returned aggregate facts, never compute or receive underlying user rows. The helper has no database, model, MAX or VM integration.

No real multi-user city cohort has been observed or claimed. The synthetic test population is only an arithmetic and privacy check.
