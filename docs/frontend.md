# Frontend

## E2: одна платёжка

После загрузки `/processing?job=<id>` автоматически опрашивает `GET /jobs/{id}`. При `succeeded` ссылка ведёт на `/review?id=<receipt_id>`. Проверка заново загружает `GET /receipts/{id}`, показывает защищённый PNG preview из `GET /receipts/{id}/pages/1` и исходник через `GET /receipts/{id}/source`; URL файла не содержит session token. Если исходник истёк, UI сохраняет доступ к данным и прямо сообщает об отсутствии страницы. На узком экране страницу можно открыть крупно отдельной ссылкой на локальный Blob URL.

Редактор меняет BillData, включая строки и перерасчёты, нормализует запятую в числах и отправляет `PUT /receipts/{id}/draft` с `expected_revision`. Клиент не вычисляет начисления. При 409 UI загружает актуальную ревизию, сохраняет введённые правки в форме и предлагает явно применить их к новой версии либо взять серверную. `POST /receipts/{id}/confirm` отправляется только после сохранения правок, заполнения обязательных полей и принятия предупреждений; используется UUID Idempotency-Key. Экран `/explanation?id=<receipt_id>` запрашивает текущую ревизию и `GET /receipts/{id}/explanation?revision=...`, отображает серверные суммы, строки, расхождения, ограничения и источники без расчёта в браузере. После повторного входа путь с ID сохраняется.

Учебный MSW имитирует queued → running → succeeded, partial OCR, правку, 409, подтверждение и объяснение на **синтетическом** `fixtures/receipts/demo-bill-2026-08.png`; копия preview лежит в `apps/web/public/synthetic-receipt.png` с тем же SHA256 `5d1c0904398857a9941afed423bdd6b0c6667873a06ac6d7ce2ec26eb50bcc53`. Mock file и worker доступны только в `dev:mock`; production `dist` их не содержит. Этот сценарий не доказывает реальный OCR.

Воспроизводимая браузерная проверка: запустите `npm run dev:mock -- --port 5173`, задайте `CHROME_PATH` к локальному Chrome/Chromium, затем `npm run test:browser:e2` из `apps/web`. Скрипт проверяет 360 px, upload → polling → preview → конфликт ревизий с сохранением правок → edit → confirm → explanation → 401 на том же `/review?id=...`. Снимок экрана сохраняется только при `E2_SCREENSHOT=<путь вне Git>`. Unit/API проверки: `npm test`; сборка: `npm run build`.

Живые E2 endpoints B подключаются после принятого координатором checkpoint. До него есть только mock доказательство этого сквозного UI; E1 dev backend поддерживает upload/job, но не публичные edit/confirm/explain. История, сравнение, FAQ, черновики и MAX Bridge относятся к следующим этапам.

## E1: первый запуск и dev API

`npm run dev:mock` даёт учебный вход и полностью локальные MSW ответы. `npm run dev:real` отключает MSW и проксирует `/team/zhkh/api/**` на локальный backend `http://127.0.0.1:8000/api/**`. Оба режима используют те же экраны и публичный префикс. Локальный код демовхода вводится в форму; он не зашит в клиент и не сохраняется в браузере. В production build dev auth и MSW не подключаются.

Для проверки с B из принятого integration checkout запустите backend с `APP_MODE=dev`, `ENGINE_MODE=stub`, `DEMO_AUTH_ENABLED=true`, `DEMO_ACCESS_CODE=<локальный код>`, `STORAGE_PATH=<локальный закрытый каталог>` и командой:

```sh
python -m uvicorn app.main:app --app-dir apps/backend --host 127.0.0.1 --port 8000
```

Затем из `apps/web` выполните `npm ci` и `npm run dev:real`. Откройте `http://127.0.0.1:5173/team/zhkh/` (или порт, показанный Vite). Выберите dev учётную запись, введите локальный код, на экране первого запуска выберите роль/территорию и подтвердите версию уведомления из `GET /meta`. После сохранения `PUT /me/profile` становится доступна загрузка. `POST /receipts` отправляет файл и UUID Idempotency-Key; экран обработки читает `GET /jobs/{id}`. В E1 успешная загрузка означает постановку в очередь. При `engine_stub=true` завершение задания не означает OCR: для документа потребуется ручной ввод. Без PostgreSQL backend использует только dev MemoryStore, и данные не переживают перезапуск.

На 401 session token удаляется из памяти, форма повторного входа открывается на текущем URL, включая `/processing?job=...`; серверный ID задания остаётся в адресе. Общий вопрос до профиля работает в MSW. В текущем dev API B endpoint ответов ещё не подключён, и UI это показывает явно.

Проверка локального Chrome и dev API не является приёмкой MAX Web/mobile или VM.

## Экранная карта

Все pathname расположены под `/team/zhkh/`; `BrowserRouter` использует `basename=/team/zhkh`, а Vite `base=/team/zhkh/`.

| Путь | Экран | Запланированные состояния по ТЗ §11.1 |
|---|---|---|
| `/` | Главная и вход | проверка MAX, ошибка подписи/сессии, вне MAX; пустая история, demo |
| `/onboarding` | Первый запуск | незаполнено, сохранение, ошибка |
| `/assistant` | Помощник | loading, уточнение, unsupported, ошибка сети |
| `/upload` | Загрузка | upload, rejected, retry |
| `/processing` | Обработка | queued, processing, failed, completed |
| `/review` | Проверка | missing, warning, invalid, сохранение, revision conflict |
| `/explanation` | Объяснение | complete, partial, source expired |
| `/comparison` | Сравнение | несовместимость, уточнение идентичности, ambiguous, partial |
| `/draft` | Черновик | copied, clipboard unavailable, stale |
| `/history` | История и настройки | empty, pagination, удаление, ошибка |

Навигация ведёт на главную, первый запуск, вопрос, загрузку и историю. Из обработки доступна проверка, затем объяснение. Сравнение, черновик и история пока показывают заглушки; их реализация относится к E3.

## Запуск и границы E0

Node 22.23.3 использовался при проверке. Из `apps/web`:

```sh
npm ci
npm run generate:types
npm run dev:mock
npm test
npm run build
```

`dev:mock` включает MSW только при `import.meta.env.DEV` и `VITE_ENABLE_MOCK=true` из `.env.mock`. Обычный `npm run dev` не включает mock. Production build не копирует worker и синтетический preview в `dist` и не загружает mock-модуль. Demo access code в mock фиксированная учебная строка, не секрет. Реальный вход MAX ещё не подключён; локальный dev API B подключён в режиме `dev:real`.

Типы `src/api/openapi.generated.ts` созданы из принятого `contracts/http/openapi.yaml` checkpoint `d0170da1cb97d5e7a128b70b79fd4e445f352702`. `src/api/types.ts` даёт короткие aliases на generated DTO. `openapi-typescript@7.13.0` требует TypeScript 5.x, поэтому закреплён TypeScript 5.9.3. При генерации из внешнего `contracts/engine/v1/BillData.schema.json` инструмент ошибочно добавляет служебный JSON Schema ключ `$defs` как обязательное поле экземпляра `components['schemas']['BillData.schema']`. Alias `Omit<..., '$defs'>` убирает только этот служебный ключ; вложенные `services`, `adjustments`, `settlement` остаются сгенерированными типами. Тест проверяет реальный `contracts/http/examples/receipt-confirmed.json` по JSON Schema C, отсутствие `$defs` и тип вложенного `service_code`.

Токен сессии хранится только в памяти модуля `src/api/client.ts`. Запросы поддерживают `AbortSignal`; ошибки нормализуются из общего envelope. Искусственные тарифы из §7.7 только в MSW, клиент не вычисляет суммы.

Mock meta содержит все обязательные поля принятого OpenAPI; 401/409, partial/unsupported сверены с его кодами и состояниями. `partial` остаётся синтетическим вариантом §7.7, потому что HTTP-пример B для неизвестного макета имеет `manual_required`.
