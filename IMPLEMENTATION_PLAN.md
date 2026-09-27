# План реализации MVP ЖКХ в MAX

Обновлено: 2026-09-27. Владелец: координатор. Источник требований: `TECHNICAL_SPEC.md` v1.1, 2026-09-27. Контракты: engine/HTTP v1.0 приняты для E0.

## Состояние

- Текущий этап: **E1 — каркасы**, задания выданы A/B/C из `4449864e24686472130b2569be04b349ed862834`; отдельные checkout/ветки созданы от принятой базы `feb1fc7ab12201e6d5a93989d64a8374fe44a139`.
- Последний принятый кодовый SHA: `3908481355f670d16b02cca530058213091af614` (`integration/e0`; отчёты/план добавляются отдельными doc-only commits).
- Проверенный промежуточный E1 checkpoint B: `1d99a19502df2b536248daad224b0f0af5e96d5a`, перенесён в `integration/e1` как `28192753c516d3b3738ea4ac36e8af84475b309a`. Принят только dev API для подключения A; PostgreSQL, worker и OCR этим SHA не подтверждены.
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
| E1-A-01 | A / `agent-a/e1` | in_progress | `tasks/e1/agent-a.md` | Onboarding, навигация, состояния, dev API после B checkpoint |
| E1-B-01 | B / `agent-b/e1` | in_progress; dev checkpoint accepted | `tasks/e1/agent-b.md` | `1d99a19` → `2819275`: API/auth/upload в MemoryStore, 4 теста; DB/worker/Compose ещё в работе |
| E1-C-01 | C / `agent-c/e1` | accepted | `tasks/e1/agent-c.md` | code `e58a28a` + `d1d6426`, docs `ed649aa`, report `bcac7f2`; verifier/17 тестов, реальный OCR синтетических PNG и PDF-скана |

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
- На координаторском Windows нет Docker daemon/WSL-дистрибутива. Отдельный PostgreSQL 16 test cluster B и автономный Docker Compose CLI доступны только для проверок БД и `config`; контейнерный build/up не подтверждён. Локальный Tesseract 5.5.3 `eng+rus` в `%TEMP%` фактически распознал синтетические PNG и PDF-скан C, но реальные квитанции и контейнерный OCR не проверены.
- У B независимый повтор persisted PostgreSQL тестов обнаружил зависимость от старых jobs и часового лимита; исправление с изоляцией test schema в работе, поэтому полный E1-B ещё review. A начал E1 правки в старом `agent-a/e0` checkout; сохранённые изменения переносятся в `agent-a/e1` без сброса исходных файлов.

## Следующий шаг

Получить pushed E1 checkpoints и отчёты. Сначала проверить C engine, затем B runtime/adapter и A реальный dev API; независимый UI и backend каркас принимать отдельно. Принять E1 только после PostgreSQL/Compose и связанных контрактов, затем выдать E2.
