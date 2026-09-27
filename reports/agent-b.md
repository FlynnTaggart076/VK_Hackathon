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
