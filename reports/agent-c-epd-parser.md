# C — E4 Moscow Oblast EPD parser report

- Base task SHA: `9b58db6`.
- Code SHA: `03c219f760b14ae07d05f68f39ec8428f7acf9da`.
- Branch: `agent-c/e4-epd-parser`.
- Template: `mos-oblast-epd-v1`. Existing `demo-bill-v1` remains available.

## Evidence

- `python -m unittest discover -s packages/housing_engine/tests -p 'test_*.py' -q`: 51 tests passed, including synthetic EPD extraction, comparison effects, privacy projection, malformed cells and local private EPD check.
- `python packages/housing_engine/verify_contract.py`: engine v1 schemas and fixture verifier passed.
- Local private EX.pdf through `extract_receipt`: `partial`, 19 main charge rows, 4 nonzero adjustments, 19/19 charge amounts, 19/19 quantities, 19/19 tariffs, 16 standard service codes plus 3 known other service labels. Account, management organization ID and address were found with review evidence. Printed base charge and adjustment totals reconcile with the extracted rows. No values, owner details, account, address, provider ID, source text or document bytes are included here.
- Voluntary insurance and the reference meter table are outside the parsed service list. The no-insurance total is selected; the with-insurance total is not combined with it.

## Integration contract

- Add `mos-oblast-epd-v1` alongside `demo-bill-v1` to backend `ExtractionConfig.enabled_templates`. For this text-bearing single-page layout, `extract_receipt` now returns a `BillData` with source evidence. Keep review before confirming it.
- `project_receipt_facts(bill)` exports period, normalized service labels/codes, scope, segment, unit, quantity, tariff, charge, adjustments and totals only. `project_epd_table_candidates(layout_text)` exports a bounded numeric projection from the main table only. Both exclude account, address, issuer, header, footer, raw service names, voluntary insurance and the reference meter table. The model may suggest wording or candidate cells; server validation and arithmetic remain authoritative.
- The private address is available in `BillData.address_text` for backend city classification; no city is asserted by this parser when address classification is ambiguous. Account and management organization INN are private matching fields and must not enter model prompts, logs or aggregate output.

## Limits and review

- This template covers the supplied text-bearing layout, not scans or arbitrary regional EPDs. Unknown/ambiguous rows or amounts stay partial or require manual review.
- Settlement formula, penalties, other account changes, per-service supplier, adjustment related period and character-level bounding boxes remain unsupported or null. The opening balance, credited payments and printed closing value are extracted as displayed, but the parser does not infer the debt formula.
- A `partial` result requires owner confirmation. City aggregates still require backend ownership, opt-in, same-city/month/unit filtering and minimum sample threshold.
