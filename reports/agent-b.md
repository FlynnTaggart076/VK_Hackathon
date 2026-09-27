# Отчёт агента B — E0-B-01 и E1-B-01

- Ветка: `agent-b/e0`; BASE_SHA: `522757f58ad61951c7d66c4e97f2d5e65a433624`.
- Принятый для формы DTO integration SHA C: `89df7e39a165902bf19308cd6512b4a19eb6205b` (позднейший doc-only integration SHA координатора: `edb784f9797f8b95f132f2d90ffe1eaa79f85a18`).
- Pushed SHA реализации: `910e141ee170bf8eb740d4a63f0b38d9f6c41212`.
- Статус: **review у координатора**. E0, продукт и VM не объявлены принятыми; E1 не начат.

## Результат

- `contracts/http/openapi.yaml`: 28 операций §7 и webhook §11.5, публичный сервер `/team/zhkh`, session bearer и webhook secret, UUID/idempotency, `expected_revision`, cursor/limit, MIME upload/source/preview, коды ошибок, безопасный envelope, `Retry-After`, `X-Request-ID`.
- Nested BillData/evidence/issues/explanation и свойства AnswerResult/ComparisonResult/DraftResult ссылаются на `contracts/engine/v1/*.schema.json` принятого C. Смысл DTO не скопирован вручную. Для webhook взят документированный базовый объект `Update` (`update_type`, `timestamp`, расширяемые поля события); `update_id` не предполагается. Официальные источники: [Update](https://dev.max.ru/docs-api/objects/Update), [подписка и секрет](https://dev.max.ru/docs-api/methods/POST/subscriptions). Конкретные типы событий требуют runtime-проверки в E1.
- `contracts/http/examples/*.json`: 24 синтетических примера, в том числе auth/error 401, конфликт 409, 413, 422, 429, 503, неизвестный макет, уточнение/unsupported, неполное сравнение и просроченный source. `meta-dev.json` честно показывает E0/dev stub: `engine_stub=true`, OCR/сравнение/демовход выключены, версии неизвестны. Остальные success JSON — формы будущих ответов, а не показания работающего API.
- `docs/backend.md`: проектная схема 13 таблиц, CAS-ревизий, изоляции двух demo identity, idempotency, закрытого storage, устойчивой очереди с lease/heartbeat/retry/cancellation и границ adapter C. Это схема E0, миграций и worker ещё нет.
- `scripts/make_http_examples.py`, `scripts/check_http_contract.py`, `scripts/requirements-contracts.lock`: воспроизводимая генерация/проверка локально. Отдельные top-level pin указаны также в `scripts/requirements-contracts.txt`.

## Проверки

| Уровень | Команда / факт | Результат |
|---|---|---|
| HTTP контракт | `python scripts/make_http_examples.py`; `python scripts/check_http_contract.py` с пакетами из `scripts/requirements-contracts.lock` | `OK: OpenAPI 3.1; 28 operations; 24 JSON examples; engine fields linked` |
| Контроль изменений | `git diff --cached --check`, `git diff --exit-code` после генерации | exit 0 |
| Git публикация | `git push origin HEAD:refs/heads/agent-b/e0`; `git ls-remote origin refs/heads/agent-b/e0` | remote SHA `910e141ee170bf8eb740d4a63f0b38d9f6c41212` |
| Локальный Compose | Не запускался; E0 не содержит runtime/Compose | не проверено |
| SSH VM | `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 hackathon hostname` | TCP/SSH дошёл до аутентификации, `Permission denied (publickey)`; внутрь VM не вошёл |
| Публичный внешний вход | `curl.exe -sS --connect-timeout 5 --max-time 15 -o NUL -w 'http=%{http_code} tls_verify=%{ssl_verify_result}' https://flynntaggart075.asuscomm.com/team/` | HTTP 200, TLS verify 0; это существующий `/team/`, не наше приложение |
| MAX | Проверено только наличие `MAX_BOT_TOKEN` и `MAX_WEBHOOK_SECRET` в окружении текущего checkout и `.env` в нём: отсутствуют; API-запросов/подписок не делалось | учётные данные и реальный клиент MAX не проверены |
| VM приложение / внешний URL `/team/zhkh/` | Не разворачивалось и не проверялось | не проверено |

## Блокеры и следующий шаг

Для будущего E4 operator-доступ к VM отсутствует на уровне SSH publickey; нужен корректный ключ/зарегистрированный пользователь. MAX credentials недоступны из текущего checkout/окружения; наличие у владельца не установлено. Эти блокеры не мешали E0 контракту. Координатор проверяет OpenAPI и examples против C, интегрирует совместимый commit, сообщает дефекты либо принимает E0-B-01; только после нового задания B начинает E1. При E1 потребуется подтвердить event-specific MAX update schema и реализовать безопасный adapter/runtime.

---

## E1-B-01: dev backend, PostgreSQL и первый Compose

- Ветка: `agent-b/e1`; BASE_SHA `feb1fc7ab12201e6d5a93989d64a8374fe44a139`; TASK_COMMIT `4449864e24686472130b2569be04b349ed862834`.
- Ранний принятый A dev API checkpoint: `1d99a19502df2b536248daad224b0f0af5e96d5a`.
- Pushed основной E1 code SHA: `aafa3348450af3a005e9a30b92411779cac8e9dc`.
- Pushed merge принятого C checkpoint и первая правка PostgreSQL теста: `a2afba39ce197ca7cd11014defaec69f3c158a78` (второй parent integration SHA `4f653165ed97bea21572231a9f623607f16e89c5`).
- Pushed итоговая правка изоляции PostgreSQL теста: `d1798ccd1f064fcd40581679a9b283e85ba0c339`.
- Статус: **review координатора**; общий E1 и продукт не объявлены принятыми.

### Реализовано

- `apps/backend/app/db` и Alembic `e1_initial`: users, profiles, sessions, documents, receipts, receipt_revisions, jobs, idempotency_keys, worker_heartbeats. PostgreSQL использует JSONB. Token хранится только SHA-256. Два demo identity имеют отдельные UUID и owner-scoped чтение; чужие UUID возвращают 404.
- Загрузка PDF/JPEG/PNG проверяет фактический MIME, размер 10 MiB, страницы PDF и пиксели; исходники хранятся по случайному ключу в закрытом томе. Транзакция создаёт document, receipt, job и idempotency result. Повтор ключа в течение 24 часов возвращает тот же результат, конфликт даёт 409, после истечения ключ используется заново.
- Worker выбирает persisted jobs с lease 180 секунд, retry до 3 попыток, heartbeat и fencing token. В E1 он только dev stub: пользовательский файл получает `manual_required` и пустые поля; явный импорт двух синтетических fixtures получает маркировку `SYNTHETIC_DEMO`. OCR/расчёты C ещё не подключены к backend.
- `compose.yaml`, `compose.local.yaml`, `compose.vm.yaml`: отдельный PostgreSQL 17, migrate, API, worker, web, закрытая сеть/тома, локальный loopback web и VM edge alias. `infra/nginx/app-local.conf` снимает префикс `/team/zhkh/`; `app-vm.conf` принимает путь после внешнего Nginx. `infra/web.Dockerfile` находится в разрешённом B infra пути и не меняет файлы A. Режимы `demo`/`production` на E1 явно отклоняются при старте.
- Реальные HTTP JSON для meta/auth/me/catalog/receipt/job и ErrorEnvelope проверяются по принятому E0 OpenAPI с внешними engine `$ref` (включая ответы SqlStore/PostgreSQL).

### Доказательства и уровень проверки

| Уровень | Команда / факт | Результат |
|---|---|---|
| Backend API + SQLite | `PYTHONPATH=<isolated Python deps>;apps/backend python -m pytest apps/backend/tests -q` | 7 тестов выполняются без PG; PG тест skipped. Формы JSON и SQLite persistence проверены. |
| Реальный PostgreSQL | Изолированный PG16.2 cluster в уникальном `%TEMP%` каталоге, loopback `127.0.0.1:55439`, отдельная `zhkh_e1_test` БД. `TEST_POSTGRES_URL=postgresql+psycopg://zhkh@127.0.0.1:55439/zhkh_e1_test`, `PYTHONPATH=%TEMP%/vk_zhkh_b_e1_python;apps/backend`, `python -m pytest apps/backend/tests -q` | Три последовательных прогона в той же среде: каждый `8 passed, 1 warning`. Каждый PG прогон создаёт уникальный test schema; проверены Alembic, JSONB собственной receipt, persistence после restart клиента, own job/worker, idempotency и readiness. Warning из Starlette/anyio deprecation. |
| HTTP контракт после C merge | `python scripts/check_http_contract.py` с `scripts/requirements-contracts.lock` | `OK: OpenAPI 3.1; 28 operations; 24 JSON examples; engine fields linked` |
| Compose parser | Docker Compose CLI v5.5.1 `--env-file .env.example -f compose.yaml -f compose.local.yaml config -q` и тот же VM override | Оба exit 0 с placeholder значениями; секретный config output не сохранялся. |
| Docker build/up и PostgreSQL 17 | Docker daemon/CLI runtime в текущей Windows среде недоступен | Не проверено; Compose parser и PG16 не доказывают целевой контейнерный запуск. |
| VM / MAX | E0 SSH дал `Permission denied (publickey)`; текущих VM/MAX credentials не получено | VM приложение, публичный `/team/zhkh/`, bot auth/webhook и mini-app не проверены. Общий Nginx/VM не изменялись. |

### Открыто и следующий шаг

Координатор повторяет тесты и Compose parser по pushed `d1798ccd1f064fcd40581679a9b283e85ba0c339`, проверяет совместимость A/C, возвращает конкретные дефекты либо принимает E1-B-01. Для полного E1 остаются Docker build/up на PostgreSQL 17 и frontend вызовы живого backend; внешние VM/MAX блокеры отдельно переносятся в следующие этапы. B не начинает E2 и не разворачивает VM до нового задания и принятого release SHA.
