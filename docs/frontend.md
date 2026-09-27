# Frontend: E0

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

Навигация E0: главная → вопрос или загрузка; верхняя навигация ведёт на главную, вопрос, загрузку и историю. Остальные пути открываются напрямую и пока показывают явную заглушку E0. Полные переходы и состояния выполняются по этапам E1–E3.

## Запуск и границы E0

Node 22.23.3 использовался при проверке. Из `apps/web`:

```sh
npm ci
npm run generate:types
npm run dev:mock
npm test
npm run build
```

`dev:mock` включает MSW только при `import.meta.env.DEV` и `VITE_ENABLE_MOCK=true` из `.env.mock`. Обычный `npm run dev` не включает mock. Production build не копирует worker в `dist` и не загружает mock-модуль. Demo access code в mock фиксированная учебная строка, не секрет. Реальный вход MAX и API B ещё не подключены.

Типы `src/api/openapi.generated.ts` созданы из принятого `contracts/http/openapi.yaml` checkpoint `d0170da1cb97d5e7a128b70b79fd4e445f352702`. `src/api/types.ts` даёт короткие aliases на generated DTO. `openapi-typescript@7.13.0` требует TypeScript 5.x, поэтому закреплён TypeScript 5.9.3. При генерации из внешнего `contracts/engine/v1/BillData.schema.json` инструмент ошибочно добавляет служебный JSON Schema ключ `$defs` как обязательное поле экземпляра `components['schemas']['BillData.schema']`. Alias `Omit<..., '$defs'>` убирает только этот служебный ключ; вложенные `services`, `adjustments`, `settlement` остаются сгенерированными типами. Тест проверяет реальный `contracts/http/examples/receipt-confirmed.json` по JSON Schema C, отсутствие `$defs` и тип вложенного `service_code`.

Токен сессии хранится только в памяти модуля `src/api/client.ts`. Запросы поддерживают `AbortSignal`; ошибки нормализуются из общего envelope. Искусственные тарифы из §7.7 только в MSW, клиент не вычисляет суммы.

Сейчас `GET /meta`, учебный `POST /auth/demo`, `POST /assistant/answers` и `GET /receipts/:id` имеют mock-ответы. Mock meta содержит все обязательные поля принятого OpenAPI; 401/409, partial/unsupported сверены с его кодами и состояниями. `partial` остаётся синтетическим вариантом §7.7, потому что HTTP-пример B для неизвестного макета имеет `manual_required`. Другие экраны представлены маршрутизируемым shell без заявлений о готовом пользовательском сценарии.
