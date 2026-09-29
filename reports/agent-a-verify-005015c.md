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
