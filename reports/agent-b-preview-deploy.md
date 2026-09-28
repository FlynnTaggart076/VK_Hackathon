# E4-B-PREVIEW-DEPLOY — isolated public browser preview

- Task base: `9d15927bf51abd8a8e1d67d42f67bf6a07f75ce7`.
- Accepted and deployed release: `af2b066ab7d2854dc0138a0e0ef838598d8b76b4` (clean detached VM checkout at `/srv/team/vk-hackathon/preview-deploy`). The deployment report commit is separate and is not a release SHA.
- Pre-deploy gate: [PG17/Compose CI 36436781153](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36436781153) passed on the accepted release SHA.
- Public preview: `https://flynntaggart075.asuscomm.com/team/zhkh-preview/`.

## VM change and rollback material

Preflight found no preview project, checkout, network, volumes or route. Existing production Compose project `vk-zhkh` was healthy at clean SHA `d3fa9b2fc4ea3ae89a0691c331945d2a6d1354f9`; shared `team-web` and sibling `/team/` routes responded. Disk had about 71 GiB free and RAM about 14 GiB available. Owner instructions `/srv/team/README.md`, `/srv/team/web/README.md` and local `Работа с сервером.md` were followed.

The preview runs as distinct Compose project `vk-zhkh-preview` with separate PostgreSQL 17 and document volumes, private API/worker, a web service without a published host port, and unique external network `vk-zhkh-preview-edge`. Its runtime directory `/srv/team/vk-hackathon/runtime-preview` is mode 0700; `app.env` is mode 0600, outside Git, with a newly generated password. MAX credentials are blank in preview. The VM checkout HEAD and clean status were rechecked after deployment.

Private copies and checksums of the original shared `compose.yaml` and `nginx.conf` were saved under `/srv/team/vk-hackathon/runtime-preview/backup/shared-before-20260928T143952Z`. The original files matched the copies immediately before editing. Only the preview edge network attachment and `/team/zhkh-preview` route were added to shared Nginx/Compose. Shared `docker compose config --quiet` and a disposable `nginx -t` passed before recreating only shared `nginx`; live `nginx -t` passed afterward. No external ingress or production project was modified.

The initial preview database dump `/srv/team/vk-hackathon/runtime-preview/backup/preview-initial-20260928T144223Z.dump` passed `pg_restore --list` and restored into a separate preview database. Both source and restored databases reported Alembic `e3_max_keyboard` and zero user rows at that initial snapshot. The initial preview document-volume archive `preview-sources-initial-20260928T144223Z.tar.gz` passed `tar -tzf`. Backups and runtime secrets remain private on the VM, outside Git. These snapshots precede the synthetic acceptance data.

## Verification

| Level | Result |
|---|---|
| VM runtime | Preview `api` and `db` healthy; `web` and `worker` running; `migrate` exited 0. PostgreSQL reports version `170011`. API meta reports `mode=preview`, `engine_stub=false`, and `external_submission=false`. Preview project has no published DB/API/worker/web host ports. |
| Shared HTTP | On the configured internal listener `10.203.77.10:8080`, `/team/`, `/healthz`, production `/team/zhkh/` and its `/health/ready`, preview `/team/zhkh-preview/` and its `/health/ready` all returned 200. Preview nested SPA route returned 200; missing API/asset returned 404; preview webhook without authorization returned 403. |
| Public HTTPS | Preview UI, JS asset, nested SPA route, `/health/ready` and `/api/v1/meta` returned 200 with TLS verification result 0. Production UI/ready and sibling `/team/` were also 200. Coordinator independently repeated public preview and production checks. |
| Synthetic acceptance | `PREVIEW_BASE_URL=https://flynntaggart075.asuscomm.com/team/zhkh-preview/ python packages/housing_engine/preview_acceptance.py` passed **10 checks**: preview boundary, two separate virtual guests, Moscow/MO onboarding and privacy confirmation, raw document upload blocked, two synthetic imports and review/confirmation, 200→270 comparison (40/30 factors), FAQ boundaries, copy-only draft with no sending, history and cross-guest isolation, draft/receipt deletion. No real receipt or complaint was sent. |
| Final runtime | VM preview HEAD still `af2b066ab7d2854dc0138a0e0ef838598d8b76b4`, clean; production HEAD still `d3fa9b2fc4ea3ae89a0691c331945d2a6d1354f9`, clean. Preview jobs aggregate `succeeded=3`. Sanitized API/worker log scan over the final 15-minute window found zero lines matching error/traceback/exception/failed. Live shared `docker compose config --quiet` and `nginx -t` passed. |

Public browser rehearsal by A and coordinator is tracked separately in their reports. This preview verifies synthetic product flow and isolation; it is not real receipt interpretation or final E5/MAX acceptance. Production MAX webhook/subscription and credentials were left unchanged; no MAX message or real complaint was sent.
