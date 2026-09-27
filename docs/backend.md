# Backend: E0 проектная схема и E1 dev реализация

Разделы ниже описывают E0 проектную схему. В E1 реализованы базовые таблицы,
миграция, закрытое хранилище документов и persisted worker с явным dev stub.
MAX, настоящий OCR, сравнение и production запуск ещё не интегрированы.

Статус: проектная схема, 2026-09-27. Таблицы, worker, storage и MAX здесь ещё не реализованы. Источник требований — `TECHNICAL_SPEC.md` §§6, 7, 11, 12. Контракты содержимого принадлежат `housing_engine`; backend использует их через один адаптер.

## Данные и границы владельца

| Таблица | Ключи и связи | Инвариант |
|---|---|---|
| `users` | UUID PK; `max_user_id` bigint UNIQUE NULL; `demo_identity` UNIQUE NULL | ровно один способ идентификации; ID MAX никогда не служит публичным UUID |
| `profiles` | `user_id` PK/FK → users | роль, территория, версия и время подтверждения уведомления |
| `sessions` | UUID PK; `user_id` FK; `token_hash` UNIQUE | только хеш токена, expiry и отзыв; токен возвращается единожды |
| `receipts` | UUID PK; `user_id` FK; `document_id` FK NULL | статус, текущая ревизия, источник данных и outcome; пользовательский фильтр во всех чтениях |
| `receipt_revisions` | PK (`receipt_id`, `revision`) | неизменяемые JSONB снимки BillData, evidence, validation, engine version; удаляются с квитанцией |
| `documents` | UUID PK; `user_id` FK | непрозрачный storage key, SHA-256, MIME, size, pages, expiry, deleted_at; нет публичного URL |
| `jobs` | UUID PK; уникальный бизнес-ключ | владелец, вид, resource, state, attempt, lease, run_after, error code, timestamps |
| `drafts` | UUID PK; `user_id` FK | ревизия, текст, recipient и refs; изменение по compare-and-swap |
| `assistant_answers` | UUID PK; `user_id` FK | вопрос, тема, DTO ответа и версия знаний; устаревание вычисляется при чтении |
| `idempotency_keys` | UNIQUE (`user_id`, `route`, `key`) | fingerprint нормализованного запроса и исходный HTTP результат на 24 часа |
| `webhook_inbox` | dedup key UNIQUE | минимальный нормализованный payload, без всего webhook body |
| `outbox` | бизнес-ключ ответа UNIQUE | адресат, минимальный payload, попытки и неизвестный исход доставки |
| `events` | UUID PK | код события, результат и длительность без PII/текстов/токенов |

Снимок квитанции изменяется только добавлением новой ревизии и атомарным обновлением `receipts.current_revision`. После создания из загрузки `queued` означает ревизию 1 без строки в `receipt_revisions`; worker может один раз вставить снимок 1. Пользовательская правка/подтверждение используют `WHERE current_revision = expected_revision` и состояние в той же транзакции. Подтверждение создаёт новую ревизию; повтор идемпотентного запроса возвращает сохранённый результат. Для чтения чужих UUID возвращается 404; удаление чужого/несуществующего UUID возвращает 204.

Индексные кандидаты: `receipts(user_id, created_at DESC, id DESC)`, `jobs(state, run_after, lease_until)`, `documents(expires_at)`, `sessions(expires_at)`, `idempotency_keys(expires_at)`; окончательные миграции и план запроса проверяются в E1. Cursor включает последнюю пару времени/UUID и подписывается или хранится как непрозрачный токен. Максимум страницы 50, default 20.

## Очередь и файлы

`POST /receipts` сначала проверяет байты, MIME, размер, число страниц, лимиты пользователя/очереди и актуальное privacy acknowledgement. Файл получает случайный storage key в закрытом томе. Создание документа, квитанции и задания завершается согласованно; при ошибке БД временный файл удаляется. API не делает OCR через `BackgroundTasks`.

Один dispatcher выбирает задание короткой транзакцией `FOR UPDATE SKIP LOCKED`, присваивает 180-секундную аренду и запускает OCR в отдельном дочернем процессе. Родитель обновляет heartbeat раз в 30 секунд и продолжает обслуживать удаление, inbox/outbox и короткие задания. Бюджет OCR 90 секунд; через 120 секунд завершается дерево процесса. Истёкшая аренда допускает повтор, максимум три попытки только для временного сбоя. Повреждённый/зашифрованный файл, ресурсный предел и неизвестный макет не ретраятся автоматически. До сохранения результата проверяются lease owner, существование ресурса и допустимое состояние; уникальная `(receipt_id, revision)` не позволяет вставить результат дважды.

Удаление квитанции сразу отзывает доступ, ставит отмену задания и удаление содержимого в очередь, которая переживает рестарт. Worker перед записью результата повторно проверяет удаление. При живом worker физическое удаление связанных source/preview/снимков должно завершаться в 60 секунд. Файлы никогда не лежат под web root и не имеют публичных ссылок. Preview страниц строится отдельным процессом B из закрытого файла; `409 PREVIEW_NOT_READY` и `503 PREVIEW_UNAVAILABLE` не блокируют ручной ввод. Оригинал и страницы живут 7 дней; данные квитанций и связанные ответы/черновики — 30; inbox/outbox — максимум 24 часа после обработки. Backup DB без source-файлов хранится вне Git и учитывается при удалении.

## Режимы и адаптер

`APP_MODE=dev|demo|production`. Демовход доступен только при `DEMO_AUTH_ENABLED=true` и не в production, требует серверный код и две фиксированные identity `reviewer_a`, `reviewer_b`. Они создают двух разных пользователей, и каждый запрос к документу, заданию, ответу и черновику ограничен `user_id`. `ENGINE_MODE=stub` допускается лишь локально в dev и явно отражается `meta.features.engine_stub`; итоговый стенд запускается с `real`. Настоящие токены/MAX secrets, БД URL и `.env` остаются вне Git; `VITE_*` не содержат секретов.

Единственная граница к C — `apps/backend/app/services/engine_adapter.py`. Он принимает сохранённый BillData/bytes после проверки владельца, ревизии и состояния, вызывает публичные функции `housing_engine` и превращает `EngineError` в безопасный HTTP envelope или состояние job. Формулы, OCR, DTO и знания C здесь не копируются. C не получает session/MAX ID, токены или доступ к БД. Контрактное соединение nested DTO ожидает принятый SHA C; это не помечено готовым.

## Развёртывание позже

E0 не меняет VM. Будущие `compose.yaml` и VM override имеют project `vk-zhkh`: `db`, `migrate`, `api`, `worker`, `web`; только `web` вступает в выделенную сеть общего Nginx, без host ports в базовом Compose. Применение разрешено из принятого release SHA по §12.8. Локальный override публикует только loopback `127.0.0.1:8080` и сохраняет публичный префикс `/team/zhkh/`. Не размещать в Git полные общие конфиги VM.

## Проверка E0 HTTP-контракта

Из корня checkout, в отдельном Python-окружении:

```sh
python -m pip install -r scripts/requirements-contracts.lock
python scripts/make_http_examples.py
python scripts/check_http_contract.py
```

Проверка валидирует OpenAPI 3.1, точные 28 операций §7 и webhook, ссылки на схемы C, совпадение полей и обязательности server/engine view, а также все JSON-примеры по JSON Schema с проверкой UUID/date-time. Генератор примеров берёт BillData из принятого C fixture. Исходные поля C не переписаны в HTTP schema: ссылки ведут в `contracts/engine/v1`. Для повторения проверки не требуются Docker, MAX, VM или токены.

Примеры ответов, кроме `meta-dev.json`, показывают будущую форму данных и не являются доказательством работающих endpoint. `meta-dev.json` показывает честное состояние каркаса E0: `engine_stub=true`, OCR/сравнение/демовход выключены, версии engine/knowledge неизвестны. Значения `features` в реальном API должны отражать запущенные функции; production со stub не принимается.

## E1 ранний dev checkpoint

`apps/backend/app/main.py` сейчас запускает только dev `MemoryStore`. Для проверки связки A ↔ B доступны `GET /api/v1/meta`, `POST /api/v1/auth/demo`, `GET /api/v1/me`, `PUT /api/v1/me/profile`, `GET /api/v1/catalog`, `POST /api/v1/receipts`, `GET /api/v1/receipts/{id}`, `GET /api/v1/jobs/{id}`. OCR ещё не выполняется: job остаётся `queued`, `meta.features.receipt_ocr=false`, `engine_stub=true`; `GET /health/ready` отвечает 503. Состояние `MemoryStore` не переживает перезапуск. При заданном `DATABASE_URL` этот checkpoint отказывается запускаться, поэтому его нельзя случайно принять за PostgreSQL-реализацию.

Пример локального запуска из корня checkout после установки `apps/backend/requirements.lock` (секретный dev-код выбирается локально, не коммитится):

```powershell
$env:APP_MODE = 'dev'
$env:ENGINE_MODE = 'stub'
$env:DEMO_AUTH_ENABLED = 'true'
$env:DEMO_ACCESS_CODE = '<локально выбранный код>'
python -m uvicorn app.main:app --app-dir apps/backend --host 127.0.0.1 --port 8000
```

В другом терминале: `curl.exe http://127.0.0.1:8000/api/v1/meta`. Авторизация demo принимает `identity=reviewer_a` или `reviewer_b`; перед загрузкой вызовите `PUT /api/v1/me/profile` с `privacy_notice_version` из meta и `privacy_acknowledged=true`. Загружайте PDF/JPEG/PNG через `multipart/form-data` с UUID в `Idempotency-Key`. Этот прямой API доступен A для dev-интеграции; публикация под `/team/zhkh/` появится в Compose позже в E1.

## E2: проверка квитанции в изолированном Compose

E2 запускает `ENGINE_MODE=real`: worker читает закрытые bytes из тома, запускает `extract_receipt` и `validate_bill` в отдельном дочернем Python-процессе, сохраняет JSONB-снимок ревизии и отдаёт `recognized`, `partial` либо `manual_required` без подстановки ответа по имени файла. OCR движка ограничен 90 секундами, родительский worker ждёт дочерний процесс не более 120 секунд, обновляет heartbeat, выполняет retention и проверяет отмену не реже раза в 25 секунд, затем убивает всё дерево процесса (POSIX process group в Linux Compose). Inbox/outbox как короткие задачи относятся к E3 и в E2 не выполняются. `GET /pages/{page}` читает готовый PNG-превью из закрытого хранилища; до окончания обработки возвращает 409. Данные одной квитанции доступны только её владельцу; чужой UUID даёт 404, удаление чужого/несуществующего UUID — 204. Исходник и превью удаляются через 7 дней, производные ревизии — через 30 дней. Повтор failed job разрешён только пока сохранён исходник.

`PUT /draft` создаёт новую ревизию через `expected_revision`, включая правку после подтверждения; прежняя подтверждённая ревизия остаётся неизменной, текущая становится `needs_review`. `POST /confirm` создаёт неизменяемую подтверждённую ревизию после повторного `validate_bill` и явного подтверждения всех warning codes, которые видны в `ReceiptView.issues`. `GET /explanation` принимает только текущую подтверждённую ревизию и вызывает публичный `explain_receipt`. `template_id`, `template_version`, `settlement.formula_kind` и `calculation_kind` принадлежат серверу: полный BillData в запросе нужен для снимка, но значения этих полей сервер восстанавливает. Для известного `line_id` сохраняется classification движка, новая строка получает безопасный `document_amount`. Ручной ввод получает `manual-v1` и формулу `unsupported`. Текущие объяснения арифметические, `sources=[]` и issue `ARITHMETIC_ONLY`; внешние тарифы и юридические утверждения не подтверждаются.

В отдельном локальном Compose project с личным `.env` (секреты вне Git) HTTP проверка выполняется в два шага:

```sh
BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=<private> python scripts/smoke_e2_http.py start --state /tmp/e2-smoke-state.json
docker compose --project-name <isolated> --env-file .env -f compose.yaml -f compose.local.yaml restart api worker
BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=<private> python scripts/smoke_e2_http.py verify --state /tmp/e2-smoke-state.json
```

Скрипт передаёт синтетический текстовый PDF как multipart bytes, ждёт persisted job, проверяет извлечение → edit CAS → confirm → explain. Затем загружает синтетический PNG и проверяет работу контейнерного Tesseract, `source=ocr`, `needs_review` и предупреждение `OCR_REVIEW_REQUIRED`. После restart читает обе квитанции и то же подтверждённое объяснение. В state file только UUID квитанций и номер ревизии, без токена или кода. Этот сценарий не проверяет MAX и VM.

## E3 MAX webhook checkpoint (2026-09-27)

`/api/v1/auth/max` verifies signed initData and exchanges it for a revocable
server session. The validation follows the [official MAX WebApp algorithm](https://dev.max.ru/docs/webapps/validation):
the HMAC key is derived with `WebAppData`, then the decoded sorted parameter
string is signed. `auth_date` is limited to five minutes with 30 seconds of
future skew. Raw initData and tokens are never logged.

`POST /integrations/max/webhook` compares `X-Max-Bot-Api-Secret` in constant
time, normalizes a bounded update, commits the minimal payload to
`webhook_inbox`, and only then returns 200. The worker performs one inbox or
outbox unit per idle cycle and during the OCR child tick. Replays share a
deduplication key. Direct `/start` and `/help` have text responses; attachments
are directed to mini-app upload. Direct text questions call C's same local
knowledge function and persist an owner-scoped answer. Group content is not stored or
answered. The outbox marks unknown network outcomes `uncertain` and does not
automatically resend them. All inbox and outbox records expire within 24 hours.

`/start` persists a MAX inline keyboard with a `message` button to prompt a
question and an `open_app` button for receipt upload. `MAX_WEB_APP`, if set to
the registered bot username or its `max.ru` link, is sent as `web_app`; linking
and opening the real mini-app still require a live MAX client check.

Outbound messages use the [official MAX POST /messages](https://dev.max.ru/docs-api/methods/POST/messages)
with `Authorization` header and `user_id` query parameter; redirects are
rejected to avoid forwarding credentials. The [Update object](https://dev.max.ru/docs-api/objects/Update)
describes the accepted envelope. These are synthetic contract checks only;
live MAX delivery requires credentials and E4 acceptance.

## E3 persisted answers and drafts

`POST /api/v1/assistant/answers` derives role and territory from the stored
profile and loads the fixed local knowledge catalog. An optional receipt must
be owned by the requester and at its current confirmed revision. The engine
produces the answer, including clarification or unsupported status; the API
stores its version and provenance for 30 days. Reads recalculate stale reasons
from the receipt revision, source review dates and catalog version. Stale
cards do not expose their old actions.

The backend validates the installed knowledge bundle at startup. `/meta` reports
that exact version; `/catalog` derives territories, topics and organizations
from the same bundle. Profile territory updates accept only catalog IDs.
Local Moscow/Moscow Oblast routing remains unavailable until a verified
regional source and organization are added by C; displaying a region in the
catalog does not imply a verified local instruction.

`POST /api/v1/drafts` uses at most two owned current confirmed receipts and
the public C draft function. Creation has a 24-hour idempotency record. The
text is editable by revision CAS and can be copied by the user; there is no
send route. Reads mark a draft stale when a receipt, source or knowledge
version changes. Deleting a receipt removes associated answers, drafts and
their draft idempotency records. The demo catalog has no verified local
recipient, so the draft recipient remains null.
