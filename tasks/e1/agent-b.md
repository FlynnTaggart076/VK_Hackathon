TASK_ID: E1-B-01
AGENT: B
STAGE: E1
BASE_SHA: feb1fc7ab12201e6d5a93989d64a8374fe44a139
BRANCH: agent-b/e1
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: feb1fc7ab12201e6d5a93989d64a8374fe44a139
GOAL: Создать запускаемый dev backend с миграцией PostgreSQL, изолированным demo auth, загрузкой и persisted job skeleton, первым Compose без заявления о готовом OCR.
INPUTS: Принятые `contracts/http/openapi.yaml`, examples, DTO C и ТЗ §§6–8, 11–12, 14.3 E1; C E1 implementation можно подключать только после принятого SHA от координатора. Инструкция VM локальна, операции VM только при действующем доступе и в границах §12.8.
ALLOWED_PATHS: apps/backend/**, contracts/http/**, infra/**, scripts/**, compose.yaml, compose.local.yaml, compose.vm.yaml, .env.example, .dockerignore, .gitignore, README.md, DATA-API.yaml, THIRD_PARTY_NOTICES.md, docs/backend.md, docs/deployment.md, reports/agent-b.md, docs/contract-changes/agent-b/**.
SUBTASKS:
  - Сначала предоставить A проверяемый dev checkpoint `GET /api/v1/meta`, `POST /auth/demo`, `GET /me`, `POST /receipts` и `GET /jobs/{id}` с error envelope/OpenAPI из E0. Реальный MAX auth только после сверки актуальной официальной схемы; dev stub явно маркирован и запрещён в production.
  - Сделать миграции минимального набора `users/profiles/sessions/receipts/documents/jobs/idempotency_keys` и закрытое файловое хранилище, проверки MIME/size/page/pixels, ownership/2 demo users, идемпотентность создания. Остальные таблицы §6.2 можно добавить по E2/E3 без ложной отметки готовности.
  - Worker skeleton читает persisted jobs из PostgreSQL, ставит lease/retry и безопасный stub outcome по fixtures, который явно включается только в dev. Обработка OCR и расчёты принадлежат C; на E1 stub не выдаётся за настоящий OCR. Сохранение после рестарта проверять, если доступен реальный PostgreSQL.
  - Собрать `compose.yaml`, `compose.local.yaml`, `.env.example`, Dockerfile backend и dev web proxy под `/team/zhkh/`; локальный тестовый project name/volumes, без внешних портов API/DB. Не менять рабочую VM/общий Nginx до принятого release SHA и отдельного задания на deploy; ранняя проверка доступа уже показала SSH publickey blocker.
  - Поставить locked зависимости, тесты ошибок/авторизации/изоляции/загрузки и команды запуска. Для MAX и VM проверить только доступность при появлении полномочий, секреты не выводить.
ACCEPTANCE: dev API соответствует проверяемому подмножеству принятого OpenAPI, два demo пользователя изолированы, upload создаёт одну queued запись/job при повторе ключа, stub и demo auth выключены в production; миграции и Compose конфигурация валидны там, где Docker доступен. Если Docker/PostgreSQL/SSH отсутствуют, дать точный уровень непроверенной интеграции и продолжить независимые тесты; E1 как общий этап останется review до реального PostgreSQL/Compose.
REPORT: reports/agent-b.md
STOP_WHEN: Отдельные pushed code/report SHA переданы координатору с проверками и блокерами; E2 и VM deploy без следующего задания не начинать.
