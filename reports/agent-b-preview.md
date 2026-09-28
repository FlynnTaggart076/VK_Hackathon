# E4-B-PREVIEW — isolated browser rehearsal

- Base/task SHA: `61080a73fd23afd6ef6031dd893196a7cf212ed3` (`main`).
- Branch and checkout: `agent-b/e4-preview`, `.checkouts/agent-b-e4-preview`.
- Initial code SHA: `b67abd3445edf76cb51693d182081f62d549fea0`.
- PostgreSQL constraint correction SHA: `d654f35d1fb7e3e546c5f226f68861402bfee672`.
- Status: corrected code submitted for coordinator review and Linux CI rerun; **no preview VM deployment yet**. Deploy only after an accepted integrated release SHA is assigned.

## Result

- Added explicit preview-only `POST /api/v1/auth/preview`. Empty body or `{}` creates a random guest user/profile and one-hour session in PostgreSQL; no client identity is accepted. The server generates a reserved `preview-<random hex>` demo identity per user, satisfying `ck_users_one_identity` while `/auth/demo` still accepts only `reviewer_a`/`reviewer_b`. Dev/demo/production return `403 PREVIEW_DISABLED`.
- `APP_MODE=preview` requires `PREVIEW_AUTH_ENABLED=true` and real engine/PostgreSQL, rejects demo auth and MAX credentials. Preview `auth/max`, MAX webhook and `auth/demo` return 403. Ordinary raw receipt upload returns `403 PREVIEW_SYNTHETIC_ONLY`; catalog sample import remains available. No live complaint submission was added.
- Added private `compose.preview.vm.yaml` with separate Compose project/network/DB/document volumes, no host ports, private-only worker, blank MAX variables, and preview web build args. `compose.preview.ci.yaml` publishes only loopback `127.0.0.1:18082` for isolated CI/local tests. Added app and shared-route Nginx snippets plus `docs/preview.md` for exact-SHA deployment, backup, restore and route checks.
- Anonymous account creation is limited by application Nginx to 12/minute plus burst 8 for the preview instance; excess returns 429. Only `preview-` guest rows cascade-delete after 31 days in batches of 100 per retention sweep, after the existing 7-day source and 30-day receipt retention.
- OpenAPI includes preview mode/route and upload refusal. Production web build defaults and `compose.vm.yaml` remain unchanged.

## Checks performed

| Level | Evidence | Result |
|---|---|
| Local backend after correction | `.venv/Scripts/python -m pytest apps/backend/tests -q` with backend and engine on `PYTHONPATH` | `30 passed, 4 skipped, 1 warning` (9.89 s). The extra skipped test requires `TEST_PREVIEW_POSTGRES_URL` pointing to isolated PostgreSQL 17. It creates an Alembic test schema, confirms the actual check constraint, two guest inserts and preview-only stale-user cleanup. SQLite is used only inside other isolated unit tests; runtime preview rejects it. |
| Contract | Separate contract-lock virtualenv, `python scripts/check_http_contract.py` | `OK: OpenAPI 3.1; 29 operations; 25 JSON examples; engine fields linked`. |
| Static | `python -m compileall -q apps/backend/app apps/backend/tests/test_preview_auth.py`; `git diff --check` | Both exit 0. |
| VM preflight, read-only | SSH `hackathon`; `df -h /srv/team`, `free -h`, shared Compose service listing | VM reachable; `/srv/team` disk 77 GiB total, 71 GiB available; memory 15 GiB total, 14 GiB available; shared Compose lists `nginx`. No VM files, containers or routes changed by B. |
| Docker Compose/build/Nginx/HTTP | Initial integrated [run 36434454832](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36434454832) at `b65958a` | CI reached route/assets/deep link/readiness, then preview auth failed: PostgreSQL rejected a guest with both identity fields NULL under `ck_users_one_identity`; API returned 503. Corrected in `d654f35`; **rerun pending**. Local Windows host has no Docker CLI. The targeted PG17 test needs `TEST_PREVIEW_POSTGRES_URL` set inside the disposable preview CI container to its `DATABASE_URL`, without logging the value. |

## Integration and next action

A consumes `POST /api/v1/auth/preview` returning the existing `AuthResponse`; meta reports `mode=preview`. A's build flags are `VITE_APP_BASE=/team/zhkh-preview/` and `VITE_PREVIEW_MODE=true`, supplied by preview Compose. C's synthetic HTTP script can verify two guest IDs, cross-owner 404, sample import and raw-upload 403. Coordinator merges the code SHA with A/C, runs the Linux Compose gate and assigns an exact accepted release SHA. B then performs §12.8 preview deployment on the VM, checks internal/public HTTPS and production sibling routes, and records evidence in a deployment follow-up report. Product E5/MAX acceptance remains open.
