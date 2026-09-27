# Отчёт агента A — E1-A-01

- Статус: review; приёмка координатора ожидается.
- Ветка: `agent-a/e1`; `BASE_SHA` `feb1fc7ab12201e6d5a93989d64a8374fe44a139`; `TASK_COMMIT` `4449864e24686472130b2569be04b349ed862834`; контракт engine/HTTP 1.0.
- Принятый B dev API checkpoint `28192753c516d3b3738ea4ac36e8af84475b309a`, merge в ветку A `76f556d3efbd469d39d5b80d1a13565eb1db5b25`.
- E1 код A: `1a9e30c5d2c320f36d40a38619db26f2dd289259` (API/onboarding), `503cee0340d0985f20c21555981bfc046d7f3592` (wiring, координатор помог после прерывания работы агента), `0ca5aa7b26c2f8c3c7a07b8e4b555ab08e4f2e15` (UX исправления). Документация: `063d8768c114e48c21c41b615ce0d4d197e14f01`. Все pushed в `origin/agent-a/e1`.

## Результат

- `apps/web`: первый запуск берёт `GET /meta`, `GET /catalog`, `GET /me`, сохраняет `PUT /me/profile` с ролью, территорией и явным принятием текущего уведомления. Upload показывается только после актуального серверного профиля; B всё равно повторно проверяет privacy notice.
- Учебный MSW и реальный dev API используют одинаковые экраны. `npm run dev:real` проксирует `/team/zhkh/api/**` на локальный B `/api/**`; локальный demo code вводится в форме, не включён в исходники/production bundle. Session token остаётся в памяти; 401 открывает вход на том же пути, включая query с job ID.
- `POST /receipts` отправляет файл и UUID Idempotency-Key; экран обработки читает `GET /jobs/{id}`. Ошибки 401/409/413/422/offline имеют текстовые состояния. Dev stub явно сообщает, что OCR не выполнен и потребуется ручной ввод; `succeeded` не назван распознанной квитанцией.
- Другие экраны остаются помеченными заглушками. Реальный dev B пока не реализует ответы FAQ, и UI это указывает; в MSW общий вопрос доступен до завершения профиля.
- Команды запуска и ограничения описаны в `docs/frontend.md`.

## Проверки

Среда: Windows PowerShell; Node 22.23.3 из `C:\Users\Stepan\AppData\Local\Temp\codex-node-v22.23.3\node-v22.23.3-win-x64`. В `apps/web`: `$nodeDir=Join-Path $env:TEMP 'codex-node-v22.23.3\node-v22.23.3-win-x64'; $env:PATH=$nodeDir+';'+$env:PATH`.

| Проверка | Результат |
|---|---|
| `& (Join-Path $nodeDir 'npm.cmd') ci` | Прошло из lock-файла; 132 пакета. |
| `& (Join-Path $nodeDir 'npm.cmd') test` | Vitest: 5/5. Проверены consent gate, 422 старой версии, queued job, 401 истёкшей сессии, прежние E0 contract cases. |
| `& (Join-Path $nodeDir 'npm.cmd') run build` | TypeScript + Vite production build успешно. |
| `rg --files dist` и `rg -l 'mockServiceWorker\|mock-session\|mock-only\|msw\|devAuth\|auth/demo' dist` | В dist только HTML/CSS/JS; mock/dev auth маркеры не найдены. |

Локальный Chrome/Playwright-core (временный пакет вне Git), viewport `360×800`:

1. `npm run dev:mock -- --port 5173`, затем `& (Join-Path $nodeDir 'node.exe') (Join-Path $env:TEMP 'vk-zhkh-playwright-check\e1-mock-flow.cjs')`: сохранён onboarding, mock upload перешёл в queued, после подстановки истёкшего тестового токена 401 показал форму входа на том же `/team/zhkh/processing?job=40000000-0000-4000-8000-000000000001`; `innerWidth=360`, `scrollWidth=360`. Скриншот осмотрен локально.
2. Из отдельного принятого checkout `integration/e1` SHA `0b0daaf994315c63de8f0db7d458de6411a31d81` запущен реальный B API в dev MemoryStore командой `python -m uvicorn app.main:app --app-dir apps/backend --host 127.0.0.1 --port 8000` с локальными `APP_MODE=dev`, `ENGINE_MODE=stub`, `DEMO_AUTH_ENABLED=true`, `DEMO_ACCESS_CODE=<локально выбранный код>`, `STORAGE_PATH=<каталог в TEMP>`. Затем `npm run dev:real -- --port 5174` и `& (Join-Path $nodeDir 'node.exe') (Join-Path $env:TEMP 'vk-zhkh-playwright-check\e1-real-flow.cjs')`: meta/auth/profile/upload/job реально вызваны через Vite proxy. Загружен только синтетический PNG 2×2 px из TEMP. Ответ: `mode=dev`, `receipt_ocr=false`, `engine_stub=true`, `job.state=queued`, service worker отсутствует; `innerWidth=360`, `scrollWidth=360`. Скриншот осмотрен локально.

## Границы и следующий шаг

- Живой браузерный B flow использовал dev MemoryStore без PostgreSQL и worker; queued не является результатом OCR и не доказывает сохранность после перезапуска. Координатор отдельно проверяет Compose/PG17 и worker на integration SHA.
- MAX Bridge, реальный MAX Web/mobile, VM, OCR bytes→review, подтверждение и объяснение не проверялись в E1-A. Реальные обращения не отправляются; голос отсутствует.
- `public/mockServiceWorker.js` и `src/api/openapi.generated.ts` в локальном checkout имеют CRLF-only статус после `npm ci`; `git diff --numstat` пуст, в commits они не включены. Старый checkout `agent-a/e0` с его незакоммиченными E1 копиями оставлен без сброса/удаления.
- После приёмки координатором ожидается отдельное задание E2; самостоятельно E2 не начинался.
