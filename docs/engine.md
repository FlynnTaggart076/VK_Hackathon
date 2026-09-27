# Housing engine: contract v1 (E0)

This checkpoint publishes the Python DTO and JSON Schema used by B's adapter. It does not implement OCR, validation, explanation, comparison, FAQ or draft generation. The seven functions in `housing_engine.__init__` have the specified signatures and currently raise `NotImplementedError`; B must use its explicit dev stub until an integrated engine release is accepted.

## Reproducible local check

From the repository root on Python 3.12 or 3.13:

```powershell
python -m venv packages/housing_engine/.venv
& .\packages\housing_engine\.venv\Scripts\python.exe -m pip install -r packages/housing_engine/requirements.lock
& .\packages\housing_engine\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e packages/housing_engine
& .\packages\housing_engine\.venv\Scripts\python.exe packages/housing_engine/verify_contract.py
& .\packages\housing_engine\.venv\Scripts\python.exe -m unittest discover -s packages/housing_engine/tests -v
```

The `.venv` directory is ignored by the package's `.gitignore`. On Linux, use `packages/housing_engine/.venv/bin/python` for the same commands. `verify_contract.py` needs no DB, MAX, HTTP, network or secrets after installation. It validates the checked-in Draft 2020-12 schemas against Pydantic, validates both receipt fixtures and all knowledge YAML, and checks the exact 200.00 → 270.00 decomposition. Any invalid fixture or changed expected result exits nonzero; the unittest changes an isolated copy of the August fixture and checks this failure path. Schemas can be regenerated intentionally with `python packages/housing_engine/verify_contract.py --write-schemas` after a reviewed DTO change.

## Contract boundary

The only public calls are `extract_receipt`, `validate_bill`, `explain_receipt`, `compare_receipts`, `answer_question`, `compose_draft`, and `load_knowledge` (§8.2). Calls are synchronous and return Pydantic DTO, not HTTP responses. `EngineError(code,message,retryable)` reserves the eight codes in §8.3; messages must be safe to show to users. E0's `NotImplementedError` is a stage marker, not a runtime error mapping.

`DocumentInput.content` is in-memory bytes, never user JSON. `ExtractionConfig.workspace` is a trusted temporary job directory provided by B. Future C code may create files only underneath that directory; it must not read a path supplied by a user or make network requests while processing. B owns file storage, preview, subprocess supervision, user/ownership checks, queues, HTTP envelopes and MAX auth. B also owns the server-only fields `id`, `created_at`, `stale`, `stale_reasons`, and `dataset_kind` of AnswerView; `dataset_kind` of ComparisonResult; and persisted draft IDs, revisions, timestamps and stale status. B decides dataset kind from stored provenance, not from receipt text. `receipt_ref` in a request always refers to a confirmed, current revision after B's check.

DTO JSON keys use snake_case. BillData has `schema_version="1.0"`; schemas are in `contracts/engine/v1`. Every field is required unless a default is stated, with explicit `null` for unknown values. Input models reject extra keys. Money is a signed decimal string with two fractional digits, DecimalValue is a decimal string with up to six fractional digits, Period has a valid month, and UUIDs are string-encoded in JSON. Float money and guessed zeroes are invalid. Structural and cross-field business checks are the E1 `validate_bill` task; a schema-valid BillData is not necessarily confirmable.

`demo-bill-v1` is the synthetic layout represented by the two JSON fixtures in `fixtures/receipts`. It has one current-period cold-water line, no separate adjustments, a signed balance with printed current charges, closing balance and amount due. Its line amount excludes separately represented adjustments. This describes test data only: no PDF/photo sample or OCR adapter exists in E0, and no real issuer, tariff, territory or document format is claimed supported.

The initial knowledge catalog has only `demo-territory`, no sources, no organizations, and no topic cards. `pilot_territory_id` remains `null` until a real territory and sources are reviewed. `contracts/engine/v1/knowledge/*.schema.json` formalizes the manifest, sources, territories, organizations, topic cards, glossary and aliases. A topic card must carry the applicability, `source_ids`, `review_after` and `content_version` described in §10.2. The E0 manifest is not a ready FAQ catalog; `load_knowledge` remains unimplemented and an empty content set must not be served as a supported answer.
