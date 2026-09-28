# Browser preview at `/team/zhkh-preview/`

This is an isolated, public **synthetic-only** rehearsal before organizer binding. It is not the MAX mini-app acceptance route. The regular `/team/zhkh/` Compose project, database, document volume, bot credentials, and MAX webhook remain separate.

## Runtime contract

- Preview Compose project: `vk-zhkh-preview`, with its own `postgres_data` and `source_documents` named volumes. Do not combine with `vk-zhkh`.
- API: `APP_MODE=preview`, `PREVIEW_AUTH_ENABLED=true`, `ENGINE_MODE=real`, `APP_ROOT_PATH=/team/zhkh-preview`. The API fails startup when preview mode or opt-in is missing, demo auth is enabled, or any MAX credential is present.
- Anonymous `POST /api/v1/auth/preview` accepts no body or `{}` and creates a random new PostgreSQL user, profile and one-hour bearer session per call. The browser keeps the token in tab session storage. A new tab gets a different owner. Production returns `403 PREVIEW_DISABLED`.
- Raw `POST /api/v1/receipts` returns `403 PREVIEW_SYNTHETIC_ONLY` in preview. Use the included `/api/v1/receipts/demo` synthetic examples; do not upload personal receipts. Manual edits of a synthetic sample, comparison, FAQ and draft copying remain available. External complaint submission, voice and MAX calls are absent.
- The app Nginx caps anonymous account creation at 12 requests/minute with burst 8 (shared limit for this one preview instance). Excess returns 429. Existing 7-day source and 30-day receipt retention still apply. Preview guest users and their remaining derived rows are removed after 31 days in bounded batches. This is a public test endpoint; use only synthetic data.
- `compose.preview.vm.yaml` publishes no host port. Its worker stays on the internal private network and all MAX variables are blank. The web image uses `VITE_APP_BASE=/team/zhkh-preview/` and `VITE_PREVIEW_MODE=true` only for this build. Production build defaults remain `/team/zhkh/` and `false`.

## Accepted-SHA deployment on the prepared VM

B performs these steps only after the coordinator accepts the exact release SHA. Follow the local VM owner instruction and `TECHNICAL_SPEC.md` §12.8. Work only in `/srv/team`; preserve current shared Compose/Nginx routes and other projects. Preflight `/team/` and `/healthz`, disk/memory, active containers/networks and files. Save private timestamped copies and checksums of `/srv/team/web/{compose.yaml,nginx.conf}`. Use a separate clean checkout such as `/srv/team/vk-hackathon/preview-deploy` at `RELEASE_SHA` with `git status --porcelain` empty. Keep `/srv/team/vk-hackathon/runtime-preview/app.env` outside Git, owned by the operator, directory mode `0700`, file mode `0600`; it needs a new URL-safe `POSTGRES_PASSWORD` distinct from production. Do not print Compose's resolved configuration or any secret.

After confirming no name collision, create the external `vk-zhkh-preview-edge` Docker network. From the preview checkout:

```sh
docker compose --env-file ../runtime-preview/app.env -p vk-zhkh-preview \
  -f compose.yaml -f compose.preview.vm.yaml config --quiet
docker compose --env-file ../runtime-preview/app.env -p vk-zhkh-preview \
  -f compose.yaml -f compose.preview.vm.yaml up --build -d
docker compose --env-file ../runtime-preview/app.env -p vk-zhkh-preview \
  -f compose.yaml -f compose.preview.vm.yaml ps
```

Verify migration completion, PostgreSQL 17, API readiness, web `nginx -t`, and that DB/API/worker have no host ports. Add **only** the new network attachment for the shared Nginx service in the current `/srv/team/web/compose.yaml`, and the two preview locations from `infra/nginx/team-web-preview-route.conf.example` to the current server in `/srv/team/web/nginx.conf`. Inspect the live files first and retain concurrent changes. Start the preview web before checking shared Nginx DNS. In `/srv/team/web`, run `docker compose config --quiet`, `docker compose run --rm --no-deps -T nginx nginx -t`, then recreate only `nginx` and inspect `docker compose ps`. Do not use `down -v`, global prune, Docker daemon restart, or external ingress changes.

Check internal `http://10.203.77.10:8080/team/zhkh-preview/`, its asset, deep link, `/health/ready`, `/api/v1/meta` with `mode=preview`, anonymous login, two-guest isolation, synthetic import and raw-upload denial. From a development machine check the same paths through public HTTPS at `https://flynntaggart075.asuscomm.com/team/zhkh-preview/`. Also recheck production `/team/zhkh/`, sibling `/team/` and `/healthz`. Record internal VM, external HTTPS and live MAX evidence separately. The preview URL is for browser rehearsal and must not be submitted as the organizer mini-app binding URL.

## Backups and recovery

Before a preview update, record old and new SHA; take a private `pg_dump -Fc` of **preview** DB and a private preview source-volume archive, verify `pg_restore --list`, then restore into a separate test database and check `alembic_version` and row counts. Keep the production backup process separate. For route failure, revert only the preview additions to current shared Nginx files using the saved copy/diff after preserving any concurrent edits; validate and recreate only shared `nginx`. For app rollback, point the clean preview checkout to its recorded previous SHA and recreate only `vk-zhkh-preview` services after checking migration compatibility on the restore DB. Never overwrite the live preview DB with an old dump after new sessions or receipts without a separate owner decision.

## Local/CI HTTP check

When Docker is available, create `vk-zhkh-preview-edge` locally and use `compose.preview.ci.yaml` as the third Compose file. This override publishes only `127.0.0.1:18082` and uses a local Nginx rewrite for the public prefix. Set a private `POSTGRES_PASSWORD`; run `config --quiet` and a synthetic HTTP smoke against `http://127.0.0.1:18082/team/zhkh-preview`. Do not apply this override on the VM.
