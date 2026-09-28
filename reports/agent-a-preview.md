# E4-A-PREVIEW — browser test mini-app

Base task SHA: `61080a73fd23afd6ef6031dd893196a7cf212ed3`. Branch: `agent-a/e4-preview`; code SHA: `92522770915bffebb4f815ac8fac83e8e96afb22`.

## Delivered

- `VITE_APP_BASE` selects `/team/zhkh/` (default) or `/team/zhkh-preview/` for Vite assets, Router, API, and mock asset paths. `VITE_PREVIEW_MODE=true` enables preview behavior only in the preview bundle.
- Preview uses one anonymous `POST /api/v1/auth/preview` exchange for a server-created guest. It never loads MAX Bridge or shows a code form. Its token is kept in `sessionStorage` for the current tab and removed after a 401; a new guest is then created with a visible loss-of-old-history notice. Production keeps the bearer token only in memory and retains signed MAX login.
- Every preview screen has a conspicuous public training banner. The upload screen hides raw file selection, warns against personal receipts, and retains server synthetic sample import. B confirmed that preview backend also rejects raw uploads with `403 PREVIEW_SYNTHETIC_ONLY`; production upload is unchanged.
- Added Vitest checks for both build prefixes, production token isolation, one preview auth exchange, tab restore, and bad paths; added `scripts/e4-preview-build-smoke.mjs` to exercise browser deep links, auto entry, reload, 401 recovery, and production isolation against stubbed HTTP responses.

## Verification

| Level | Command / setup | Result |
|---|---|---|
| Frontend unit | `npm ci`; `npm test` with portable Node 22.20.0 in ignored `.checkouts/_tools` | 2 files, 16 tests passed |
| Production bundle | `npm run build` with `VITE_APP_BASE` and `VITE_PREVIEW_MODE` unset | success; `index.html` assets under `/team/zhkh/assets/` |
| Preview bundle | `VITE_APP_BASE=/team/zhkh-preview/ VITE_PREVIEW_MODE=true npm run build` | success; `index.html` assets under `/team/zhkh-preview/assets/` |
| Browser, stub API | After each build, `CHROME_PATH=<Chrome> EXPECT_PREVIEW=true|false node scripts/e4-preview-build-smoke.mjs` | both passed in Chrome: preview deep link, one guest, per-tab reload, 401 new guest and upload warning; production deep link had only `GET /team/zhkh/api/v1/meta`, no preview auth/banner |
| Git | `git diff --cached --check` before code commit | exit 0 |

The browser smoke intentionally stubs API responses. It does not prove server guest creation, synthetic receipt import, answer/history/draft persistence, or VM/public HTTPS. Those depend on B's separate preview backend and accepted integrated release; coordinator/B must run the complete flow after deployment. `apps/web/public/mockServiceWorker.js` acquired CRLF-only working-tree noise during `npm ci`; its content is unchanged ignoring line endings, and it was excluded from commits.

## Integration contract

Backend: `POST /api/v1/auth/preview` with no body, existing `AuthResponse`, random unique guest per call; enabled only in preview instance; `meta.mode=preview`. B confirmed no-body request accepted and will add OpenAPI mode/route plus Docker build args `VITE_APP_BASE` and `VITE_PREVIEW_MODE`. Refresh `apps/web/src/api/openapi.generated.ts` after B's contract is integrated.
