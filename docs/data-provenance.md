# Data provenance (E3)

| Artifact | Origin | Status |
|---|---|---|
| `fixtures/receipts/water-2026-08.json` | Canonical BillData in TECHNICAL_SPEC.md §7.7, transcribed field for field | Synthetic; no personal data or actual tariff |
| `fixtures/receipts/water-2026-09.json` | §7.7 change of period to 2026-09, quantity to 6.000000, tariff to 45.000000, charge/printed totals to 270.00, and a new UUID line_id; all other fields follow the August fixture | Synthetic; no personal data or actual tariff |
| `fixtures/receipts/water-comparison.json` | Expected values in §§7.7 and 9.7: difference 70.00, quantity effect 40.00, tariff effect 30.00, rounding 0.00 | Synthetic arithmetic expectation; not evidence of consumption |
| `fixtures/receipts/demo-bill-2026-08.pdf` | Deterministically generated English `DEMO-BILL-V1` text PDF by `generate_demo_documents.py` | Synthetic educational layout; text layer only, not an actual invoice |
| `fixtures/receipts/demo-bill-2026-08.png` | Raster rendered from that PDF using pypdfium2 | Synthetic scan of the same layout, not a phone photo |
| `fixtures/receipts/demo-bill-2026-08-scan.pdf` | Image-only PDF made from that raster using ReportLab | Synthetic scan; pypdf text extraction returns empty |
| `fixtures/receipts/demo-bill-2026-09.pdf` and `.jpg` | Generator-produced September text PDF and pypdfium2 JPEG | Synthetic 6 × 45.00 = 270.00 control |
| `fixtures/receipts/demo-bill-2026-09-{adjustment,debt-payment,credit,unknown-service}.pdf` and their PNG/JPEG renderings | Generator variations of the same educational layout | Synthetic -50.00 separate adjustment, 100.00 opening debt with 80.00 payment, -30.00 credit, and an unknown service; no real billing claim |
| `fixtures/receipts/demo-bill-cropped.pdf`, `demo-bill-unreadable.png`, `unknown-layout.pdf`, `corrupt.pdf` | Generator-created missing-total, blank, unrelated and invalid inputs | Negative controls for partial/manual/error outcomes |
| `fixtures/receipts/demo-bill-2026-09-mismatch.pdf` | Generator changes printed total to 271.00 while service/current/closing remain 270.00 | Synthetic mismatch; code must preserve the printed value and report +1.00 difference |
| `fixtures/receipts/manifest.json` | Generator-produced SHA-256, byte lengths, type, representation, layout and expected fields for every sample | Local integrity/provenance record, not a quality measurement |
| `knowledge/territories.yaml` | Explicit demo territory from §7.7 and §10.2 | Synthetic; only `demo-territory` |
| `knowledge/manifest.yaml` | E0 structure from §10.2 | Contract-only; `pilot_territory_id: null` |
| `knowledge/sources.yaml`, `organizations.yaml` | Empty E0 structure from §10.2 | No verified external sources, links, deadlines or organizations claimed |
| `fixtures/receipts/e3-settlement-comparison.json` | Independently stated §9.8 values for 200.00 → 190.00 when adjustment -50.00 and payment 30.00 apply | Synthetic expected result; no real debt or payment |
| `knowledge/topics/*.yaml` | Fifteen generic topic IDs and questions from §10.1, editorial text written for E3 | No pilot-specific instructions or verified source claims; `review_after` is an editorial reminder |
| `knowledge/aliases.yaml`, `glossary.yaml` | Controlled synonyms and definitions of this application's own bill fields from §§9.4 and 10.2 | No external legal or tariff claims |
| `knowledge/source-host-allowlist.yaml` | Empty explicit allowlist pending source review | No external source URL is approved |

The address, account and organization in the receipt fixtures are obvious educational placeholders. Fixture values are not legal tariffs or evidence that an invoice is correct. The generated PDF/PNG/JPEG set does not establish recognition quality on real bills or phone photos. E2's opt-in smoke actually exercised seven synthetic raster/scan paths on local Tesseract `v5.5.3.20260724` with `eng+rus`; OCR evidence remains `needs_review`. Real source URLs, verified dates, contacts, service instructions and pilot territory require separate review before publication; no verification timestamp is inferred from file creation time. No real person or external organization is represented by the synthetic records. The E3 catalog `knowledge_version` hashes local content; its generic card review dates do not imply external source verification. No network lookup runs while answering a user question.
