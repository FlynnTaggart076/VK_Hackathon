# E4-B-PREVIEW — isolated browser rehearsal

- Base/task SHA: `61080a73fd23afd6ef6031dd893196a7cf212ed3` (`main`).
- Branch and checkout: `agent-b/e4-preview`, `.checkouts/agent-b-e4-preview`.
- Code SHA: `b67abd3445edf76cb51693d182081f62d549fea0`.
- Status: code submitted for coordinator review; **no preview VM deployment yet**. Deploy only after an accepted integrated release SHA is assigned.

## Result

- Added explicit preview-only `POST /api/v1/auth/preview`. Empty body or `{}` creates a random guest user/profile and one-hour session in PostgreSQL; no client identity is accepted. Dev/demo/production return `403 PREVIEW_DISABLED`.
- `APP_MODE=preview` requires `PREVIEW_AUTH_ENABLED=true` and real engine/PostgreSQL, rejects demo auth and MAX credentials. Preview `auth/max`, MAX webhook and `auth/demo` return 403. Ordinary raw receipt upload returns `403 PREVIEW_SYNTHETIC_ONLY`; catalog sample import remains available. No live complaint submission was added.
- Added private `compose.preview.vm.yaml` with separate Compose project/network/DB/document volumes, no host ports, private-only worker, blank MAX variables, and preview web build args. `compose.preview.ci.yaml` publishes only loopback `127.0.0.1:18082` for isolated CI/local tests. Added app and shared-route Nginx snippets plus `docs/preview.md` for exact-SHA deployment, backup, restore and route checks.
- Anonymous account creation is limited by application Nginx to 12/minute plus burst 8 for the preview instance; excess returns 429. Preview guest rows cascade-delete after 31 days in batches of 100 per retention sweep, after the existing 7-day source and 30-day receipt retention.
- OpenAPI includes preview mode/route and upload refusal. Production web build defaults and `compose.vm.yaml` remain unchanged.

## Checks performed

| Level | Evidence | Result |
|---|---|
| Local backend | `.venv/Scripts/python -m pytest apps/backend/tests -q` with backend and engine on `PYTHONPATH` | `30 passed, 3 skipped, 1 warning` (10.14 s). The three skipped tests require local PostgreSQL. Includes four new preview tests for config gates, unique guests, separate profile ownership, no-body/empty-body HTTP auth, raw-upload refusal and disabled MAX/demo routes. SQLite is used only inside isolated unit tests; runtime preview rejects it. |
| Contract | Separate contract-lock virtualenv, `python scripts/check_http_contract.py` | `OK: OpenAPI 3.1; 29 operations; 25 JSON examples; engine fields linked`. |
| Static | `python -m compileall -q apps/backend/app apps/backend/tests/test_preview_auth.py`; `git diff --check` | Both exit 0. |
| VM preflight, read-only | SSH `hackathon`; `df -h /srv/team`, `free -h`, shared Compose service listing | VM reachable; `/srv/team` disk 77 GiB total, 71 GiB available; memory 15 GiB total, 14 GiB available; shared Compose lists `nginx`. No VM files, containers or routes changed by B. |
| Docker Compose/build/Nginx/HTTP | Docker CLI unavailable on this Windows host | **Not yet verified**; coordinator's Linux CI must run `docker compose config --quiet`, preview `up --build`, both app `nginx -t` configurations, PostgreSQL HTTP smoke and two-guest isolation. Do not treat local unit checks as Docker or VM acceptance. |

## Integration and next action

A consumes `POST /api/v1/auth/preview` returning the existing `AuthResponse`; meta reports `mode=preview`. A's build flags are `VITE_APP_BASE=/team/zhkh-preview/` and `VITE_PREVIEW_MODE=true`, supplied by preview Compose. C's synthetic HTTP script can verify two guest IDs, cross-owner 404, sample import and raw-upload 403. Coordinator merges the code SHA with A/C, runs the Linux Compose gate and assigns an exact accepted release SHA. B then performs §12.8 preview deployment on the VM, checks internal/public HTTPS and production sibling routes, and records evidence in a deployment follow-up report. Product E5/MAX acceptance remains open.
