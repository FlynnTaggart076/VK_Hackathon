# B — VM reboot recovery and persistent service policy

Base accepted release: `85e81df0b232e3a664af7773661533967e2d4d77`. Code branch: `agent-b/e4-restart-policy`, code commit `789cbd13c2c1d5d87842c4174816f421d73f1cd5`. This is a restart-policy follow-up, **not a deployed release**.

## Incident and preservation

- VM `hackathon` booted at `2026-09-29 05:03:25 UTC`; Docker became active at `05:03:36 UTC`. Existing production and preview db/api/worker/web exited with code 255 around `05:03:33 UTC` because their restart policy was `no`. Shared `team-web-nginx-1` had `unless-stopped` but entered a restart loop: `host not found in upstream "vk-zhkh-web"`. The internal `/team/` and `/healthz` were connection refused; public paths returned 502.
- Another operator restored the existing production and preview stacks around `05:15 UTC` and adjusted the shared Nginx to resolve app upstreams at runtime. Internal `/team/`, production ready and preview ready then returned 200. The existing VM checkouts remain at old SHAs `d3fa9b2` and `af2b066` with another operator's uncommitted restart-policy changes; shared `nginx.conf` also changed. B preserved those files and did not run `up`, migrations, or modify common Nginx.
- Closed backups were created in each environment's `runtime*/backup/release-20260929T051322Z` outside Git. Backup directories are 0700; dumps, source archives and logs are 0600. Production cold PG/source volume archives completed before DB restart. A preview cold archive attempt was interrupted during the parallel restore and is **not** counted as a valid backup.

## Verified backups and current data

- Fresh live `pg_dump -Fc`: production 32,949 bytes, preview 40,637 bytes; `pg_restore --list` passed for both. Independent restore into `zhkh_restore_20260929_052929` and `zhkh_preview_restore_20260929_052929` passed. Both restored databases have Alembic `e3_max_keyboard`; production has 0 receipts and 1 profile, preview has 8 receipts and 17 profiles. No personal rows were printed. The restore test databases remain inside their respective private PostgreSQL containers and are not used by the app.
- Production and preview source-document volume archives both passed `tar -tzf` after the live restore. Backup files remain on the same VM, so off-VM disaster recovery is still outside this check.

## Git fix and checks

- Only persistent services `db`, `api`, `worker`, `web` in `compose.vm.yaml` and `compose.preview.vm.yaml` gain `restart: unless-stopped`. One-shot `migrate` remains without a restart policy. The VM network verifier asserts this; preview Compose CI invokes the assertion.
- On Windows, YAML merge and restart assertions passed for both overrides; Python compilation and `git diff --check` passed. Docker is unavailable on Windows.
- A new **clean** VM review worktree at `/srv/team/vk-hackathon/restart-review-789cbd1` exactly matched code SHA `789cbd1` with empty `git status`. From that worktree, production and preview `docker compose ... config --quiet` passed with their respective private env files. Production network/isolation verifier and both restart-policy checks passed. No resolved Compose configuration or secret was printed.

## Release gate

Do not update either running stack from the previous `85e81df` release: its Compose files would remove the emergency restart settings. Coordinator must accept this fix and issue a new release SHA. Then B can create clean production/preview deploy checkouts at that SHA, complete migration and app checks, and keep the currently healthy shared Nginx untouched unless a tested route change is needed. Preview synthetic receipts still do not provide a numerical real-city cohort; that limitation must be shown honestly.
