# A · E4 DeepSeek dialogue UI and continuations

Latest code commit pushed to `origin/agent-a/e4-deepseek-flow`: `5b6a4e44b516aa00639f6b8630cefebe0c6f381e` (initial code `dfe066d16d72c02b9057efb39a404ed6078e0f46`, base `9b58db6`). This report is a following documentation commit on the same branch.

## Delivered

- Every `AnswerView.clarification.field` has editable text input and a `datalist`; server options remain clickable. Empty options no longer strand the user. The form retains earlier answers, selected topic, original question and confirmed receipt across chained clarifications. A typed service maps to the strict service enum; unknown service text remains in the submitted question with `service_code=other`.
- Territory and role clarification changes use `PUT /me/profile` before `/assistant/answers`, after a visible acceptance of the current privacy notice. The saved profile is reflected in the app. A selected topic wins over classification. Missing receipt, unsupported and server fallback text remain visible; there is a retry path after errors.
- Confirmed receipts now link from history, review and explanation to a question or city comparison. `select_topic` actions retain `receipt_ref`. Dense receipt rows are collapsed into editable summaries; the first and newly added rows open automatically.
- Added separate city aggregate consent in History and city comparison route. Numeric values are hidden for synthetic receipts, cohorts below five, incomplete results and ambiguous services. A trend requires the immediately previous month. The backend will derive the exact service/scope/segment/unit from a unique owner row, or return `ineligible`.

## Verification

Portable Node `v22.23.3` was used from `%TEMP%`; no system installation or secret was committed.

- `npm run build`: pass (TypeScript and Vite).
- `npm test`: 4 files, 20 tests passed.
- `npm run test:browser:e2`: pass, upload → processing → review → revision conflict → confirm → explanation → expired session, 360 px.
- `npm run test:browser:e3:mock`: pass, history → comparison → draft → FAQ clarification → unsupported, 360 px.
- `npm run test:browser:e4:clarifications`: pass, supplier contact with zero service options → typed service → organization → answer; edit a prior answer by keyboard; topic by question; unknown request; all six clarification fields; territory/role profile updates avoid mock 409; aggregate consent; synthetic cohort blocked; receipt retained, 360 px with no horizontal overflow.
- `npm run test:browser:e4:dense-review`: pass, 19 synthetic service rows render, a second row opens for editing, 360 px viewport and 360 px document width. Full page height was 6241 px. This checks mobile density, not the private `EX.pdf` itself.
- `git diff --check`: pass. No token, private PDF or raw receipt data in this branch.

## Integration dependencies and remaining acceptance

- B's DeepSeek answer, `aggregate_opt_in` profile field, `PUT /me/aggregate-consent`, and `GET /receipts/{id}/city-comparison` must land with the agreed schema before the new city controls work against the real API. The old API returns 404 on these routes. After B's OpenAPI update, regenerate `apps/web/src/api/openapi.generated.ts` and replace the temporary local aggregate type definition.
- Verified supplier contact data may still be absent; a completed service clarification can correctly end in an unsupported or limited answer. Model outage text depends on B's `AnswerView` fallback.
- City aggregation and real EPD extraction require B/C server tests. The 19-row browser check uses synthetic rows; the actual PDF, PostgreSQL cohort, VM endpoint and MAX client were not tested by A.
- The collapsed dense review remains a long vertical form. A real 19-row, 173-evidence review needs a human pass after integration; every extracted value must remain reviewable before confirmation.

## Strict ID follow-up

The clarification text field also accepts arbitrary phrases. `topic_id`, `territory_id` and `service_code` cannot receive arbitrary phrases under the backend contract. The follow-up sends a recognized topic ID or `null` plus the user's topic words in the question; an unknown organization name also goes into the question with `organization_id=null`. An unknown territory or role remains visible in its field with an actionable validation error before any profile PUT or answer call. Service phrases map to the enum or `other` with the original words in the question. `document_kind` is a free string in `QuestionContext` and is sent as typed.

`npm run build` passed, `npm test` passed 20 tests, and sequential 360 px browser runs `test:browser:e4:clarifications`, `test:browser:e3:mock`, `test:browser:e2` passed after this fix. The E4 browser run types custom values into all six clarification fields; it checks request bodies for topic, organization, service and document, and confirms that invalid territory/role never reach the API.

Next: integrate B and C contracts, run browser tests against a real local API, then re-check the exact EPD layout and MAX mini-app after accepted release deployment.
