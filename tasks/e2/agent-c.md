TASK_ID: E2-C-01
AGENT: C
STAGE: E2
BASE_SHA: dae14d9a838154b72e4cf122881b190032ae0a74
BRANCH: agent-c/e2
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: dae14d9a838154b72e4cf122881b190032ae0a74
GOAL: Довести один документированный макет от bytes через частичное/полное извлечение и точную арифметику до детерминированного объяснения подтверждённой квитанции.
INPUTS: Принятые E1 `packages/housing_engine`, engine v1 schemas и синтетический fixture manifest; ТЗ §§8–9, 14.3 E2, 15.1. B получит только проверенный координатором public API SHA. Реальные квитанции не добавлять в Git без подтверждённого права и обезличивания.
ALLOWED_PATHS: packages/housing_engine/**, knowledge/**, contracts/engine/**, fixtures/**, docs/engine.md, docs/data-provenance.md, reports/agent-c.md, docs/contract-changes/agent-c/**.
SUBTASKS:
  - Улучшить `extract_receipt(DocumentInput, ExtractionConfig)` для выбранного `demo-bill-v1`: PDF text/PNG/JPEG/image-only PDF bytes, реквизиты/период/услуги/корректировки/итоги, evidence с page/bbox/source и честными `needs_review`; неизвестный/обрезанный/нечитаемый формат — partial или manual_required. Не использовать имя файла, fixture ID или заранее готовый JSON как результат OCR.
  - Реализовать публичный `explain_receipt(ExplainRequest, KnowledgeBundle)` с Decimal-арифметикой из подтверждённого BillData: формулы строк, текущие начисления отдельно от итога к оплате, долг/оплата/перерасчёт без двойного учёта, mismatch/incomplete/unsupported и ограничения. Не выдумывать нормативы, тарифы, ссылки или территорию; без проверенного внешнего источника объяснение остаётся арифметическим и помечает ограничения.
  - Расширить синтетические bytes fixtures/manifest и независимые tests: 200→270, изменение тарифа/объёма, -50 корректировка, долг/оплата, плохой OCR, неизвестный макет, повреждённый PDF, несовпадение печатной суммы. DTO/schema v1 не менять молча; при необходимости proposal через docs/contract-changes.
  - Документировать точные версии/языки Tesseract, install API, timeout/memory/pixel ограничения и уровень проверки для B. Пакет должен тестироваться без БД, HTTP, MAX или сети.
ACCEPTANCE: v1 schema verifier и tests проходят; извлечение из bytes поддерживаемого PDF/растра использует реальный text/OCR путь и возвращает валидные DTO, unsupported/partial не выдаёт fabricated fields; объяснение подтверждённого 200/270 даёт точные суммы и источники только при наличии проверенных данных; B получает воспроизводимый public API и fixtures. Реальные счета и VM quality отдельно не заявляются.
REPORT: reports/agent-c.md
STOP_WHEN: отдельные pushed code/report SHA и список системных OCR-зависимостей переданы координатору для review либо указан конкретный блокер; E3 не начинать.
