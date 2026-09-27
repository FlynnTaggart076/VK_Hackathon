TASK_ID: E3-C-01
AGENT: C
STAGE: E3
BASE_SHA: b33ed1e0493d76dfd7051a141e2075c698f8e967
BRANCH: agent-c/e3
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: b33ed1e0493d76dfd7051a141e2075c698f8e967
GOAL: публичные compare_receipts/answer_question/compose_draft/load_knowledge v1 и проверяемые E3 fixtures без сети во время пользовательского запроса.
INPUTS: принятый E2 main, §8–10, §17.4, 15 topic_id, существующие DTO/schema/knowledge. Пилотная территория и реальные квитанции не предоставлены; demo источники/организации маркировать synthetic, локальные инструкции без проверенного источника не выдавать как факт.
ALLOWED_PATHS: packages/housing_engine/**, knowledge/**, contracts/engine/**, fixtures/**, docs/engine.md, docs/data-provenance.md, reports/agent-c.md, docs/contract-changes/agent-c/**.
DEPENDENCIES: compare DTO v1 уже принят в E0, задача сравнения независима от B/A; ранний pushed checkpoint передать B. Внешнее подтверждение пилотной территории/локальных источников отсутствует: реализовать безопасное generic/unknown поведение и явно отметить блокер, не выдумывать verified_at.
SUBTASKS:
  - Ранний pushed checkpoint: compare_receipts для bytes-derived synthetic 200→270, ровно delta 70, quantity 40, tariff 30; current confirmed refs, порядок по периоду, account/provider/address/identity acknowledgement, same-month block, nonadjacent interval, unit mismatch, duplicate/ambiguous lines. Fixtures отдельно задают ожидаемые Decimal, не повторяют алгоритм. Передать B публичный пример/exception codes.
  - Завершить §9.8: adjustments/debt/payments/credit clamp, printed vs calculated totals, unknown operands null, `other` не теряется, rounding residual, 200→190 случай без двойного adjustment. Всюду честные partial/unsupported/reconciliation issues.
  - Создать 15 тем §10.1 с контролируемым ranking/clarification/unknown. Источники и применимость проверять по manifest/territory/review_after; перед внесением реального источника фактически открыть его и записать provenance. Нет живого веб-поиска в пользовательском пути. «Справка» без вида/территории/роли вызывает уточнение. Просроченный/чужой источник не становится инструкцией.
  - compose_draft по текущим confirmed refs/line_id, неизвестные значения не подставлять, получатель null без проверенного канала, только текст и actions для копирования/ссылки; никакого send. Устойчивость к prompt injection из PDF/вопроса.
CHECKS: независимые unittest/fixture и schema verifier, точные 70/40/30 и все §9.8 cases, 15 тем, unknown/stale-source/territory/document clarification, draft facts and no send. Пакет без FastAPI/DB/MAX/сети при runtime; реальные источники проверять отдельно при подготовке, с датой и ссылкой в provenance.
STOP_AND_REPORT: ранний compare code SHA + schema/fixture пример для B, затем итоговый code SHA и report SHA в origin/agent-c/e3. Указать ограничения пилотных данных. Не менять backend/web и не начинать E4.
