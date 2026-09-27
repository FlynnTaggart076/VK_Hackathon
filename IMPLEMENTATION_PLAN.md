# План реализации MVP ЖКХ в MAX

Обновлено: 2026-09-27. Владелец: координатор. Источник требований: `TECHNICAL_SPEC.md` v1.1, 2026-09-27. Контракты: engine/HTTP v1.0 приняты для E0.

## Состояние

- Текущий этап: **E2 — одна платёжка насквозь**, задания A/B/C выданы из task commit `f613288e5b0a9bc733e6653ba9706bea7e3313d9`; отдельные checkout/ветки `agent-{a,b,c}/e2` и `integration/e2` созданы от принятой базы `dae14d9a838154b72e4cf122881b190032ae0a74`.
- Принятый E1 runtime merge SHA: `7afd978166b514088f1f130a426a2ca655aeba93`; E2 BASE_SHA: `dae14d9a838154b72e4cf122881b190032ae0a74` (doc-only запись приёмки). Проверенный E1 runtime candidate: `c56a793d71b5b10e1ff42ad38d2783635ad007d9` (`integration/e1`).
- Промежуточный E1 checkpoint B: `1d99a19502df2b536248daad224b0f0af5e96d5a`, перенесён как `28192753c516d3b3738ea4ac36e8af84475b309a`; он дал A dev API, но E1 принят по более позднему интеграционному SHA.
- E2 ранние checkpoint: C `7242082cb940c8b05c0435b4802d2220710fa8e7` → `integration/e2` `57f8baef06b4adb41aa4b73aa8ca8da32c8c7755` (bytes PDF→explain, verifier/19 tests); B `f508d9add75da0b791720f1a5e0f08f403243001` → `integration/e2` `0ebed8b7685772de5ea67866ca62c9efc3049a64` (owner source/list/delete и revision CAS, backend 9 passed/1 PG skipped). Оба checkpoint приняты только как зависимости, весь E2 ещё in_progress.
- Полный E2-C принят: code `6b251b0e1770a2ca19c169943da38099c7076b7f`, report `056ea2e576d2fbf7be4dfae5733fc158eced4e17`, integration code `2d94e9283ad30b251034426eb399c3102452f74f`; verifier/25 tests/21 manifest hashes и реальный Tesseract smoke на синтетических растровых документах. E2 B real-flow checkpoint `5694604ee498d3dc71cb4aca400c6fb4355a993d` интегрирован как `8d1a2a4`; [Compose CI #2](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36321907368) поднял PG17/real engine/web/worker. A mock UI checkpoint `3033a2a9bbcb6444a04ac8929c953bb45d1c24fe` интегрирован как `c14bc7a`; 6 тестов/build и Chrome 360 px mock, исправление read-only формулы и live flow в работе. Общий E2 не принят.
- Release SHA: отсутствует; развёртывания нет.
- Git remote: `https://github.com/FlynnTaggart076/VK_Hackathon.git`; push `main` и веток A/B/C проверен.
- Локальные исходные файлы: `TECHNICAL_SPEC.md`; `Prompt.txt`, `Работа с сервером.md` и презентация остаются только локально. Последняя инструкция VM обязательна для B и координатора, но не публикуется целиком.
- E1 даёт dev UI, PostgreSQL/Compose и engine на синтетических документах. Сквозной OCR→правка→подтверждение→объяснение, VM и MAX ещё не приняты. Это не готовый MVP.

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
| E1-A-01 | A / `agent-a/e1` | accepted | `tasks/e1/agent-a.md` | `1a9e30c`, `503cee0`, `0ca5aa7` code; `3895c6e` report; 5 тестов/build, mock и B dev API в Chrome 360 px |
| E1-B-01 | B / `agent-b/e1` | accepted | `tasks/e1/agent-b.md` | `aafa334`, `d1798cc`, `599c9f6`, `5f1e0b3` code; `e9de94d` report; PG тесты и Compose CI PG17 зелёные |
| E1-C-01 | C / `agent-c/e1` | accepted | `tasks/e1/agent-c.md` | code `e58a28a` + `d1d6426`, docs `ed649aa`, report `bcac7f2`; verifier/17 тестов, реальный OCR синтетических PNG и PDF-скана |
| E2-A-01 | A / `agent-a/e2` | in_progress; mock checkpoint accepted | `tasks/e2/agent-a.md` | `3033a2a` → `c14bc7a`: 6 tests/build, 360 px mock; read-only формула и живой E2 API ещё в работе |
| E2-B-01 | B / `agent-b/e2` | in_progress; runtime checkpoint review | `tasks/e2/agent-b.md` | `f508d9a` → `0ebed8b`; real adapter `5694604` → `8d1a2a4`; PG17 Compose up, полный HTTP/restart smoke и negative cases ещё в работе |
| E2-C-01 | C / `agent-c/e2` | accepted | `tasks/e2/agent-c.md` | `7242082` + `6b251b0` code, `056ea2e` report; verifier/25 tests/21 hashes/7 synthetic OCR cases |

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
- На координаторском Windows нет Docker daemon/WSL. Docker build/up, PostgreSQL 17, worker, API, web/assets/deep link и `nginx -t` прошли на изолированном GitHub Actions Linux runner [E1 CI #7](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36319065489). Это не VM. Локальный Tesseract 5.5.3 `eng+rus` распознал синтетические PNG и PDF-скан C; реальные квитанции и контейнерный OCR не проверены.
- Старый `agent-a/e0` checkout хранит незакоммиченные E1 копии без сброса/удаления. В `agent-a/e1` и `integration/e1` остаются CRLF-only изменения generated/MSW файлов с пустым content diff; в commits не включались.

## Следующий шаг

Получить B финальные negative/retention тесты и HTTP smoke script; повторить полный bytes→OCR→edit→confirm→explain и restart на PG17 CI. Проверить A read-only формулу и живой браузерный E2 flow с тем же API; вернуть дефекты владельцам. E2 не принимать без полного сценария; VM/MAX остаются внешними проверками будущих этапов.
