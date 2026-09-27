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

E2 запускает `ENGINE_MODE=real`: worker читает закрытые bytes из тома, вызывает публичные `extract_receipt` и `validate_bill`, сохраняет JSONB-снимок ревизии и отдаёт `recognized`, `partial` либо `manual_required` без подстановки ответа по имени файла. `GET /pages/{page}` читает готовый PNG-превью из закрытого хранилища; до окончания обработки возвращает 409. Данные одной квитанции доступны только её владельцу; чужой UUID даёт 404, удаление чужого/несуществующего UUID — 204. Исходник и превью удаляются через 7 дней, производные ревизии — через 30 дней. Повтор failed job разрешён только пока сохранён исходник.

`PUT /draft` создаёт новую ревизию через `expected_revision`; `POST /confirm` создаёт неизменяемую подтверждённую ревизию после повторного `validate_bill` и явного подтверждения warning codes. `GET /explanation` принимает только текущую подтверждённую ревизию и вызывает публичный `explain_receipt`. `template_id`, `template_version`, `settlement.formula_kind` и `calculation_kind` принадлежат серверу: полный BillData в запросе нужен для снимка, но значения этих полей сервер восстанавливает. Для известного `line_id` сохраняется classification движка, новая строка получает безопасный `document_amount`. Ручной ввод получает `manual-v1` и формулу `unsupported`. Текущие объяснения арифметические, `sources=[]` и issue `ARITHMETIC_ONLY`; внешние тарифы и юридические утверждения не подтверждаются.

В отдельном локальном Compose project с личным `.env` (секреты вне Git) HTTP проверка выполняется в два шага:

```sh
BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=<private> python scripts/smoke_e2_http.py start --state /tmp/e2-smoke-state.json
docker compose --project-name <isolated> --env-file .env -f compose.yaml -f compose.local.yaml restart api worker
BASE_URL=http://127.0.0.1:8080/team/zhkh DEMO_ACCESS_CODE=<private> python scripts/smoke_e2_http.py verify --state /tmp/e2-smoke-state.json
```

Скрипт передаёт синтетический текстовый PDF как multipart bytes, ждёт persisted job, проверяет извлечение → edit CAS → confirm → explain. Затем загружает синтетический PNG и проверяет работу контейнерного Tesseract, `source=ocr`, `needs_review` и предупреждение `OCR_REVIEW_REQUIRED`. После restart читает обе квитанции и то же подтверждённое объяснение. В state file только UUID квитанций и номер ревизии, без токена или кода. Этот сценарий не проверяет MAX и VM.
