# B: MAX bot identity response and read-only VM preflight

## Code

- Branch `agent-b/e4-synthetic-cohort`; separate code SHA `8d24ea367f95695a8dc1392281aa64c84fd2dffc`.
- Exact, short identity/capability questions (`Кто ты?`, `Что умеешь?` and close variants) receive a fixed factual answer about the ЖКХ bot, mini-app, and excluded voice/submission functions. This path needs no model request or consent and works during a model outage. It asks the user to send `/start` for the mini-app button.
- Off-topic and injected compound requests do not match the identity route. Existing question classification and rejection remain in place; the code does not add arbitrary conversation or change receipt parsing.
- Local Windows isolated tests: `15 passed` for `test_e3_max_queue.py` and `test_e4_deepseek_core.py`. The new queue test verifies both identity prompts, off-topic rejection and a prompt injection attempt. `git diff --check` clean. No live MAX message was sent.

## VM preflight (read-only, 2026-09-29 07:46 UTC)

- Production API container uses clean checkout `deploy-release-32a09a1`; preview API uses clean `preview-release-32a09a1`. Both checkouts are at accepted SHA `32a09a12daad87c5137577ac5cd7ee505d51c554` with no tracked changes. Both databases report Alembic revision `e4_city_cohort`.
- All eight app containers were running, API/DB health was good, and each db/api/worker/web container had effective restart policy `unless-stopped`. Shared `team-web-nginx-1` was healthy. VM internal `/team/`, production ready and preview ready returned 200.
- Root filesystem: 70 GiB free of 77 GiB. Latest predeploy prod/preview `db.dump` files (created 06:50 UTC, 32949/40637 bytes) passed read-only `pg_restore --list`; corresponding source archives passed `tar -tzf`. These backups precede any new rollout and must be refreshed with restore tests after an accepted release SHA.
- Older checkouts `deploy` (`d3fa9b2`) and `preview-deploy` (`af2b066`) each retain a foreign modified Compose override. Preserve them and the shared Nginx. No VM files, services, databases or routing were changed in this preflight; SSH session was closed.

## Gate

- Do not deploy this code before coordinator review, combined CI and an accepted `origin/main` release SHA. Production needs the accepted MAX UX changes; preview needs the accepted synthetic city flow. Use §12.8 fresh backup/restore, Compose config, migration revision, scoped service update, internal/public checks and rollback plan.
- Android and MAX Web opening remain user-client acceptance checks; the persistent chat button also depends on the URL setting in MAX partner platform.
