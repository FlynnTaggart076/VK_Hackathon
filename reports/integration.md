# Отчёт координатора об интеграции

Обновлено: 2026-09-27. Текущий этап: E1 после принятого E0. Статус E0: accepted.

## Принятые SHA

| Область | SHA | Основание |
|---|---|---|
| База | `522757f58ad61951c7d66c4e97f2d5e65a433624` | Bootstrap; задания: `b5f0d55d96761fdb4fe495f719ad6eaa2a0fee94` |
| C | code `8114fd6de0d7112f529012967aaadb6fadedbf92`, report `09a20b1ea6b271138351775b5c38a7d5465e718b` | Engine DTO/fixtures/knowledge schemas accepted |
| B | code `910e141ee170bf8eb740d4a63f0b38d9f6c41212`, report `4b467d549faf3b5c94c9b1a5247a3f78da268c0a` | HTTP OpenAPI/examples accepted |
| A | code `66b155d84291a3f6543f0806c00864bfeecf7397`, report `4674d4e1eab607141f5e290e7cb28135c296c15e` | UI shell/generated types/mock accepted |
| Проверенный integration candidate | `3908481355f670d16b02cca530058213091af614` | Код после C→B→A, перед doc-only отчётом `effbccc923acb36a7ee3bb91c10bfb43348883d3` |
| E1 dev API checkpoint B | code `1d99a19502df2b536248daad224b0f0af5e96d5a`, integration `28192753c516d3b3738ea4ac36e8af84475b309a` | Только dev endpoints для A; полный E1 не принят |
| E1 C | code `e58a28aedddad3a8433368f19f3db45c299cd0da`, Decimal fix `d1d6426502a5ddbc0591302903b0e311036fc3d3`, docs `ed649aa3c3d4f2850f67ff3b84b5161351c72a3d`, report `bcac7f2430e04201475a94a4c4730380c126b10e` | Принят в `integration/e1` `4f653165ed97bea21572231a9f623607f16e89c5` |
| Release/VM | нет | Развёртывание не выполнялось |

## Проверки и решение

- В пустом remote опубликованы bootstrap и задания, все SHA кодеров проверены через `ls-remote`. Diff каждого кодера ограничен его путями §13; `git diff --check` на кандидате завершился с кодом 0.
- На integration candidate `3908481`: `python packages/housing_engine/verify_contract.py` → схемы/синтетические 200→270 и knowledge structure OK; `python -m unittest discover -s packages/housing_engine/tests -v` → 1 test OK, негативный fixture требует ненулевого exit.
- `python scripts/check_http_contract.py` → OpenAPI 3.1, 28 операций, 24 JSON-примера, ссылки на вложенные engine DTO; exit 0.
- В `apps/web`: `npm ci`, `npm run generate:types` (без content diff), `npm test` → 3/3, `npm run build` → success; поиск `mockServiceWorker|mock-session|mock-only|msw` в production `dist` совпадений не дал. Координатор повторил эти проверки на объединённом checkout, Node 22.23.3 из временного каталога.
- A отдельно проверил локальный Chrome mock flow при 360×800: вход, вопрос, unsupported и синтетическая метка. Это не реальный MAX, VM, backend или OCR.
- B проверил существующий внешний `/team/`: HTTP 200/TLS verify 0; SSH VM дошёл до auth и получил `Permission denied (publickey)`. Приложение `/team/zhkh/` не публиковалось. MAX credentials и реальный клиент не проверены.
- E0 принят как контрактный этап. Семь engine-функций пока `NotImplementedError`, HTTP пока спецификация, UI остальные экраны заглушки; E1–E5 не приняты.
- На `integration/e1` координатор повторил `python -m pytest apps/backend/tests -q` с locked зависимостями из изолированного каталога: 4 passed, одно стороннее deprecation warning. Реально работают meta, demo auth, me/profile, catalog, upload, receipt и queued job; `MemoryStore` не сохраняется после рестарта, `receipt_ocr=false`, `engine_stub=true`, readiness 503. При `DATABASE_URL` этот checkpoint отказывается стартовать вместо молчаливого перехода на память.
- E1 C: на `integration/e1` `verify_contract.py` OK, 17 unittest OK, `pip check` OK. Tesseract `v5.5.3.20260724` с `eng/rus` из отдельного `%TEMP%` каталога фактически дал `recognized`, период `2026-08`, объём `5.000000`, тариф `40.000000`, итог `200.00` на синтетических PNG и PDF без текстового слоя. Для PNG: 25 evidence, 18 `needs_review`, issue `OCR_REVIEW_REQUIRED`. Реальные квитанции и контейнерный runtime этим не проверялись.
- B code `aafa3348450af3a005e9a30b92411779cac8e9dc` прошёл PostgreSQL 16/Alembic в первом прогоне, HTTP contract 28 операций/24 примера и `Compose v5.5.1 config -q` local/VM. Независимый повтор на непустой test DB обнаружил две зависимости теста от старого состояния: worker брал старую job, затем upload упирался в `RATE_LIMITED`. B исправляет тест изоляцией schema; код B пока не принят в интеграцию.

## Текущие задачи и блокеры

Текущие задачи: `E1-A-01`, `E1-B-01` в работе; `E1-C-01` принят. A переносит сохранённые E1 изменения из старого `agent-a/e0` checkout в `agent-a/e1`; B устраняет неповторяемость PG теста. Общий E1 ещё не принят. PostgreSQL 16 и синтетический OCR локально проверены, Compose `config` проверен без daemon; VM SSH отвергает ключ (`Permission denied (publickey)`), MAX credentials не доступны. Владелец доступа запрошен без передачи секретов в Git.

## Следующий шаг

Получить E1 pushed SHA и отчёты, проверить C→B→A, выполнить локальный Compose/PostgreSQL при наличии среды; реальный OCR/VM/MAX подтверждать отдельно от mock/stub.
