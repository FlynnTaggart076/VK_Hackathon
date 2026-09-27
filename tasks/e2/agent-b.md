TASK_ID: E2-B-01
AGENT: B
STAGE: E2
BASE_SHA: dae14d9a838154b72e4cf122881b190032ae0a74
BRANCH: agent-b/e2
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: dae14d9a838154b72e4cf122881b190032ae0a74
GOAL: Связать persisted upload/job с реальным housing_engine и дать изолированные revision/edit/confirm/explanation endpoints для одной квитанции.
INPUTS: Принятые E1 main, `contracts/http/openapi.yaml`, engine DTO и `reports/agent-c.md`, ТЗ §§6–9, 12, 14.3 E2. Код C E2 использовать после проверенного координатором SHA; до него независимо делать DB/CAS/API каркас и контрактные тесты. VM только по отдельному принятому release SHA и доступу в границах §12.8.
ALLOWED_PATHS: apps/backend/**, contracts/http/**, infra/**, scripts/**, compose.yaml, compose.local.yaml, compose.vm.yaml, .env.example, .dockerignore, .gitignore, README.md, DATA-API.yaml, THIRD_PARTY_NOTICES.md, docs/backend.md, docs/deployment.md, reports/agent-b.md, docs/contract-changes/agent-b/**.
SUBTASKS:
  - Реализовать owner-scoped GET receipt/job/source/preview, edit draft с `expected_revision` и конфликтом 409, confirm с серверной валидацией и immutability confirmed revision, explanation только для подтверждённой версии. PostgreSQL transaction/idempotency/lease/retry должны переживать restart API/worker; чужой ID — 404.
  - После принятия C adapter вызывать публичные `extract_receipt`, `validate_bill`, `explain_receipt` на bytes из закрытого storage, сохранять BillData/evidence/issues/engine version и partial/manual outcome. Не выбирать ответ по имени файла или синтетическому ID. Для dev fixture/stub оставить явный отдельный режим; E2 real route без stub.
  - Установить в Docker зафиксированные Python/system OCR зависимости C, включая Tesseract 5 `rus+eng` из закреплённого источника, без сетевой загрузки при первом запросе. Проверить Compose PG17 миграции, job, API, web-префикс и данные после пересоздания сервисов в отдельном project/volume; не трогать рабочую VM.
  - Сохранить OpenAPI и реальные error envelopes совместимыми; при изменении смысла DTO/HTTP сначала `docs/contract-changes/agent-b/...` и решение координатора. Проверить права двух demo пользователей, 401/409/422/413, повтор upload и безопасное удаление/retention по текущему контракту там, где относится к E2.
ACCEPTANCE: через живой Compose из bytes синтетического поддерживаемого документа получены OCR результат, правка, подтверждение и объяснение; после restart API/worker результат читается из PG17; unsupported/partial не становятся выдуманным success; тесты, OpenAPI verifier, `docker compose config` и runtime smoke проходят. Если Docker локально недоступен, использовать изолированный CI и записать точный уровень проверки. VM/MAX не считать проверенными.
REPORT: reports/agent-b.md
STOP_WHEN: отдельные pushed code/report SHA и фактические проверки переданы координатору для review либо указан конкретный блокер; E3/VM deploy не начинать без задания.
