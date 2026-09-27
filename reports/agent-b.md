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
- Pushed runtime исправления после GitHub Actions smoke: `599c9f68f20767d5b3edff24549f0f4b4ecef0ac` (worker fixture path и local edge), `5f1e0b3aeb507775c39fee26992a995507255d62` (Nginx static root); documentation SHA `fecf01c791370c57039d4d876efd3c0f6a4fab35`.
- Статус: B E1 код принят в `integration/e1` и прошёл изолированный Compose runtime smoke; общий E1 и продукт объявляет принятыми только координатор после A/C и остальных критериев.

### Реализовано

- `apps/backend/app/db` и Alembic `e1_initial`: users, profiles, sessions, documents, receipts, receipt_revisions, jobs, idempotency_keys, worker_heartbeats. PostgreSQL использует JSONB. Token хранится только SHA-256. Два demo identity имеют отдельные UUID и owner-scoped чтение; чужие UUID возвращают 404.
- Загрузка PDF/JPEG/PNG проверяет фактический MIME, размер 10 MiB, страницы PDF и пиксели; исходники хранятся по случайному ключу в закрытом томе. Транзакция создаёт document, receipt, job и idempotency result. Повтор ключа в течение 24 часов возвращает тот же результат, конфликт даёт 409, после истечения ключ используется заново.
- Worker выбирает persisted jobs с lease 180 секунд, retry до 3 попыток, heartbeat и fencing token. В E1 он только dev stub: пользовательский файл получает `manual_required` и пустые поля; явный импорт двух синтетических fixtures получает маркировку `SYNTHETIC_DEMO`. OCR/расчёты C ещё не подключены к backend.
- `compose.yaml`, `compose.local.yaml`, `compose.vm.yaml`: отдельный PostgreSQL 17, migrate, API, worker, web, закрытая сеть/тома, локальный loopback web и VM edge alias. `infra/nginx/app-local.conf` снимает префикс `/team/zhkh/`; `app-vm.conf` принимает путь после внешнего Nginx. `infra/web.Dockerfile` находится в разрешённом B infra пути и не меняет файлы A. Режимы `demo`/`production` на E1 явно отклоняются при старте.
- Реальные HTTP JSON для meta/auth/me/catalog/receipt/job и ErrorEnvelope проверяются по принятому E0 OpenAPI с внешними engine `$ref` (включая ответы SqlStore/PostgreSQL).

### Доказательства и уровень проверки

| Уровень | Команда / факт | Результат |
|---|---|---|
| Backend API + SQLite | `PYTHONPATH=<isolated Python deps>;apps/backend python -m pytest apps/backend/tests -q` | После runtime fix `8 passed, 1 skipped, 1 warning`; PG тест без URL skipped. Формы JSON и SQLite persistence проверены. |
| Реальный PostgreSQL | Изолированный PG16.2 cluster в уникальном `%TEMP%` каталоге, loopback `127.0.0.1:55439`, отдельная `zhkh_e1_test` БД. `TEST_POSTGRES_URL=postgresql+psycopg://zhkh@127.0.0.1:55439/zhkh_e1_test`, `PYTHONPATH=%TEMP%/vk_zhkh_b_e1_python;apps/backend`, `python -m pytest apps/backend/tests -q` | Три последовательных прогона до runtime fix: каждый `8 passed, 1 warning`; после fix `9 passed, 1 warning`. Каждый PG прогон создаёт уникальный test schema; проверены Alembic, JSONB собственной receipt, persistence после restart клиента, own job/worker, idempotency и readiness. Warning из Starlette/anyio deprecation. |
| HTTP контракт после C merge | `python scripts/check_http_contract.py` с `scripts/requirements-contracts.lock` | `OK: OpenAPI 3.1; 28 operations; 24 JSON examples; engine fields linked` |
| Compose parser | Docker Compose CLI v5.5.1 `--env-file .env.example -f compose.yaml -f compose.local.yaml config -q` и тот же VM override | Оба exit 0 с placeholder значениями; секретный config output не сохранялся. |
| Docker build/up и PostgreSQL 17 | [GitHub Actions run #6](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36318770691), integration SHA `0b0daaf994315c63de8f0db7d458de6411a31d81` | **Success** на изолированном Linux runner: Compose `config --quiet`, `up --build --detach`, PostgreSQL major 17, API `/health/ready` и meta HTTP 200, worker running, `nginx -t`, web HTTP 200, JS asset HTTP 200, deep SPA link HTTP 200. Meta подтвердил `engine_stub=true`, `receipt_ocr=false`. Локальная Windows среда по-прежнему не имеет Docker daemon. |
| VM / MAX | E0 SSH дал `Permission denied (publickey)`; текущих VM/MAX credentials не получено | VM приложение, публичный `/team/zhkh/`, bot auth/webhook и mini-app не проверены. Общий Nginx/VM не изменялись. |

### Открыто и следующий шаг

Первые runtime прогоны [#3](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36318022335) и [#5](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36318607065) выявили, соответственно, eager вычисление несуществующего `parents[4]` в worker и HTTP 500 у web при отсутствии явного Nginx static root. Оба дефекта устранены указанными code SHA; run #6 прошёл. Далее координатор проверяет совместимость с A/C и решает приёмку общего E1. VM/MAX остаются внешними блокерами; CI не доказывает доставку в VM или реальный клиент MAX. B не начинает E2 и не разворачивает VM до нового задания и принятого release SHA.

---

## E2-B-01: persisted OCR, ревизии, подтверждение и объяснение

- Ветка `agent-b/e2`; BASE_SHA `dae14d9a838154b72e4cf122881b190032ae0a74`; TASK_COMMIT `f613288e5b0a9bc733e6653ba9706bea7e3313d9`.
- Pushed B code SHA: ранний DB/CAS checkpoint `f508d9add75da0b791720f1a5e0f08f403243001`; real worker/API `5694604ee498d3dc71cb4aca400c6fb4355a993d`; retry/retention/HTTP smoke `6915eaa7a8c78897f1fc080ae4c9c881417ba8dc`; PNG OCR smoke `dcb880009b3f59b5ae7f415657cde2d06df8b0cd`; QA исправление confirmed edit, предупреждений и child boundary `e76b6fed70db2929c394d8929cced6d1cb7bb90b`; periodic retention/process tree `baeaa1b4b5ccd19ed01cd3460a68e60f7507f482`; автономный Linux verifier без pip `6b5dd3543a612c502c29789eb91408b8ddb077a4`; kill orphan grandchild `0dcab459c7a6a17f5ff03333436f3f78c7cd07b8`.
- Принятый C E2 code `6b251b0e1770a2ca19c169943da38099c7076b7f` и report `056ea2e576d2fbf7be4dfae5733fc158eced4e17` включены обычным merge B `af49e3e1dcc684e6952b99b8d54e3badab0f0ce4`; API использует публичные функции C без копии DTO.

### Реализовано

- Реальный `receipt_ocr` job читает закрытые bytes по случайному storage key, передаёт их в отдельный Python child, вызывает публичные `extract_receipt`/`validate_bill`, сохраняет BillData/evidence/issues/engine version в JSONB. Поддерживаемый синтетический макет даёт `recognized`; неизвестный макет и неизвестная услуга остаются `manual_required`/`partial` с issues. Никакой выбор по filename не используется. Dev fixture/stub остаётся отдельным явным режимом.
- Parent worker обновляет heartbeat и выполняет retention/cancel check во время OCR каждые не более 25 секунд; C OCR ограничен 90 секундами, внешний budget 120 секунд убивает child и его дерево в Linux process group, в том числе когда лидер вышел до grandchild. Inbox/outbox — E3, в E2 не выполняются.
- Owner-scoped list/get/source/preview/job; edit по CAS и stable `line_id` evidence; confirmed → новая `needs_review` ревизия без изменения прежней confirmed; confirm повторно валидирует C, требует ACK всех видимых warning codes и replay по ключу; explain доступен только для текущей confirmed revision. Ручной ввод ставит `manual-v1`/`unsupported`; server-owned поля восстанавливаются из прежней версии, новая строка получает `document_amount`.
- Источник и PNG-превью хранятся закрыто 7 дней, derived receipts/revisions 30 дней, idempotency 24 часа. Удаление владельца физически удаляет исходник/превью, чужой ID отвечает 204. Retry failed job только при доступном source.
- Dockerfile использует pinned Python deps C и официальные Debian bookworm пакеты `tesseract-ocr=5.3.0-2`, `tesseract-ocr-eng/rus=1:4.1.0-2`; build проверяет `tesseract 5` и оба языка. Compose local default real, `meta.features.receipt_ocr=true`, `engine_stub=false`.

### Доказательства и границы

| Уровень | Команда / факт | Результат |
|---|---|---|
| Backend API + real engine, Windows | `PYTHONPATH=apps/backend`, `TEST_E2_POSTGRES_URL=postgresql+psycopg://zhkh@127.0.0.1:55441/zhkh_e2_test`, `%TEMP%/vk_zhkh_b_e2_python/Scripts/python.exe -m pytest apps/backend/tests -q` | `19 passed, 2 skipped, 1 warning` на code `baeaa1b`; E1 PG env не задан и Linux process-group test ожидаемо skipped. Тесты включают bytes→worker→edit→confirm→explain→restart, confirmed→edit/restart CAS, двух владельцев, warning ACK, manual, retry, retention, unknown/partial, malformed PDF 400, >25 MP PNG 413, missing OCR binary failed job, child timeout kill. |
| PostgreSQL 16.2 отдельно от Kompas | Уникальный `%TEMP%/vk_zhkh_b_e2_pg_20260927_01`, loopback `127.0.0.1:55441`, DB `zhkh_e2_test`; `test_e2_postgres_revisions_and_restart` три последовательных запуска | Каждый `1 passed`; каждый создаёт отдельную schema. Проверены Alembic, JSONB, реальные bytes/worker, конкурентный CAS (один успех/один 409), persisted чтение после restart клиента. Это PG16, не целевой PG17. |
| Engine C | `python -m unittest discover -s packages/housing_engine/tests -p 'test_*.py' -q`; локальный Tesseract 5.5.3 direct PNG | 25 C unittest прошли после merge; synthetic PNG `recognized`, `200.00`, OCR evidence needs_review, `OCR_REVIEW_REQUIRED`. Реальные квитанции и фото не тестировались. |
| HTTP contract | `python scripts/check_http_contract.py` с установленным `scripts/requirements-contracts.lock`; `pip check` после восстановления PyYAML 6.0.3 | `OK: OpenAPI 3.1; 28 operations; 24 JSON examples; engine fields linked`; dependencies healthy. |
| Compose parser | Docker Compose CLI v5.5.1 `--env-file .env.example -f compose.yaml -f compose.local.yaml config -q` и VM override | Оба exit 0, без daemon. |
| PG17 Compose build/up | [CI run #1](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36321592087) и [#2](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36321907368) | Оба success: PG17, pinned Tesseract build, real meta, worker, API ready, Nginx/web/asset/deep route. |
| PG17 full PDF HTTP | [CI run #3](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36322481263), integrated SHA `4d0b537` | Success: synthetic text-PDF bytes→job→edit→confirm→explain, затем restart api+worker и повторное чтение persisted receipt/explanation. Это было до PNG smoke и child/process-tree QA исправлений. |
| PG17 PDF + PNG OCR/restart | [CI run](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36323513080), integration SHA `f37f36f` включает B `baeaa1b` | Success: PG17 Compose, synthetic PDF bytes→job→edit→confirm→explain, synthetic PNG bytes→Tesseract OCR/needs_review, затем restart api+worker и повторное persisted чтение. |
| PG17 final runtime + Linux process-tree kill | [CI run #9](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36324066741), integration SHA `bd907fc7dc3073f666ea2feca13a93eee2cb2de6` | **Success**: Compose PG17, real PDF/PNG OCR HTTP, edit/confirm/explain, restart persistence и offline Linux verifier для live parent+grandchild и exited leader+grandchild. GitHub Actions API вернул `completed/success` для точного SHA. Предыдущий [run #7](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36323640841) не дошёл до теста из-за недоступного PyPI внутри private Compose; verifier теперь без установки пакетов. |
| VM / MAX | Доступ SSH/credentials не предоставлен; release SHA для VM не выдан | VM не разворачивалась, общий Nginx не менялся; MAX не проверен. |

### Открыто

PG17 PDF и PNG HTTP smoke/restart и оба Linux сценария завершения дочернего дерева прошли в run #9. Локальный Windows Docker daemon отсутствует. Подтверждение качества OCR реальных квитанций/фото и VM/MAX не заявляется. Координатор решает приёмку E2-B по этим доказательствам; E3 B без нового задания не начинается.

---

## E3-B-01: сравнение, справка, черновики и MAX-контур

- Ветка `agent-b/e3`; BASE_SHA `b33ed1e0493d76dfd7051a141e2075c698f8e967`; TASK_COMMIT `c11b5235319c12ecb18a6c4ca05c35a54f5c0560`.
- Pushed checkpoints: MAX auth `4f2514f`; сравнение через принятый C API `ce17db7`, исправление mixed synthetic и identity `7dbc2ab`; webhook/inbox/outbox `268885a`; manifest-bound synthetic upload `6a71e3f`; путь к manifest в контейнере `02f6377`; persisted answer/draft `75d0302`; trusted dynamic catalog и MAX text answer `81eef8f`; расширение E3 HTTP smoke `f055351`; исправление версии знаний `fba594c`; региональный каталог/PG webhook verifier `bd9a969`; кнопки MAX и миграция `6051f43`; production `MAX_WEB_APP` gate `362985a133f82235498105f8fdfd410b6cc7fdce`.
- C compare, FAQ/draft и регионы Москвы/Московской области включены через `origin/integration/e3` merge `219996e`; вложенные DTO и расчёт 70/40/30 не дублируются в B.

### Реализовано

- `POST /comparisons` читает ровно две принадлежащие пользователю текущие подтверждённые ревизии, вызывает C `compare_receipts`, сохраняет порядок периодов и отклоняет чужие ID, stale revision и несопоставимую identity. Смешанный synthetic/user dataset маркируется synthetic.
- `POST /assistant/answers` и `POST /drafts` вызывают публичные функции C с серверным профилем и текущими receipt snapshots. Результаты, `knowledge_version` и provenance сохраняются на 30 дней; чтение пересчитывает stale по ревизии, источникам и каталогу. Черновик редактируется по CAS и имеет 24-часовую идемпотентность; отправки обращений нет.
- `/catalog` и `/meta.knowledge_version` получают данные из установленного валидированного knowledge bundle, включая `demo-territory`, `moscow`, `moscow-oblast` и 15 тем. Профиль принимает только доверенные territory IDs. Выбор региона пока не означает проверенный местный маршрут: УК и региональные источники не назначены.
- Опциональный `demo_sample_id` требует точное совпадение ID и SHA/размера/MIME байтов с manifest. Эти байты всё равно идут в реальный OCR job. Обычный upload остаётся `user_provided`; sample fixture не выбирается по имени файла.
- MAX `initData` проверяется HMAC и временем, после чего выдаётся серверная сессия. Webhook проверяет `X-Max-Bot-Api-Secret`, ограничивает тело и сохраняет минимальное событие до HTTP 200. Dedup уникален в БД; worker обрабатывает личные `/start`, `/help`, текстовые вопросы через C, инструкции для вложений, но не групповой контент. Outbox имеет ограниченные повторы и `uncertain` после неизвестного исхода. `/start` сохраняет inline keyboard `message`/`open_app`; production требует `MAX_WEB_APP`. Секреты и raw initData не логируются.

### Проверки и границы

| Уровень | Доказательство | Итог |
|---|---|---|
| Локальный backend | `PYTHONPATH=apps/backend;packages/housing_engine/src`, `%TEMP%/vk_zhkh_b_e2_python/Scripts/python.exe -m pytest apps/backend/tests -q --tb=short` на `362985a` | `26 passed, 3 skipped, 1 Starlette warning`. PG-зависимые тесты пропущены без локального URL. |
| HTTP contract | `python scripts/check_http_contract.py`; `python scripts/make_e3_compare_example.py` после обновления C | OpenAPI 3.1, 28 операций, 25 примеров; `comparison-complete` несёт текущую версию `1.0.2-e3-regions+dae01cb7efe7`. |
| Alembic и PG17 Compose | [CI run 36329206031](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36329206031), integration SHA `452c31a3e6de244b17b4a5b2d94aa2e123698430` включает B `6051f43` | Миграция `e3_max_keyboard`, запуск/readiness, E2 PDF/PNG/restart, E3 HTTP comparison/answer/draft и offline PG17 webhook replay пройдены по последовательности workflow; финальный run **failed** на последующем A browser assertion `e3-real-flow.mjs:102`, ожидавшем статус «перед копированием». Production gate `362985a` в этом run ещё не включён; локально проверен. |
| MAX webhook runtime без send | `scripts/verify_e3_webhook.py` внутри изолированного Compose с случайным secret и пустым bot token в указанном CI run | Wrong secret 403; concurrent duplicate direct event даёт один inbox и один queued outbox, кнопки сохранены. Реальной отправки нет. |
| Официальный MAX контракт | Проверены 2026-09-27 [WebApp validation](https://dev.max.ru/docs/webapps/validation), [subscriptions](https://dev.max.ru/docs-api/methods/POST/subscriptions), [messages](https://dev.max.ru/docs-api/methods/POST/messages), [keyboard](https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard) | Синтетические HMAC, webhook и wire-body тесты. Нужны действующие token/secret, привязка mini-app и проверка MAX Web/мобильного клиента. |
| VM и внешний HTTPS | VM SSH доступ координатором подтверждён read-only; E3 release SHA не назначен | B не разворачивал приложение, не менял общий Nginx и не проверял `/team/zhkh/` на VM. Публичная доставка webhook не заявляется. |

### Статус и следующий шаг

E3-B-01 передан на review по code SHA `362985a`; отдельный report SHA — данный commit. Координатор интегрирует production gate, проверяет PG17 шаги и возвращает конкретные B дефекты, если они появятся. Общая E3 browser-приёмка пока блокируется ошибкой A на run 36329206031, а реальный MAX/VM остаётся E4 внешней проверкой. B не начинает E4 без задания и release SHA.

---

## E4-B-01: подготовка VM и безопасного исходящего MAX

- Ветка `agent-b/e4`, BASE_SHA/E3 accepted release `d223c4e49a12c4ebc5d98c3c8da8fc6c0202e16f`, TASK_COMMIT `40f0e8a1995f4a44f44f174cfa51f2f6acdae2c5`; follow-up по outbound worker `5591daef865502be5acc13ee8c410e0f99722b7a`.
- Pushed code/docs `961cd9d50eba825e8335f3f76ad67dd2e3ae1c38`; private backup и production doc refinement `e389cfa4d30a0c3230110a4b31dd37860ecc511b`; CA trust `0734dba7dd3319f505d7e69aa12de284f06c6759` и canonical LF pin `455804e7463508d169987e7846c0c6d6b56b7a5c`. Старый d223 не разворачивался: worker был только в `private: internal`, поэтому не мог отправлять ответы MAX. Координатор проверил E4 в integration SHA `2e357624e9f59287b09f2593e13dedf619d1e057`; новый accepted release SHA для VM пока не назначен.

### Изменение

- `compose.vm.yaml` даёт **только worker** отдельную обычную сеть `max_egress` для DNS/HTTPS, оставляя db/migrate/api в закрытой `private`, web — `private` и `vk-zhkh-edge` с alias `vk-zhkh-web`. У приложения нет опубликованных host ports. VM override принудительно включает production/real и выключает demo; отсутствие MAX bot token/webhook secret/mini-app target теперь отклоняет `compose config` до запуска. Общий `compose.yaml` больше не требует фиктивный `DEMO_ACCESS_CODE` при выключенном demo.
- Добавлены только фрагменты маршрута/сети общего веб-входа в `infra/`; текущие файлы VM не редактировались. `docs/deployment.md` задаёт read-only preflight, границы `/srv/team/vk-hackathon/{deploy,runtime}`, изолированный запуск, сохранение чужих маршрутов, проверку внутреннего/внешнего пути, MAX и DB dump/restore в отдельной БД.
- Backend image устанавливает публичный корневой сертификат Минцифры в собственный CA store через `update-ca-certificates`; Dockerfile сверяет SHA-256 файла. TLS verification и проверка имени хоста не отключались. Источник, DER/PEM fingerprint и обновление описаны в `infra/certs/README.md`.

### Фактические проверки

| Уровень | Команда/факт | Результат |
|---|---|---|
| Git/checkout | `agent-b/e4` от d223, clean; push origin | Code/doc SHAs выше опубликованы; чужие файлы сохранены. |
| Compose parser и топология | Portable Docker Compose v5.5.1 `-p vk-zhkh -f compose.yaml -f compose.vm.yaml config --quiet` с синтетическими env; JSON config разобран без вывода значений | Exit 0; modes production/real/no demo; сети db/api/migrate=`private`, worker=`private,max_egress`, web=`private,edge`; private internal, edge external/alias; ни у одного сервиса нет host ports. Local override config тоже exit 0. Это parser, не работающая Docker сеть. |
| Негативный config | По одному удалены синтетические `MAX_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_WEB_APP`, затем VM `config --quiet` | Все три отсутствия отклонены с ненулевым кодом до запуска. Секреты не использовались/не выводились. |
| Backend/HTTP | `%TEMP%/vk_zhkh_b_e2_python/Scripts/python.exe -m pytest apps/backend/tests -q --tb=short`; `scripts/check_http_contract.py` | 26 passed, 3 skipped (PG tests без URL), 1 Starlette warning; OpenAPI 3.1, 28 операций/25 примеров. |
| Отдельный PG16.2 и backup/restore | Новый `%TEMP%/vk_zhkh_e4_pg_20260927_01`, loopback 55443, отдельные `zhkh_e4_source`/`zhkh_e4_restore`; Alembic head; synthetic user; `pg_dump -Fc`, `pg_restore --list`, restore в другую БД | Оба DB имеют `e3_max_keyboard` и 1 synthetic user; dump 28717 bytes. Кластер остановлен, TEMP данные/dump сохранены. Служба Kompas и её данные не затронуты. Это PG16, не PG17/VM. |
| Внешний baseline до deploy | `curl.exe` с TLS verify на developer machine к существующим `/team/`, `/healthz`, `/team/zhkh/` | HTTPS `/team/` 200, `/healthz` 404, `/team/zhkh/` 404; `tls_verify_result=0` для всех. 404 внешнего `/healthz` не является внутренним healthcheck VM. |
| MAX TLS CA provenance | Официальный [MAX changelog](https://dev.max.ru/docs-api/changelog-api) требует `platform-api2.max.ru` и сертификат Минцифры; PEM получен из `http://nuc-cdp.digital.gov.ru/cdp/rootca_ssl_rsa2022.crt` 2026-09-27. DER SHA-256 `D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31` совпал с корнем доверенной Windows цепочки живого MAX. Git LF PEM SHA-256 `0819977502D9AED2234830F6FFB91F82F401D3674C6E51DD19E16D8B3DBF0EB4`; `git ls-files --eol` = i/lf w/lf. OpenSSL `s_client -verify_hostname platform-api2.max.ru -CAfile infra/certs/russian-trusted-root-ca.crt` | `Verification: OK`, `Verified peername: *.max.ru`, `Verify return code: 0`; без CA — код 20. Stdlib Python `ssl.create_default_context(cafile=...)` и tokenless GET `/me` получили HTTP 401 после успешного TLS. Это локальная проверка, не контейнер/VM. |
| VM read-only | B BatchMode получил `Permission denied (publickey)`; PTY дошёл до запроса passphrase и был отменён без ввода секрета. Координатор затем выполнил свежую интерактивную read-only инвентаризацию `ssh hackathon` 2026-09-27. | `/srv/team`: README.md, VK-bot/, web/; только healthy `team-web-nginx-1`, адрес 10.203.77.10:8080, `docker compose ls` только team-web. В текущем web Compose нет shared edge network; nginx.conf имеет /healthz, /team/, /. Свободно 74G диска и 14Gi RAM; внутри VM /team/ и /healthz HTTP 200, снаружи HTTPS /team/ HTTP 200 с TLS verify 0. Это свидетельство координатора, без изменения VM; B сам не вошёл. |
| Изолированный Linux CI | [GitHub Actions run 36333584617](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36333584617), integration SHA `2e357624e9f59287b09f2593e13dedf619d1e057` | **Success**: VM Compose config/topology, сборка образа с pinned CA, worker DNS и tokenless HTTPS к MAX, shared Nginx snippet syntax, PG17/E2–E3 и E4 browser. Это CI, не проверка конфигурации общего Nginx на живой VM, не MAX auth/POST. Текущий локальный Windows без Docker daemon. |
| MAX/VM deploy | Действующие MAX credentials, привязка mini-app и права регистрации пока не подтверждены; `/srv/team/vk-hackathon` и приватного app runtime на VM нет; новый accepted release SHA после egress fix не выдан | **Not deployed.** Никаких VM/Nginx/сетевых изменений, реального MAX POST, webhook registration, MAX Web/mobile проверки не было. |

### Следующий шаг

После успешного CI нужен новый принятый координатором release SHA, приватные MAX bot token/webhook secret, привязанный mini-app target и рабочий SSH-доступ для B. Затем проверить эти prerequisites вне Git, добавить только свой edge route/network в существующий team-web по §12.8, развернуть точный SHA и отдельно проверить internal VM, external HTTPS и реальный MAX Web/mobile. До этого production не запускать.

## E4-B deploy follow-up: prerequisite gate, 2026-09-27

- Задание: `tasks/e4/agent-b-deploy-followup.md` из `b09d930eb767c5cf64348b5d193c9880c0e24c72`; отдельная ветка `agent-b/e4b`, checkout чистый до этого отчёта. Единственный разрешённый кандидат развёртывания `01a271a506db1e65aedd68efc7101c761827d89a` существует локально как commit. Никакой branch HEAD или task/report commit вместо него на VM не отправлялся.
- Проверка только наличия: в процессе B отсутствуют `MAX_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_WEB_APP`; в checkout нет `.env` и `runtime/app.env`. Значения не читались и не выводились. Приватные реальные значения, привязка мини-приложения и права регистрации webhook оператору B не предоставлены/не подтверждены. Это решающий блокер production deploy; синтетические переменные CI не применимы.
- Координатор ранее успешно вошёл на VM интерактивным SSH и выполнил read-only инвентаризацию, описанную выше. В текущем процессе B `ssh-add -l` сообщает об отсутствии agent, а `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 hackathon hostname` завершился `Permission denied (publickey)`. Это отсутствие разблокированного ключа в данном процессе, а не доказательство недоступности VM.
- **Not deployed:** VM, общий Nginx, Compose, соседние проекты и секреты не менялись. Внутренний VM health, внешний `/team/zhkh/`, webhook registration и реальный MAX Web/mobile после развёртывания отсутствуют, потому что развёртывания не было.

Следующий шаг: передать B реальные MAX prerequisites защищённым каналом и подтвердить привязку mini-app/право регистрации; обеспечить интерактивный SSH или разблокированный agent. Затем B повторит read-only preflight непосредственно перед записью и выполнит §12.8 из чистого checkout **только** `01a271a506db1e65aedd68efc7101c761827d89a`, с раздельной фиксацией internal VM, external HTTPS и MAX результатов.

## E4-B инфраструктурное развёртывание: 2026-09-27

Задание `tasks/e4/agent-b-deploy-followup-2.md` из `df745c87190709e695eac8a63440fc81bf524173`. Ветка отчёта `agent-b/e4c`; отдельный docs SHA `2776ab35b11222693308e3706292f9f9b53403f6`. **На VM развёрнут только принятый код SHA `01a271a506db1e65aedd68efc7101c761827d89a`**, чистый detached checkout `/srv/team/vk-hackathon/deploy`; `runtime/release.sha` содержит этот SHA и имеет режим `0600`. Документальные commits этой ветки не разворачивались. Это техническое развёртывание, не общая приёмка E4/E5.

### Предварительная проверка и сохранность

- Git-for-Windows SSH с `BatchMode=yes`, `StrictHostKeyChecking=yes` и локальным разблокированным agent дал вход в `hackathon`. Прочитаны актуальные `/srv/team/README.md` и `/srv/team/web/README.md`. В 17:35 UTC до записи: `/srv/team/vk-hackathon` отсутствовал; единственный проект `team-web` и healthy `team-web-nginx-1`; сети `bridge`, `host`, `none`, `team-web_default`; новых app volumes не было; свободно 74G диска и 14Gi RAM. Старые внутренние `/team/` и `/healthz` дали 200.
- Токен получен из локального `TOKEN.txt`, для которого `git check-ignore` подтвердил исключение из Git; передан только по SSH stdin без печати/аргумента командной строки. Пароль БД и webhook secret сгенерированы случайно вне Git. `/srv/team/vk-hackathon/runtime` — `0700`, `runtime/app.env` — `0600`; Docker environment и обычный `compose config` без `--quiet` не выводились. Проверка последних 1000 строк логов пяти собственных контейнеров не нашла значений токена, webhook secret или пароля БД.
- До изменения общего входа закрытые копии `/srv/team/web/{compose.yaml,nginx.conf}` сохранены в `runtime/backup` с временем `20260927T174009Z`, режим `0600`. SHA-256 исходных файлов соответственно `5a5e2a5831f2283048e2f7846f1ee0b55a30d5d6b3bd2d59242adeb2bf5ff32b` и `0c0b8d1401f0b528a27f145cd978b07571dad483ae8a6d8ead4031dd763a7f8a`. Перед точечным изменением оба хеша повторно совпали; чужие services/routes/порт сохранены.

### Запуск и данные

| Проверка | Фактический результат |
|---|---|
| Compose и сеть | Создана только `vk-zhkh-edge`; приложение использует project `vk-zhkh`, приватную и worker egress сети, не публикует host ports. `docker compose --env-file ../runtime/app.env -p vk-zhkh -f compose.yaml -f compose.vm.yaml config --quiet` завершился 0; `up --build --quiet-build -d` после исправления режима checkout завершился 0. |
| Режим исходников | Первый `up` остановился на `migrate` exit 255: `No 'script_location' key found in configuration`. Причина — выбранный при clone `umask 0007`: Docker `COPY` сохранил `0660/0770`, а `USER app` не мог читать `/workspace/alembic.ini`. Только публичным файлам deploy checkout добавлено `a+r`, каталогам `a+rx`, исключая `.git` и закрытый runtime; world-write не добавлялся. `git status --porcelain` остался пуст, HEAD — тот же принятый SHA; `alembic heads` после rebuild показал `e3_max_keyboard`. Порядок записан в `docs/deployment.md`. |
| Сервисы | `team-web-nginx-1`, `vk-zhkh-db-1`, `vk-zhkh-api-1` healthy; `vk-zhkh-worker-1` и `vk-zhkh-web-1` running; `migrate` успешно завершён. PostgreSQL `17.11`, Alembic `e3_max_keyboard`; app-internal ready/meta ответили 200. Worker с проверкой TLS получил ожидаемый 401 на tokenless `GET https://platform-api2.max.ru/me`. |
| DB backup/restore | `runtime/backup/zhkh-20260927T175115Z.dump`, 29103 байта, `0600`; `pg_restore --list` прошёл. Восстановление в отдельную `zhkh_restore_20260927T175115Z` завершилось, версия Alembic там `e3_max_keyboard`; рабочая БД не перезаписывалась. Копия пока только на VM и сама по себе не защищает от потери VM. |
| Общий Nginx | В существующие файлы добавлены только сеть Nginx `vk-zhkh-edge` и два location `/team/zhkh`; `docker compose config --quiet` и `docker compose run --rm --no-deps -T nginx nginx -t` прошли. Пересоздан только `team-web-nginx-1`; прежний bind `10.203.77.10:8080:80` сохранён. |

### Внутренний HTTP, внешний HTTPS и MAX

- **VM internal** `http://10.203.77.10:8080`: `/team/`, `/healthz`, `/team/zhkh/`, JS asset, `/team/zhkh/health/ready`, `/team/zhkh/api/v1/meta` и вложенный `/team/zhkh/receipts` — 200; несуществующие API/asset — 404; `POST /team/zhkh/integrations/max/webhook` без секрета — 403. `meta.features.engine_stub=false`, `demo_auth=false`. С правильным секретом и заведомо некорректным `{}` webhook ответил 400 до очереди: заголовок принят, реальное событие не создавалось.
- **External HTTPS** с Windows через стандартную TLS-валидацию: тот же UI/JS/ready/meta/deep link — 200, несуществующие API/asset — 404, webhook без секрета — 403, старый `/team/` — 200. Внешний `/healthz` — 404 как и до deploy: это внутренний путь общего Nginx, не `/team/healthz`.
- **MAX API**: перед регистрацией [GET `/subscriptions`](https://dev.max.ru/docs-api/methods/GET/subscriptions) вернул 200 и 0 подписок. После публичного HTTPS smoke [POST `/subscriptions`](https://dev.max.ru/docs-api/methods/POST/subscriptions) с типами `message_created`, `bot_started` и приватным секретом вернул HTTP 200, `success=true`; повторный GET — одна подписка на наш webhook и ноль других. Авторизованный запрос и секрет не печатались. Реальных сообщений боту и обращений не отправляли; фактическая доставка MAX webhook и ответ бота пользователю пока не проверены.

### Качество, нагрузка и остаток

- В том же развёрнутом backend/worker image отдельный контейнер `--network none --cpus 1 --memory 1g --pids-limit 64` с read-only fixture mount прошёл `packages/housing_engine/tests/smoke_e2_ocr.py`: 7/7 синтетических растров/скан-PDF соответствуют ожидаемым outcomes (6 `recognized`, 1 `partial`), Tesseract 5.3.0 `eng+rus`. Итоги включают август `200.00`, сентябрь `270.00`, корректировки `220.00`, долг/оплату `290.00`, переплату `0.00`. Первый запуск без `PYTHONPATH=/workspace` завершился import error до OCR; повтор с явным путём прошёл. Это не оценка качества реальных квитанций.
- Ограниченный smoke на **своей private Docker сети**: 20 запросов `/health/ready` и 20 `/api/v1/meta`, concurrency 2, лимит контейнера 0.5 CPU/256 MiB/32 PIDs, 0 ошибок. Для ready p50/p95/max = 13.3/20.0/47.7 мс; для meta = 1.7/2.1/2.6 мс; суммарно 0.19 с. Это короткая проверка доступности, не нагрузочная гарантия и не проверка общего входа под трафиком.
- Публичный URL готов для передачи организаторам по FAQ через форму привязки; координатор запросил действие владельца. Привязка mini-app, подписанный initData в MAX Web/мобильном MAX, реальная доставка webhook, пилотные квитанции и локальные УК/поставщики остаются непроверенными. Синтетический каталог и учебный макет явно отмечены в README/demo. **Готовность продукта и приёмка E4/E5 не объявляются.**
