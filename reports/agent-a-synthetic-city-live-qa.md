# A · E4 deployed preview browser QA script

Code pushed to `origin/agent-a/e4-synthetic-city-live-qa`: `321ffd622fa752228d774b0fd27a5b960a6a4134`. Base is accepted release `b9032d549b560e93ebfbd3276ba0de8e63289d90`. This branch adds only `apps/web/scripts/e4-synthetic-city-preview-live.mjs` and its package command; it does not change the deployed application.

## Coverage

Run with `CHROME_PATH` and optional `PREVIEW_URL` (default `https://flynntaggart075.asuscomm.com/team/zhkh-preview/`): `npm run test:browser:e4:synthetic-city-preview-live`. The URL must be HTTPS with the exact preview prefix and no credentials or query string. The script uses the real API; it does not intercept responses or upload a local file.

- At 360 px, an isolated virtual guest completes Moscow onboarding, imports the August and September 2026 *synthetic* city samples, checks their periods, accepts each actual review warning, confirms them, and follows History to the preview city comparison.
- It reads both API results and checks `synthetic_preview_cohort`, city/service/scope/segment/unit/period, five artificial records, own charge, mean, median and deviation. Expected Moscow current/previous means are `342.00` / `256.00` RUB, with own amounts `270.00` / `200.00` RUB. It verifies the visible training badge and both numeric panels.
- At 1280 px, a second browser context gets a distinct virtual guest, selects Moscow Oblast, imports and confirms the two Lyubertsy samples, and checks `319.20` / `243.20` RUB means and `252.00` / `190.00` RUB own amounts. Both widths must have no horizontal overflow. Across both guests it expects four preview cohort calls and zero real cohort calls.
- Output is one short JSON record with result, stage/check names, request counts, warning counts and layout widths. It does not print session tokens, account data, response bodies or full request URLs. Failure output has bounded, redacted diagnostics. The script does not deploy, restart or change VM services; the four imported receipts are synthetic records in newly created preview guest accounts.

## Current validation and next step

`node --check apps/web/scripts/e4-synthetic-city-preview-live.mjs`, package JSON parse/command lookup, and `git diff --check` passed. Accessible names and review-warning selectors were checked against the accepted `e4-preview-live.mjs`, the synthetic UI browser mock script and current React components. The live script has **not** been run: B was deploying release `b9032d5` when this report was written. After deployment, run it against the preview URL, record the actual JSON and failure details if any, then integrate this QA-only branch separately from the deployed release. A green syntax check is not live browser acceptance or MAX client acceptance.
