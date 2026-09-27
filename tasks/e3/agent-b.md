TASK_ID: E3-B-01
AGENT: B
STAGE: E3
BASE_SHA: b33ed1e0493d76dfd7051a141e2075c698f8e967
BRANCH: agent-b/e3
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: b33ed1e0493d76dfd7051a141e2075c698f8e967
GOAL: persisted API сравнения/FAQ/черновика, stale/удаление и безопасный MAX webhook/bot контур E3 без реальной отправки обращений.
INPUTS: принятый E2 main, OpenAPI v1, C DTO/fixtures; инструкция владельца «Работа с сервером.md» и границы §12.8. VM deploy только из принятого RELEASE_SHA отдельным E4 заданием; текущего release SHA нет.
ALLOWED_PATHS: apps/backend/**, contracts/http/**, infra/**, scripts/**, compose*.yaml, .env.example, README.md, DATA-API.md, THIRD_PARTY_NOTICES.md, docs/backend.md, docs/deployment.md, reports/agent-b.md, docs/contract-changes/agent-b/**.
DEPENDENCIES: ранний C pushed compare API/schema checkpoint перед реальным compare adapter; C knowledge/answer/draft checkpoint перед соответствующими endpoints. Пока их нет, делать независимые auth/MAX HMAC/webhook/inbox/outbox/owner/history/delete и контрактные тесты. Не копировать арифметику C и не выдавать stub за real.
SUBTASKS:
  - Ранний checkpoint: по принятым C функциям реализовать compare для двух owner-scoped current confirmed revisions; порядок по периоду, identity acknowledgement, одинаковый месяц/счёт/поставщик/адрес, 409 stale после edit. Вернуть серверные 70/40/30 без собственной формулы. Опубликовать SHA/HTTP examples для A.
  - Ответы и черновики: route question/answer с контекстом профиля/территории, verified source filtering C, unknown clarification; хранить answer/knowledge_version/dataset_kind и stale reasons. Draft только из подтверждённых текущих refs, edit/copy state и recipient/actions; изменение receipt делает stale. Реальной отправки обращений нет.
  - История/удаление/retention: pagination и owner isolation, 410 source-expired при сохранении derived данных, удаление во время OCR не восстанавливает данные; два пользователя меняют ID receipt/job/answer/draft и получают 404. Обработать перезапуск/inbox/outbox и идемпотентность.
  - MAX: проверить актуальный официальный MAX контракт по первичному источнику; реализовать проверку подписанного initData с тестовыми векторами, сроком/повтором, безопасный webhook и inbox/outbox/команды справочного бота. Без действующих credentials выполнить только синтетические тесты; не логировать raw initData/token/PII. При блокере указать точные отсутствующие данные, не трогать VM/внешний вход.
  - HTTP OpenAPI/examples обновлять синхронно с реализацией; dev synthetic auth остаётся явным, production отвергает demo/stub. Никакой CI/CD или отправки обращений.
CHECKS: isolated PG16/PG17 migration и integration tests (owner/CAS/stale/delete/restart/HMAC/webhook), HTTP contract verifier, Compose config/build/smoke на проверяемом SHA, без секретов в Git/логе. Отдельно записать локальный, CI, VM, внешнее HTTPS и реальный MAX уровни; непройденные уровни не объявлять проверенными.
STOP_AND_REPORT: ранний pushed compare SHA и согласованный контракт для A, затем итоговый code SHA + report SHA в origin/agent-b/e3. Не деплоить VM без назначенного accepted RELEASE_SHA, не начинать E4 самостоятельно.
