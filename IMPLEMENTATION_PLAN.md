# План реализации MVP ЖКХ в MAX

Обновлено: 2026-09-27. Владелец: координатор. Источник требований: `TECHNICAL_SPEC.md` v1.1, 2026-09-27. Контракты: engine/HTTP v1.0 приняты для E0.

## Состояние

- Текущий этап: **E1 — каркасы**, задания готовятся после приёмки E0.
- Последний принятый кодовый SHA: `3908481355f670d16b02cca530058213091af614` (`integration/e0`; отчёты/план добавляются отдельными doc-only commits).
- Release SHA: отсутствует; развёртывания нет.
- Git remote: `https://github.com/FlynnTaggart076/VK_Hackathon.git`; push `main` и веток A/B/C проверен.
- Локальные исходные файлы: `TECHNICAL_SPEC.md`; `Prompt.txt`, `Работа с сервером.md` и презентация остаются только локально. Последняя инструкция VM обязательна для B и координатора, но не публикуется целиком.
- E0 даёт контракты и локальный shell, но OCR, backend runtime, полный UI, VM и MAX ещё не реализованы. Это не готовый MVP.

## Этапы и переходы

| Этап | Содержание | Условие перехода |
|---|---|---|
| E0 | DTO/fixtures C, полный P0 OpenAPI B, API-клиент и mock A | Схемы и примеры валидны; вложенные DTO совпадают; A потребляет контракт |
| E1 | Самостоятельные каркасы UI, API/БД/worker, engine | Три части запускаются; A вызывает реальные meta/auth/upload B в dev |
| E2 | Одна квитанция насквозь | Bytes → OCR → правка → подтверждение → объяснение; состояние сохраняется после перезапуска |
| E3 | Сравнение, FAQ, черновик, история, бот | Сценарий §17.4; delta 70; unknown; нет отправки; без mocks/stubs |
| E4 | Принятый SHA в VM и MAX | URL, API, webhook и MAX Web/mobile проверены; соседние маршруты сохранены |
| E5 | Стабилизация и сдача | Все P0/AT, backup/restore, пользовательская проверка и материалы сдачи по release SHA |

## Текущие задачи

| ID | Владелец / ветка | Статус | Задание | Приёмка |
|---|---|---|---|---|
| E0-C-01 | C / `agent-c/e0` | accepted | `tasks/e0/agent-c.md` | `8114fd6` code, `09a20b1` report; schemas/fixtures/knowledge checks прошли |
| E0-B-01 | B / `agent-b/e0` | accepted | `tasks/e0/agent-b.md` | `910e141` code, `4b467d5` report; 28 операций/24 примера прошли |
| E0-A-01 | A / `agent-a/e0` | accepted | `tasks/e0/agent-a.md` | `66b155d` code, `4674d4e` report; 3 теста/build прошли |
| E1-A-01 | A / `agent-a/e1` | todo | `tasks/e1/agent-a.md` после task commit | Onboarding, навигация, состояния, dev API |
| E1-B-01 | B / `agent-b/e1` | todo | `tasks/e1/agent-b.md` после task commit | API/auth/DB/upload/worker skeleton/Compose |
| E1-C-01 | C / `agent-c/e1` | todo | `tasks/e1/agent-c.md` после task commit | Пакет, математика/валидация, PDF-text и OCR первого макета |

## Принятая интеграция E0

1. C перенесён в `integration/e0`: DTO/fixtures `0e0f29b`, knowledge/lock `89df7e3`, отчёт `edb784f`.
2. B получил C и перенесён: HTTP contract `d0170da`, отчёт `9f6ed95`.
3. A получил OpenAPI, сгенерировал типы и перенесён: shell `0bef18d`, контрактная сверка `3908481`, отчёт `effbccc`.
4. Общие проверки и ограничения записаны в `reports/integration.md`. E0 принят; E1 выдаётся отдельным task commit.

## Блокеры и зависимости

- VM: SSH дошёл до проверки ключа, затем `Permission denied (publickey)`; операторский вход и deploy блокированы, владелец доступа нужен до E4.
- MAX: bot/mini-app credentials не доступны B в текущем окружении; реальный MAX не проверен, владелец доступа нужен до E4.
- Выбор реальной пилотной территории и права на реальные обезличенные квитанции ещё не подтверждены. Для E0 используются явно синтетические данные.
- `openapi-typescript` трактует `$defs` C как поле экземпляра BillData; A использует узкий `Omit<'$defs'>` и тест канонического fixture. При обновлении схем повторять generate/test.
- E1 запускается локально с явными dev mock/stub; VM/MAX и реальные документы не подменяются этими проверками.

## Следующий шаг

Опубликовать финальный E0 commit в `main`, записать точный `BASE_SHA` в E1 задания, создать отдельные checkout/ветки A/B/C и продолжить цикл приёмки E1 по §14.
