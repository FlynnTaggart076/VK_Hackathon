# A · Frontend acceptance of release-005015c import

Base: `47303838d40613c1cae24fe959e2fb4eae40ba47` (`origin/integration/import-005015c`). Work was performed in the separate `agent-a/verify-005015c` checkout. No application source changes or release-archive changes were needed.

## Checks

In `apps/web`, with portable Node 22.23.3 and local Chrome:

| Command | Result |
| --- | --- |
| `npm ci --no-audit --no-fund` | Passed; 133 packages installed |
| `npm test` | Passed; 8 files, 49 tests |
| `npm run build` | Passed; TypeScript and production Vite build |
| `npm run test:browser:e5:russian` | Passed; 13 screens without Latin UI words |
| `npm run test:browser:e5:service-kind` | Passed; unique service list, dependent fields; 360 px viewport and document width |
| `npm run test:browser:e4:dense-review` | Passed; 19-row synthetic review at 360 px with no horizontal overflow |
| `npm run test:browser:e2` | Passed; upload, polling, review, revision conflict, edit, confirm, explanation, expired session at 360 px |
| `git diff --check` | Passed |

The browser tests used the local Vite mock server and `C:\Program Files\Google\Chrome\Application\chrome.exe`. The server was stopped after the checks. npm touched only line endings in `apps/web/public/mockServiceWorker.js`; the file had no content diff and was restored in this checkout.

## Review and result

Reviewed the new service catalog, service selection and dependent unit/scope/segment fields, amount parsing and validation, and the receipt review/confirmation path. The catalog parity and form behavior are covered by the unit suite; the two E5 browser scenarios and the dense review/E2 regressions cover the user-visible path. No reproducible frontend release blocker was found, so this branch adds only this report.

These are local mock, unit and build results. Real API, VM, MAX client, and real receipt interpretation are outside this A check and require their separate acceptance evidence. Next coordinator step: combine this report with backend/VM checks for the imported release and act on any concrete CI or live defects.

## E2 real browser CI follow-up

E2 CI run `36620632003`, job `109584816709`, passed API/PostgreSQL/OCR checks and then timed out at `e2-real-flow.mjs:18` waiting for the «Первый запуск» link. In `App.tsx` that link appears only while `canUpload(profile, meta)` is false. A reviewer account whose onboarding is already complete can therefore enter successfully without seeing it. The footer's «Изменить роль и территорию» link is rendered for every authenticated account and opens the same onboarding route.

Code commit `62715f48a6d3b9c408db2208b7f7298753f784a6` changes that locator in E2, E3, E4 resilience and both live preview browser scripts. It keeps the role, territory, privacy acknowledgement and subsequent assertions intact. The E5 service-kind mock scenario now confirms the first-run prompt disappears after onboarding and the footer link still opens the form. The dev-entry helper was inspected; its login and retry locators match the current UI, so it was not changed.

Verification: `node --check` passed for all six changed browser scripts; `npm run test:browser:e5:service-kind` passed with 360 px viewport/document width; `git diff --check` passed. The real E2 and E3 scripts require an integrated backend and have not been run locally. Coordinator should rerun CI on the integrated fix SHA; this local check does not establish that the whole real flow passes.
