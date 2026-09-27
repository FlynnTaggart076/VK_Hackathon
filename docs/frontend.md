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
npm run dev:mock
npm test
npm run build
```

`dev:mock` включает MSW только при `import.meta.env.DEV` и `VITE_ENABLE_MOCK=true` из `.env.mock`. Обычный `npm run dev` не включает mock. Production build не копирует worker в `dist` и не загружает mock-модуль. Demo access code в mock фиксированная учебная строка, не секрет. Реальный вход MAX и API B ещё не подключены.

Пока используется ручная запись типов из ТЗ §§6–7 в `src/api/types.ts`; после принятия OpenAPI B нужно сверить типы и примеры. Токен сессии хранится только в памяти модуля `src/api/client.ts`. Запросы поддерживают `AbortSignal`; ошибки нормализуются из общего envelope. Искусственные тарифы из §7.7 только в MSW, клиент не вычисляет суммы.

Сейчас `GET /meta`, учебный `POST /auth/demo`, `POST /assistant/answers` и `GET /receipts/:id` имеют mock-ответы. Примеры 401, 409, partial и unsupported проверяются тестами. Другие экраны представлены маршрутизируемым shell без заявлений о готовом пользовательском сценарии.
