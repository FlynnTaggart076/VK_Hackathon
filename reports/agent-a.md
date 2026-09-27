# Отчёт агента A — E0-A-01

- Статус: review, ожидает приёмки координатора.
- Ветка: `agent-a/e0`; база задания: `522757f58ad61951c7d66c4e97f2d5e65a433624`; task commit: `b5f0d55d96761fdb4fe495f719ad6eaa2a0fee94`.
- Независимый shell code SHA: `d393a92dda1fc35538c0bcd57cb16474eae3f379`.
- Принятый контракт B/C: `origin/integration/e0` SHA `d0170da1cb97d5e7a128b70b79fd4e445f352702`; обычный merge в ветку A: `f6938081058bef017ccfc4ba0bb0133eea750b00`.
- Итоговый E0 code SHA: `66b155d84291a3f6543f0806c00864bfeecf7397`, pushed в `origin/agent-a/e0`.
- Контрактная версия: 1.0.

## Результат

- `apps/web`: React/TypeScript/Vite shell с `BrowserRouter` под `/team/zhkh/`, карта всех экранов §11.1, доступные подписи и фокус, минимальный работающий экран вопроса.
- `src/api/openapi.generated.ts`: сгенерировано из принятого OpenAPI B. `src/api/types.ts` использует generated DTO. `Meta.engine_version` и `knowledge_version` исправлены на nullable согласно контракту; `AnswerContext.role` также nullable.
- Типизированный fetch работает с `/team/zhkh/api/v1`, bearer хранится только в памяти, запросы принимают `AbortSignal`, HTTP ошибки читаются через общий envelope. Денежной арифметики в JS нет.
- MSW включается только через `dev:mock`/`.env.mock`; есть meta, учебный demo auth, answer, partial receipt, 401/409, unsupported. Meta имеет все обязательные поля OpenAPI. Синтетические ответы помечены. Production сборка не копирует worker и не содержит активный mock.
- Карта экранов, команды и точное описание нюанса генератора `$defs` — в `docs/frontend.md`.

## Проверки

Среда Windows PowerShell. Системного Node в PATH не было; использован официальный переносимый архив Node 22.23.3 в `C:\Users\Stepan\AppData\Local\Temp\codex-node-v22.23.3\node-v22.23.3-win-x64`. Подготовка PATH в сессии PowerShell: `$nodeDir=Join-Path $env:TEMP 'codex-node-v22.23.3\node-v22.23.3-win-x64'; $env:PATH=$nodeDir+';'+$env:PATH`. Из `apps/web` выполнены:

| Команда | Фактический результат |
|---|---|
| `& (Join-Path $nodeDir 'npm.cmd') ci` | Успешно, 132 пакета из lock, аудит без найденных уязвимостей. |
| `& (Join-Path $nodeDir 'npm.cmd') run generate:types` | Успешно, OpenAPI → `src/api/openapi.generated.ts`; после повторной генерации Git status чистый. |
| `& (Join-Path $nodeDir 'npm.cmd') test` | Vitest: 1 файл, 3 теста прошли. Проверены 401/error envelope, unsupported, partial/409, canonical `receipt-confirmed.json` по JSON Schema C и отсутствие `$defs` в BillData instance. |
| `& (Join-Path $nodeDir 'npm.cmd') run build` | TypeScript + Vite production build успешен. |
| `rg --files apps/web/dist` и `rg -l 'mockServiceWorker\|mock-session\|mock-only\|msw' apps/web/dist` из корня | В dist только `index.html`, CSS и JS; поиск mock-маркеров совпадений не дал. |

Браузерный smoke выполнен на локальном `npm run dev:mock -- --port 5173` с Chrome через временный `playwright-core` вне Git. Команда запуска проверки: `& (Join-Path $nodeDir 'node.exe') (Join-Path $env:TEMP 'vk-zhkh-playwright-check\flow.cjs')`; временный скрипт открывал `http://127.0.0.1:5173/team/zhkh/` в viewport `360×800`, нажимал «Войти в учебный mock», переходил на «Помощник», задавал «неизвестный вопрос» и ждал заголовок «Пока нет проверенного ответа». Факт: pathname `/team/zhkh/assistant`, ответ `unsupported`, синтетическая пометка. Отдельный снимок 360 px осмотрен; горизонтальной прокрутки основного содержимого не видно. Это локальный mock Chrome, не MAX Web/mobile и не VM.

## Зависимости, ограничения, следующий шаг

- OpenAPI/fixtures B/C приняты координатором и потреблены; контрактной несовместимости DTO не выявлено. Генератор добавляет `$defs` JSON Schema как поле экземпляра BillData; локальный `Omit<'$defs'>` убирает только это служебное поле и сохраняет типы вложенных `services`, `adjustments`, `settlement`. Canonical JSON валидирован тестом.
- E0 shell не реализует полный пользовательский путь: MAX Bridge, onboarding, upload/polling, проверка/подтверждение, сравнение, черновик, история и реальный API относятся к следующим заданиям.
- Следующий шаг после приёмки координатором — отдельное задание E1. Самостоятельно E1 не начинался.
