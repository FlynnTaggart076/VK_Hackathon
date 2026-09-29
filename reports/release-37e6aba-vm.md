# VM release 37e6aba: shared dialogue and house lookup, 2026-09-29

Release SHA: `37e6abadb185ac384227dc9edda61fc9f5295ecc` (`origin/main`). The previous production and preview ran `b9032d5`. Deployed at the owner's request; the change request is in [docs/change-request-dialog-house-lookup.md](../docs/change-request-dialog-house-lookup.md).

## Steps

1. **Preflight.**
   - Checked: disk 70G free, RAM 14Gi available.
   - Production, preview and the sibling `/team/` returned 200.
   - Shared Nginx and `/srv/team/web` were not changed; the application routes already existed.
2. **New clean checkouts.** Detached worktrees `deploy-release-37e6aba` and `preview-release-37e6aba` were created from `deploy/.git` as `artem`. Both have an empty `git status`. Following the documented permission rule, files got `a+r` and directories `a+rx`, excluding `.git`. Old release worktrees are kept as rollback points.
3. **Env.** Private `runtime/app.env` (mode 0600) gained:
   - `HOUSESCORE_API_KEY`, passed over SSH stdin and never printed;
   - `HOUSESCORE_DAILY_LIMIT=30`;
   - `HOUSE_LOOKUP_USER_DAILY_LIMIT=5`.

   A copy of the previous file is saved as `app.env.bak-before-37e6aba`. `compose.preview.vm.yaml` forces an empty key for preview.
4. **Backups** in `runtime/backup/predeploy-37e6aba-20260929T165734Z` and `runtime-preview/backup/predeploy-37e6aba-20260929T165734Z` (mode 0600):
   - `pg_dump -Fc` passed `pg_restore --list`;
   - storage archives passed `tar -tzf`;
   - full restore of the production dump into the separate DB `zhkh_restore_37e6aba` gave `e4_city_cohort` (the pre-deploy revision); the live DB was not touched.

   Incident: a first backup attempt at `…T1656Z` was removed by my own cleanup line before the final set above was taken. No older backup was affected.
5. **Rollout.** For both stacks: `config --quiet`, then `up --build -d`.
   - `migrate` exited 0 in both stacks.
   - Both live DBs are at `e5_dialog_state`.
   - Compose labels point to the new worktrees.
6. **Cache seed.** The prototype's saved HouseScore/Dominfo answers (16 files, no credentials) were copied into both `source_documents` volumes at `/storage/house_cache`, owned by `app:app`. They are not in Git.

## Checks

- **Internal `10.203.77.10:8080`:** production and preview readiness 200; `/team/` 200; `/healthz` 200.
- **External HTTPS:**
  - production root, deep link `/assistant`, readiness and JS asset return 200;
  - an unknown API path returns 404;
  - an unsigned webhook returns 403;
  - the preview root returns 200;
  - `meta` reports `mode=production`, `dialog=true`, `house_lookup=true`, `demo_auth=false`, `engine_stub=false`.
- **Preview over public HTTPS (synthetic guest):** «контакт поставщика» → Электричество → «Люберцы» → street and house → card with the managing company, its phone, and the supplier from the seeded cache. «Где передать показания?» asks the service. «Справка о составе семьи» ends with an honest limitation plus a «Контакты УК» option. The DeepSeek consent buttons are shown.
- **Production live HouseScore:**
  - production `api` and `worker` reach `housescore.ru`; `/api/user/stats` returned 200 and showed 18/100 used before the test;
  - one live lookup of a house not in the cache took 4 requests and 1.2 s, and built the management card;
  - `external_usage` recorded 4.
- **Logs and queues:** no error lines in `api` or `worker` logs of either stack since start; worker heartbeat 0–1 s; bot inbox has no queued items.

## Known limits

- **Dominfo is unreachable from the VM network.** TLS to its Cloudflare addresses times out over IPv4 and IPv6, both from the host and from containers; from the developer machine it returns 200. For new houses, the managing company and its contacts still come from HouseScore. Suppliers per service show «не удалось найти» with the GIS ЖКХ route; seeded or cached houses keep their suppliers. The fix is outside the project: VM egress or proxy.
- **HouseScore quota:** about 78 requests left on the key; one new house costs about 4. Limits are 30 live requests per day globally and 5 new addresses per user per day.
- **Not checked:**
  - a live DeepSeek call with the new `extract()` prompt;
  - real MAX Web/Android sessions;
  - off-VM backup.
