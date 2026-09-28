# E4-A-PREVIEW-LIVE — public browser QA, 2026-09-28

Task base: `901ad60af7bad4d1521bfa914ce9d8108625e93e`. Branch: `agent-a/e4-preview-live`. Browser QA script SHA: `090335fa0bd03f79de1c1f70f2257d710b337569`. B reported that the public preview was deployed from accepted release `af2b066ab7d2854dc0138a0e0ef838598d8b76b4`; A did not access the VM to verify its Git HEAD.

Public target: `https://flynntaggart075.asuscomm.com/team/zhkh-preview/`. Command from `apps/web`: `CHROME_PATH=<local Chrome executable> node scripts/e4-preview-live.mjs`. Playwright uses the real public HTTPS UI and API. There is no API interception or stub, MAX message, manual file upload, or VM mutation. Chrome version: `153.0.8010.53`.

| Viewport | Territory | Browser evidence |
|---|---|---|
| 360 × 900 | Москва | Nested `/history` HTTP 200; guest auto entry without MAX/login/code; visible training banner; one preview auth exchange; session survived reload; onboarding saved; catalog August synthetic sample imported, reviewed and confirmed; history displayed confirmed document; FAQ account-number answer included GIS ЖКХ source; separate browser context got another guest and empty history; no wrong-prefix API/asset call or material console/API error; no horizontal overflow. |
| 1280 × 900 | Московская область | Same checks passed on a distinct guest and separate synthetic sample. |

The full two-viewport no-stub run completed successfully twice. The first exploratory run also completed the 360 px user flow but strict logging then flagged a generic Chrome console 404 and an aborted receipt request. The 404 resource URL was not captured; no UI or API step failed. Later full runs found no app HTTP failures. An in-flight `GET /team/zhkh-preview/api/v1/receipts/<id>` was cancelled as the page navigated, consistent with `net::ERR_ABORTED`; the script now records this separately from network failures. One additional attempt timed out on initial Chrome navigation after 30 seconds; an immediate `curl -I` to that same public deep link returned HTTP 200, and the next full Chrome run passed. This single timeout is not enough to attribute a persistent app defect.

The tested import is the server's catalog synthetic JSON, not byte-level OCR of a real document. Public preview verifies an ordinary browser flow only. Signed MAX launch, mobile MAX and organizer binding remain outside this acceptance. `apps/web/public/mockServiceWorker.js` received CRLF-only worktree noise during `npm ci`; ignored in the commit (`git diff --ignore-space-at-eol` exit 0).
