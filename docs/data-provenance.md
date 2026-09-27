# Data provenance (E0)

| Artifact | Origin | Status |
|---|---|---|
| `fixtures/receipts/water-2026-08.json` | Canonical BillData in TECHNICAL_SPEC.md §7.7, transcribed field for field | Synthetic; no personal data or actual tariff |
| `fixtures/receipts/water-2026-09.json` | §7.7 change of period to 2026-09, quantity to 6.000000, tariff to 45.000000, charge/printed totals to 270.00, and a new UUID line_id; all other fields follow the August fixture | Synthetic; no personal data or actual tariff |
| `fixtures/receipts/water-comparison.json` | Expected values in §§7.7 and 9.7: difference 70.00, quantity effect 40.00, tariff effect 30.00, rounding 0.00 | Synthetic arithmetic expectation; not evidence of consumption |
| `knowledge/territories.yaml` | Explicit demo territory from §7.7 and §10.2 | Synthetic; only `demo-territory` |
| `knowledge/manifest.yaml` | E0 structure from §10.2 | Contract-only; `pilot_territory_id: null` |
| `knowledge/sources.yaml`, `organizations.yaml`, `glossary.yaml`, `aliases.yaml` | Empty E0 structure from §10.2 | No factual content, links, review dates, deadlines or organizations claimed |

The address, account and organization in the receipt fixtures are obvious educational placeholders. Fixture values are not legal tariffs or evidence that an invoice is correct. There is no original PDF/image to match against at E0. Real source URLs, verified dates, contacts, service instructions and pilot territory require separate review before publication; no verification timestamp is inferred from file creation time. No real person or external organization is represented by the synthetic records.
