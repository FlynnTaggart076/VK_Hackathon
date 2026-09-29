# B: MAX mini-app button follow-up

## Diagnosis, read-only production check

- Current production worker was running. `MAX_WEB_APP` was present and had username format; bot token was present. No secret or username value was printed or copied.
- In the last three hours at the time of inspection: five webhook inbox events were `done` and their five outbox messages were `sent`. One `/help` and one `/llm_on` were present; both outbox messages had no keyboard. No `/start` or `bot_started` event appeared in that window. This supports the code-path diagnosis, not an Android opening claim.
- The existing code attached `start_keyboard()` only to `/start` and `bot_started`. Its inline `open_app` payload has the expected `web_app` bot username shape per [MAX keyboard documentation](https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard) and [MAX Bot API schema](https://github.com/max-messenger-bot/max-bot-api-schemas/blob/main/schema_2026_07_01.json).
- A separate persistent chat-header launch button is configured through the bot's mini-app URL and button setting on the [MAX partner platform](https://dev.max.ru/docs/webapps/introduction). An inline response keyboard does not create that persistent button.

## Submitted fix and verification

- Code SHA `951cb63282f274f47fe0c5f34aaa1c00e12b8f55` on `agent-b/e4-synthetic-cohort`, separate from synthetic-city code `dc72ab3` and its report `0caf92d`.
- Outbox now attaches the existing two-button keyboard on `/help` and `/llm_on` as well as `/start`/`bot_started`. Arbitrary messages, receipt questions and `/llm_off` keep their current attachment behavior.
- Local targeted tests: `14 passed` for `test_e3_max_queue.py` and `test_e4_deepseek_core.py`, including a new `/help` + `/llm_on` keyboard test. `git diff --check` clean.
- No MAX API message was sent to a real user and no VM service or configuration was changed. The code requires the coordinator's integration, CI and release gate. Android `/start` button visibility/opening and the partner-platform URL setting still require owner verification.
