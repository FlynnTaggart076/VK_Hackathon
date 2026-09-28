# E4 C: isolation of unanswered live MAX chat sequence

Date: 2026-09-28. Branch: `agent-c/e4-live-chat`. Base: `47eeca5e7fd749117b76fade830d8f0ce68849da`.

## Scope and result

Using the frozen knowledge catalog and public `answer_question` function, I simulated a new bot user with `territory_id=null`, `role=other`, no receipt, and no selected topic, organization, service, or document. Inputs were synthetic equivalents of the observed sequence, without the owner's exact text or personal data.

| Turn | Result | Topic | Max observed call time across 500 runs |
| --- | --- | --- | ---: |
| Off-topic instruction to write a sorting algorithm | `unsupported` | `null` | 0.429 ms |
| Question why a utility bill increased | `answered` | `bill_change` | 0.519 ms |
| `/help`-like text | `unsupported` | `null` | 0.271 ms |

All 500 three-turn cycles (1500 calls, 211.098 ms total) returned the same statuses in that order. No exception, hang, or state poisoning was reproduced. A second bill-change wording also returned `answered` / `bill_change` in 0.14 ms. These timings are local warm Python 3.13 measurements on Windows, not a production latency guarantee. `/help` is a bot command and requires backend command routing; it is not a housing-engine knowledge question.

## Verification

- `python -m unittest discover -s packages/housing_engine/tests -q`: 46 tests, OK. Two expected `EOF marker not found` messages come from existing negative PDF fixtures.
- `python packages/housing_engine/verify_contract.py`: exit 0; schema, synthetic bill fixtures, 15 topic cards, allowlist and references valid.
- No code, contract, knowledge, or gold fixture was changed. The engine path provides no evidence explaining why MAX delivered no visible reply; B should inspect webhook intake, worker processing, outbound MAX API result, and `/help` routing on the VM with redacted logs.

No VM, secret, MAX account, real receipt, or owner message contents were accessed in this task.
