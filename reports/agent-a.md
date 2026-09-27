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
