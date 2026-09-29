# C — release 005015c engine/backend verification

- Base: imported owner release `47303838d40613c1cae24fe959e2fb4eae40ba47`.
- Branch: `agent-c/verify-005015c`.
- Portability fix: `87720230482c65a2da32d30ed35b3111114ae987` (pushed).

The imported service catalog, EPD scope correction, issue rebasing and store revision path passed the available tests. Review of `rebase_issues` and `SqlStore.edit_revision` found no further reproducible blocker in this checkout. The audit's PostgreSQL concern was not reproduced locally because there is no local PostgreSQL; the coordinator's CI covers that gate.

## Verification

- Python 3.13 virtual environment from `apps/backend/requirements.lock`, editable `packages/housing_engine`; contract script dependencies installed separately.
- `pytest packages/housing_engine/tests -q`: **74 passed**.
- `pytest apps/backend/tests -q` with `PYTHONPATH=apps/backend`: **74 passed, 6 skipped** (PostgreSQL-dependent checks).
- `packages/housing_engine/verify_contract.py`: **OK** after the manifest fix.
- `scripts/check_http_contract.py`: **OK**, OpenAPI 3.1, 33 operations, 25 examples.
- Every staged manifest sample's byte count and SHA-256 matched its staged Git blob; `git diff --cached --check` passed.

## Fix and boundary

The manifest used Windows CRLF byte counts and hashes for three JSON fixtures, while their Git blobs contain LF. A clean Linux checkout would fail `verify_contract.py`. `.gitattributes` now forces LF only for `water-2026-08.json`, `water-2026-09.json` and `water-comparison.json`; the manifest records those Git blob bytes. Existing fixture content and engine/backend behavior are unchanged.

No VM, remote service or real user data was touched. This report does not claim PostgreSQL, MAX or browser acceptance; those are coordinator CI/deployment gates.
