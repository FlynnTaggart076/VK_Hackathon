# Отчёт агента A — E4-A-01

Статус: независимый frontend код и локальные проверки завершены; реальный E4 Compose browser gate и MAX Web/mobile ожидают внешнего запуска. Ветка `agent-a/e4`, BASE_SHA `d223c4e49a12c4ebc5d98c3c8da8fc6c0202e16f`, TASK_COMMIT `40f0e8a1995f4a44f44f174cfa51f2f6acdae2c5`. Pushed code SHA: `3116955d4d7eceac08c08ba4ca8bd0a082c304ed`, `671c3513580c71efa47d4e36f47d03e74213fbe0`, `802f26d867179b6e221f79d8318e7dbdb00f8d56`, `2a9e7c43c791dbba3d78f2077d8f9f2513bf2854`.

## Изменения

- Production UI загружает MAX Bridge и отправляет только `window.WebApp.initData` в `POST /auth/max`. Подпись проверяет backend; `initDataUnsafe` не используется. Session token остаётся в памяти. После 401 UI просит переоткрыть mini-app, не повторяет автоматически обмен старыми стартовыми данными. Внешний браузер без Bridge не предлагает демовход.
- История после сбоя сети предлагает повтор и не показывает ложное пустое состояние. 413 даёт понятное действие с размером файла; preview можно повторить после ошибки или `PREVIEW_NOT_READY`. Серверный 409 сохраняет локальные правки и предлагает выбор ревизии.
- `apps/web/scripts/e4-real-resilience.mjs` предназначен для Vite `dev:real` → Compose API/worker/PG17: network abort/retry, реальные ответы 413/409/401, `manual_required` на синтетическом unknown-layout PDF, provenance, unknown без придуманного источника, 360/1280 px и deep-link reload. `e4-bridge-sim.mjs` проверяет production ветку с подставленным Bridge и API; это явно симуляция.

## Фактические проверки

Среда A: Windows PowerShell, Node 22.23.3 (`C:\Users\Stepan\AppData\Local\Temp\codex-node-v22.23.3\node-v22.23.3-win-x64`), Chrome headless `C:\Program Files\Google\Chrome\Application\chrome.exe`. Из `apps/web`: `npm ci --no-audit --no-fund` — 133 пакета; `npm test` — 14/14; `npm run build` — успешно; `node --check scripts/e4-real-resilience.mjs` и `node --check scripts/e4-bridge-sim.mjs` — успешно. Поиск в production `dist` по `mockServiceWorker|mock-only|auth/demo|DEMO_ACCESS_CODE|synthetic-receipt` не дал совпадений.

Для браузерной симуляции: `npm exec vite preview -- --host 127.0.0.1 --port 5175 --strictPort`; затем `BASE_URL=http://127.0.0.1:5175/team/zhkh/`, `CHROME_PATH=<локальный Chrome>`, `npm run test:browser:e4:bridge-sim` — **SUCCESS**. Подставленная сырая строка ушла в тело `/auth/max`, не в URL; после подставленного 401 сохранился `/team/zhkh/review?id=...`, повторной авторизации не было, session token не появился в localStorage. Отдельная страница без Bridge показала вход только внутри MAX. Это не подписанный вход MAX и не реальный backend.

[GitHub Actions E4 run 36332663523](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36332663523) на `integration/e4` SHA `71b7096f0289a6c561f3f0d0b0c18cf3ba55c64a` завершился Failure на проверке MAX egress (`urllib.error.URLError: CERTIFICATE_VERIFY_FAILED`). Результата `e4-real-resilience.mjs` из этого run нет; не считать E4 real API сценарий пройденным. Более ранний [E3 real Compose CI](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36329625261) прошёл stale draft/copy-only, FAQ unknown и 360 px на E3 SHA `065c8e0575a0ad97b83a6202c7a1988032816a6e`; это базовая проверка прошлого этапа, не повторный E4 результат.

## Ограничения и следующий шаг

Реальные MAX Web/mobile, подписанный `initData`, VM URL и реальная пилотная квитанция ещё не проверены. На Windows нет локального Compose daemon. Нужен повтор CI после исправления TLS preflight и фактический запуск `npm run test:browser:e4:real` с внешним `BASE_URL`, `DEMO_ACCESS_CODE`, `CHROME_PATH`; затем тот же сценарий внутри зарегистрированного MAX Web и мобильного клиента по развёрнутому release SHA. `apps/web/public/mockServiceWorker.js` имеет только CRLF локальную разницу, не включён в commits. Старые worktrees не тронуты. Голос и отправка обращений не реализованы.

---

# Отчёт агента A — E3-A-01

Статус A: review, frontend browser gate прошёл; E3 в целом ожидает независимой проверки качества FAQ. Окончательная приёмка E3 у координатора. Ветка `agent-a/e3`, `BASE_SHA` `b33ed1e0493d76dfd7051a141e2075c698f8e967`, `TASK_COMMIT` `c11b5235319c12ecb18a6c4ca05c35a54f5c0560`, контракт engine/HTTP 1.0.

Ключевые pushed SHA A: ранний mock/UI `b10026f6aabe38373124068934c7912700d97467`; demo import/history `2970ea7c26bcdbf7e59819256a862bd7d471db76`; real comparison browser `3abc57ffe88c406ca3622a214708dcb7bf8f97bf`; E2 selector fix `1b012d63829e859e7e5ffd0b936e806641da9888`; real FAQ/draft UI `d6db7886f8de480b12178ccf6f40207bfbdb57d7`; receipt-context FAQ and extended real browser `46439b965bd16024c4d97e895112b9d67b91aa91`; attached option fix `7142b8c4ca05097481bd8dc5f16e24f5a0ebd7bb`; stale copy assertion fix `9a1ecf90c1f7be1a4ec4b3b6a8c711500c086c42`; frontend docs `1e551045c4d993133a9d4d81c3737f0ef6ce0f00`.

## E3 результат

- `/history` читает серверную pagination и provenance, возобновляет job через `GET /receipts/{id}`, сообщает об истечении исходника при 410, удаляет только после подтверждения. `/comparison` выбирает две текущие confirmed ревизии и отображает серверные разницы 70/40/30, не вычисляя деньги в браузере; identity acknowledgement требуется до итогов, partial/ambiguous остаются явно неполными.
- `/assistant` использует 15 тем и территории из каталога, текущую роль профиля и подтверждённую ревизию квитанции при вопросе по документу; показывает уточнение, проверенные источники с территорией/сроком, unsupported и безопасные действия. Проверенные местные каналы без данных организации не обещаются.
- `/draft` показывает факты confirmed строки, получателя/actions, редактирование с CAS, copy-only и отдельное предупреждение при stale. Отправки обращения нет. Учебные образцы UI берёт из `catalog.demo_receipts` через защищённый `POST /receipts/demo`; PDF не размещены в `apps/web/public`.

## E3 проверки

Локально: Windows PowerShell, Node 22.23.3 в `C:\Users\Stepan\AppData\Local\Temp\codex-node-v22.23.3\node-v22.23.3-win-x64`, Chrome headless. Из `apps/web`: `npm ci` (133 packages), `npm test` (13/13), `npm run build` (успех), `node --check scripts/e3-real-flow.mjs` (успех). Production `dist` проверен поиском `mockServiceWorker|mock-only|demoAuth|VITE_ENABLE_MOCK`: совпадений нет.

`npm run dev:mock -- --port 5174` и `E3_MOCK_URL=http://127.0.0.1:5174/team/zhkh/`, `CHROME_PATH=<локальный Chrome>`, `npm run test:browser:e3:mock`: Chrome 360×800 прошёл история → compare 70/40/30 → черновик → уточнение «справка» → unknown, `innerWidth=360`, `scrollWidth=360`. Это MSW с синтетическими данными, отдельно от real API.

Linux Compose PG17: [GitHub Actions E3 CI #36329625261](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36329625261) на `integration/e3` SHA `065c8e0575a0ad97b83a6202c7a1988032816a6e` — **SUCCESS**. Координатор запустил `npm run test:browser:e3:real` с `BASE_URL=http://127.0.0.1:5173/team/zhkh/`, локальным `DEMO_ACCESS_CODE` и `CHROME_PATH` из CI env; Vite `dev:real` проксировал к Compose web/API/worker/PG17. Проверены два demo import, confirm, серверные 70/40/30, reload, общий источник ГИС ЖКХ, unknown, черновик/save/copy-only/stale после изменения ревизии и явное подтверждение устаревших фактов, 360 px. Тот же CI проверил E2/E3 HTTP, миграции/readiness, offline MAX webhook и PG replay. Это real dev HTTP/worker/PG17 на синтетических данных, не VM/MAX live.

Ограничения: локального Docker daemon нет; VM/MAX Web/mobile и реальные квитанции не проверялись. Независимый FAQ quality gate координатора пока 49/60 на отдельном наборе; E3 нельзя принять до его завершения. `apps/web/public/mockServiceWorker.js` имеет CRLF-only локальный статус, в commits не включён; прежние worktrees сохранены. Следующий шаг — передать отчёт координатору; C/B исправляют и перепроверяют FAQ quality, A отвечает только на конкретные frontend дефекты.

---

# Отчёт агента A — E2-A-01

- Статус: review; живой браузерный E2 прогон в CI успешен, окончательная приёмка этапа остаётся у координатора.
- Ветка `agent-a/e2`; `BASE_SHA` `dae14d9a838154b72e4cf122881b190032ae0a74`; `TASK_COMMIT` `f613288e5b0a9bc733e6653ba9706bea7e3313d9`; контракт engine/HTTP 1.0.
- Pushed код: mock UI `3033a2a9bbcb6444a04ac8929c953bb45d1c24fe`, server-owned formula и fixture bytes `b1a68b39861b7e6f5b1588f3c0453b079cd59c51`, live script и server-owned поля `b0646ed8216a42942d4b010a4c446d9ec362ef9f`, совместимость CI proxy env `a727351a70081cb8170c22f1b8eb06a54cbb8db0`.
- E0/E1 приняты координатором до этого этапа; последний E1 A report SHA `3895c6e8aae097b52120dd51ad897a1ff81928cf`.

## Результат

- `/processing?job=` опрашивает состояние задания до завершения; после успеха открывает `/review?id=`. Review загружает ReceiptView по ID, показывает защищённый preview страницы, доступ к исходнику, evidence/issues, маркировку partial/manual/synthetic и редактируемые поля/строки BillData. `template_id`, `template_version`, `calculation_kind`, `formula_kind` показаны только для чтения, поскольку их определяет B.
- `PUT /receipts/{id}/draft` использует `expected_revision`; при 409 загружает актуальную ревизию без потери несохранённой формы. Для подтверждения требуется сохранить правки, пройти локальную проверку обязательных полей и принять серверные warnings; `POST /confirm` получает UUID Idempotency-Key. `/explanation?id=` заново получает текущую подтверждённую ревизию и показывает серверные суммы, строки, разницы, ограничения и источники без клиентской денежной арифметики.
- MSW имитирует E2 только в `dev:mock`, включая 409 и частичное извлечение. Browser mock загружает bytes checked-in синтетического `fixtures/receipts/demo-bill-2026-08.png`; preview copy `apps/web/public/synthetic-receipt.png` имеет SHA256 `5d1c0904398857a9941afed423bdd6b0c6667873a06ac6d7ce2ec26eb50bcc53`. Реальный browser script `apps/web/scripts/e2-real-flow.mjs` берёт синтетический PDF из Git и внешний dev код из env.

## Проверки A

Среда: Windows PowerShell, Node 22.23.3 (`C:\Users\Stepan\AppData\Local\Temp\codex-node-v22.23.3\node-v22.23.3-win-x64`), Chrome headless. Из `apps/web` подготовка: `$nodeDir=Join-Path $env:TEMP 'codex-node-v22.23.3\node-v22.23.3-win-x64'; $env:PATH=$nodeDir+';'+$env:PATH`.

| Проверка | Фактический результат |
|---|---|
| `npm ci` после остановки Vite | 133 пакета из lock, успех. Первая попытка при работающем Vite получила Windows EPERM на нативной библиотеке; повтор после остановки успешен. |
| `npm test` | 7/7: E0/E1 контрактные случаи, E2 mock HTTP flow, сохранённые поля и серверные признаки, null issuer и обязательная сумма перерасчёта. |
| `npm run build`; `node --check scripts/e2-real-flow.mjs` | Успешно; production `dist` содержит HTML/CSS/JS, поиск `mockServiceWorker|synthetic-receipt|mock-session|mock-only|msw|devAuth|auth/demo` совпадений не дал. |
| `CHROME_PATH=<локальный Chrome>; npm run dev:mock -- --port 5173; npm run test:browser:e2` | Chrome 360×800: upload → polling → preview → 409 с сохранением правок → edit → confirm → explanation → 401 и повторный вход на том же `/review?id=`. `innerWidth=360`, `scrollWidth=360`. Снимки review/explanation осмотрены локально. |
| [GitHub Actions E2 Compose/browser CI #11](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36324627223), integration SHA `d38ae6307b6e0fcf1ea50ef05c84a337d72345a9` | **Success**, Linux runner: Vite `dev:real` на 5173 → Compose web на 18081 → API/worker/PG17 с `ENGINE_MODE=real`; `BASE_URL=http://127.0.0.1:5173/team/zhkh/`, `CHROME_PATH` и локальный `DEMO_ACCESS_CODE` заданы в CI env. Выполнен `npm run test:browser:e2:real`: синтетический PDF bytes → OCR job → preview → UI edit → confirm → explanation → reload и повторный вход; 360 px без горизонтального переполнения. Этот уровень — настоящий dev HTTP/worker/OCR в CI, не VM/MAX и не реальная квитанция. |

## Зависимости, ограничения, следующий шаг

- Локальная браузерная проверка A — MSW и синтетический PNG; живой E2 путь выполнен отдельно в CI на синтетическом PDF. На Windows нет локального Compose daemon. Сквозное чтение **того же UI receipt** после перезапуска API/worker координатор проверяет дополнительно; успешный browser reload без restart этого не доказывает.
- Read-only сверка B выявила серверные warning codes, которые не все попадали в прежний ReceiptView, и запрет edit confirmed. B передал исправления в E2 интеграцию; A не ограничивал кнопку временно. Живой browser CI проверил базовый edit/confirm path, но не все warning/confirmed-edit варианты.
- MAX Web/mobile, VM и реальные квитанции не проверялись. Все browser файлы синтетические. История, сравнение, FAQ, черновики и удаление относятся к E3; голос и отправка обращений исключены.
- Локальный `apps/web/public/mockServiceWorker.js` имеет CRLF-only статус после `npm ci`, `git diff --numstat` пуст; в commits не включён. Старые E0/E1 checkout не сбрасывались и не удалялись.
- Следующий шаг координатора: повторно прочитать UI receipt после API/worker restart и принять E2 по всем критериям. A ждёт конкретные дефекты CI, если появятся; E3 самостоятельно не начинался.
