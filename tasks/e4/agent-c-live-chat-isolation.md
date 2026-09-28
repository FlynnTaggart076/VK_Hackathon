# E4 C: isolate knowledge-engine behavior for live chat sequence

- Role: housing_engine/knowledge (§18.4). Use a new isolated checkout/branch from `origin/main`. Do not access VM or bot secrets.
- Owner observed no MAX reply to an out-of-scope prompt-injection style text, then an on-topic bill-change question and `/help` on 2026-09-28. Independently reproduce `answer_question` with new-bot-user context (`territory_id=null`, `role=other`, no receipt) for synthetic equivalents of all three turns. Record status/error class only, not the owner's exact message or personal data.
- Check whether any input can throw, hang, or poison a subsequent answer; measure bounded timing. If there is an engine defect, add a focused regression and fix only engine/knowledge paths, then push code SHA and separate report SHA. If engine returns safely, report that evidence and hand backend/transport investigation to B. Do not change gold cases to fit output.
