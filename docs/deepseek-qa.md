# Acceptance checklist for the DeepSeek change

Run against a disposable local/preview database first. Record exact release SHA, environment, HTTP/client result and whether the model call was real or mocked. Use only synthetic receipts in automated tests. Keep `EX.pdf`, token values and user identities out of reports.

## MAX chat

1. `/start`, `/help`, then an open question about water charges: all three receive a reply even after a model timeout.
2. Ask who supplies hot water, answer a follow-up clarification with `горячая вода`: the next reply stays on the prior question and does not start an unrelated topic.
3. Ask a completely unrelated question and an instruction to ignore rules: no fabricated ЖКХ fact or external action.
4. With no confirmed receipt, ask `Почему вырос счёт?`: a short request for a receipt, not a fabricated comparison.
5. With one confirmed receipt, ask the same: only current line amounts and their provenance; no previous-month claim and no generic action list.
6. With two same-account consecutive confirmed receipts, ask the same: deterministic old/new and difference, distinguish charge from payment/debt/voluntary insurance.
7. Ask about another user's receipt ID: no access or data in the response.

## Mini-app

1. `Контакт поставщика` -> question -> `По какой услуге?` -> type `горячая вода` or choose a suggestion -> submit. The flow reaches an answer or an honest unavailable-channel result; no dead-end prompt.
2. Repeat for each clarification field (`topic_id`, `territory_id`, `role`, `organization_id`, `service_code`, `document_kind`) with a chain of two prompts. Selected topic, receipt and question persist; user can edit a prior value.
3. `Определить по вопросу` uses the model classifier. A selected topic overrides classifier output. Unknown question asks for clarification or gives a clear limit.
4. Upload the private real EPD only in a controlled local environment, inspect field evidence and all 19 billed service lines, edit and confirm. Keep the separate voluntary insurance and reference meter section out of billed-service totals. Do not upload it to the public preview or include its details in reports.
5. With one bill, inspect compact current charges. With two, compare matching account/issuer and periods. Different accounts must not be paired automatically.
6. Turn on aggregate contribution explicitly. Fewer than five eligible distinct real contributors for the same exact city/month/service/unit shows no numeric average. With five or more, show `n`, city, month, metric, unit and mean/median. Check opted-out/deleted users leave the cohort; a user cannot request individual rows from the cohort.
7. Check every assistant/receipt/history/comparison/draft action at 360 px and desktop, including back/reload, job failure, old answers and expired session.

## Release gates

- Official DeepSeek API contract is used through server env only. Live smoke sends synthetic text only; no token or prompt in logs.
- Parser and arithmetic pass local tests; PostgreSQL migration, ownership, cohort and deletion pass PG17 CI; frontend build and browser check pass.
- B deploys only a coordinator accepted release SHA after private backup and restore check, Compose config and Nginx syntax. Production and preview routes, `/team/` and MAX webhook are rechecked separately. E4/E5 remain open until actual MAX Web/mobile and owner acceptance.
