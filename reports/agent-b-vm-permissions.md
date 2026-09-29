# B: VM image permission incident and follow-up

Code commits: `bf9a0cddc9f3427e4bd7bbb584b881c69129e588` and `28c8a34f211531ac4ca577d2d8db3e71f3bb7d35` on `agent-b/e4-vm-permissions`.
CI follow-up code: `a09fffdf623b442e645688b1593d1d8d871424bc`.
Base release: `c0784c7abd3dbf63754d3403e15730eaaec11770`.

## VM state and recovery, 2026-09-29 UTC

- The accepted release was checked out in two new, clean, detached worktrees at the exact base SHA. The old production and preview checkouts retain another operator's uncommitted restart-policy edits; the shared Nginx configuration was not changed.
- Production and preview PostgreSQL custom-format dumps were saved in private `predeploy-c0784c7-20260929T0600Z` backup directories with mode `0600`. Both passed `pg_restore --list` inside their PostgreSQL containers. Earlier, separate private restore databases had verified full restores from the pre-release dumps. Source-volume archives were also retained. No live database was restored or overwritten.
- `DEEPSEEK_API_KEY` was transferred from the locally ignored file into the separate production and preview runtime `app.env` files, each mode `0600`. The temporary transfer file was removed. Neither key nor resolved Compose configuration was printed or committed.
- Production Compose build succeeded, but its one-shot migration exited 255 with `No 'script_location' key found in configuration`. Its image copied `/workspace/alembic.ini` with mode `0660`, owned by root; `USER app` could not read it. The new checkout had mode `0660`, while the prior checkout's ini was mode `0664`. The production database remained at `e3_max_keyboard`; no release migration was applied. Preview deployment was not started.
- Production `api`, `worker`, and `web` were rebuilt and started from the previous checkout HEAD `d3fa9b2fc4ea3ae89a0691c331945d2a6d1354f9` with `--no-deps`; the production DB and migrate service were not run or rolled back. Container Compose labels point to that previous checkout, and all four persistent services have `unless-stopped`. Production readiness, preview readiness, and the sibling `/team/` returned HTTP 200 internally; the coordinator independently confirmed public HTTPS 200.

## Fix and validation gate

- The backend Dockerfile now gives `/workspace` to group `app` for reading, including directories, and checks Alembic, engine, knowledge and fixture access during the image build after switching to `USER app`. No runtime files become world-writable or group-writable.
- E2 Compose CI removes the source files' other-read bit before building, reproducing the VM checkout mode that caused the failure.
- The first integration E2 run built the guarded image but three later cohort tests failed because their containers bind-mounted the permission-restricted host fixtures. The CI follow-up restores other-read permissions immediately after Compose build and in the exit trap. The new CI run is pending.
- Local `git diff --check` passed. An isolated VM `docker build` of code SHA `28c8a34` from a clean checkout with the actual `0660` ini mode succeeded (`permission_build_exit:0`); the Dockerfile check ran as `USER app` and read Alembic, engine, knowledge and fixtures. This used a unique review image tag and did not run Compose, migrate, or alter live services. Integration CI remains required before release. Do not deploy this code until the coordinator accepts a new release SHA after CI.
- After acceptance, redeploy production and preview from new clean worktrees, verify `e4_city_cohort` migration, HTTPS/preview UI, model and MAX egress, and preserve the shared Nginx and other projects. MAX client acceptance remains separate.
