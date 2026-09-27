# Отчёт координатора об интеграции

Обновлено: 2026-09-27. Текущий этап: E2 после принятого E1. Статус E0/E1: accepted. Ранние промежуточные проверки ниже сохранены как история; итоговое решение E1 находится в конце отчёта.

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

Итоговое решение E1 и следующие действия записаны ниже.

## Итоговая приёмка E1

- Принятый merge в `main`: `7afd978166b514088f1f130a426a2ca655aeba93`; проверенный runtime candidate `c56a793d71b5b10e1ff42ad38d2783635ad007d9` (`integration/e1`). После candidate добавлены только отчёты/документация. Release SHA для VM пока отсутствует.
- C: code `e58a28aedddad3a8433368f19f3db45c299cd0da`, Decimal fix `d1d6426502a5ddbc0591302903b0e311036fc3d3`, report `bcac7f2430e04201475a94a4c4730380c126b10e`.
- B: dev checkpoint `1d99a19502df2b536248daad224b0f0af5e96d5a`, PG/worker code `aafa3348450af3a005e9a30b92411779cac8e9dc` + `d1798ccd1f064fcd40581679a9b283e85ba0c339`, runtime fixes `599c9f68f20767d5b3edff24549f0f4b4ecef0ac` + `5f1e0b3aeb507775c39fee26992a995507255d62`, report `e9de94df0f9882f3a8f74b93bc886bbb0e15ddf0`.
- A: API/onboarding `1a9e30c5d2c320f36d40a38619db26f2dd289259`, coordinator wiring `503cee0340d0985f20c21555981bfc046d7f3592` (ограниченная помощь A), UX fix `0ca5aa7b26c2f8c3c7a07b8e4b555ab08e4f2e15`, report `3895c6e8aae097b52120dd51ad897a1ff81928cf`.
- Координатор на интеграционном checkout: frontend Vitest `5 passed`, TypeScript/Vite build success, production bundle без dev/mock маркеров; backend `8 passed, 1 skipped` без локально запущенного PostgreSQL; engine verifier OK и `17 unittest` OK; HTTP contract `28 operations / 24 examples` OK; `git diff --check` OK. B на изолированном PG16.2 после исправления schema isolation получил `9 passed`.
- [GitHub Actions E1 CI #7](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36319065489) на candidate `c56a793` завершился success: Compose build/up, PostgreSQL 17, API readiness/meta HTTP 200, worker running, `nginx -t`, web HTTP 200, JS asset HTTP 200, deep SPA link HTTP 200. `meta` сообщил `engine_stub=true`, `receipt_ocr=false`.
- A проверил Chrome 360×800: учебный mock onboarding→queued upload→401 relogin с сохранением job URL; в real dev Chrome через B MemoryStore — meta/auth/profile/upload/job queued, MSW отсутствует, горизонтального переполнения нет. Это реальный HTTP dev API, но без PostgreSQL/worker в браузерном прогоне. Отдельный CI и B-тесты покрыли контейнер/БД.
- E1 **accepted** по §14.3: три компонента независимо запущены, A вызвал реальные dev endpoints B; mock/stub явно помечены. Реальные пользовательские квитанции, сквозной OCR→правка→подтверждение→объяснение, VM и MAX не проверены. VM SSH по-прежнему `Permission denied (publickey)`; MAX credentials не получены. Старые локальные незакоммиченные файлы и CRLF-only артефакты сохранены, не включены в merge.

## Следующий шаг после E1

Опубликовать doc-only запись приёмки и задания E2. Начать независимые A/C части, B подключать к принятому контракту C. Не объявлять E2 принятым до bytes→OCR→UI review/edit→confirm→explain и повторного чтения после перезапуска. Подготовка VM/MAX продолжается только при действующем доступе и в границах инструкции владельца.

## Выдача E2

- Принятая база `dae14d9a838154b72e4cf122881b190032ae0a74`, task commit `f613288e5b0a9bc733e6653ba9706bea7e3313d9`. Заполнены `tasks/e2/agent-{a,b,c}.md`; созданы отдельные checkout `agent-{a,b,c}-e2` и `integration-e2` от базы, ветки `agent-{a,b,c}/e2` и `integration/e2`.
- A запущен на независимый mock review/edit/confirm/explain по принятому HTTP v1.0, живой B API подключается после checkpoint. B запущен на независимые PostgreSQL/CAS/revision/API части; adapter C только после принятого engine SHA. C запущен на OCR bytes и детерминированное объяснение с ранним публичным checkpoint для B.
- Текущие задачи: E2-A-01, E2-B-01, E2-C-01 `in_progress`; pushed E2 code/report SHA ещё нет, E2 не принят. Блокеры будущей VM/MAX проверки прежние: SSH `Permission denied (publickey)`, отсутствуют MAX credentials. Пользовательские документы/пилотная территория не предоставлены; синтетические fixtures явно помечены.
- Следующий шаг: получить C checkpoint, проверить его и передать B; затем B persisted adapter и A живой UI проверить общим Compose/restart smoke. Не создавать release SHA и не разворачивать VM до принятой версии и разрешённого доступа.

## Ранние принятые зависимости E2

- C pushed `7242082cb940c8b05c0435b4802d2220710fa8e7` → `integration/e2` `57f8baef06b4adb41aa4b73aa8ca8da32c8c7755`. Публичные `extract_receipt` из bytes двух синтетических PDF и `explain_receipt` дали август/сентябрь 200.00/270.00, `matched`, `sources=[]`, `ARITHMETIC_ONLY`. Координатор повторил `verify_contract.py` OK, 19 unittest OK, SHA-256 нового PDF совпал с manifest, `git diff --check` OK. C продолжает негативные OCR fixtures; C задача целиком не принята. Этот SHA передан B.
- B pushed `f508d9add75da0b791720f1a5e0f08f403243001` → `integration/e2` `0ebed8b7685772de5ea67866ca62c9efc3049a64`. Owner-scoped source/list/delete и revision CAS проверены на объединённом C+B checkout: `python -m pytest apps/backend/tests -q` → `9 passed, 1 skipped` (локальный PG не настроен), одно стороннее Starlette warning; `git diff --check` OK. HTTP edit/confirm/explain и OCR worker ещё не готовы; B продолжает adapter. A продолжает mock UI до принятого B HTTP checkpoint.
- `integration/e2` pushed; `main` остаётся на принятом E1. Текущие E2-A/B/C `in_progress`; E2 release SHA нет, VM/MAX не менялись. Следующая общая проверка: C негативные fixtures → B real worker/PG17/restart → A живой UI. Результаты локального mock и синтетического OCR не подменяют эту проверку.

## E2 после полных C fixtures и первых A/B runtime checkpoint

- C E2 принят: итоговый code `6b251b0e1770a2ca19c169943da38099c7076b7f`, report `056ea2e576d2fbf7be4dfae5733fc158eced4e17`, integration code `2d94e9283ad30b251034426eb399c3102452f74f`. Координатор на объединённом checkout повторил engine verifier OK, `25 unittest` OK, 21/21 manifest bytes+SHA256 OK и opt-in Tesseract 5.5.3 `eng+rus`: пять поддерживаемых PNG/JPEG recognized, неизвестная услуга partial, PDF-скан recognized; все OCR evidence `needs_review`. Счета реальной УК и телефонные фото не проверены.
- B real-flow checkpoint `5694604ee498d3dc71cb4aca400c6fb4355a993d` → `integration/e2` `8d1a2a4` даёт bytes→engine worker, source/preview, edit CAS, confirm/explain. На объединённом checkout `11 passed, 1 skipped` без локальной PG, HTTP contract verifier `28 operations/24 examples` OK. B сообщил три успешных последовательных прогона отдельного PG16 теста с Alembic, JSONB, конкурентным CAS и чтением после restart; общий PG17 HTTP flow ещё проверяется. [Compose CI #1](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36321592087) и [#2](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36321907368) подняли real-engine стек на PG17 и проверили readiness/meta, worker, Nginx, web/assets/deep link. Это не доказывает bytes→confirm→explain после restart; B пишет воспроизводимый HTTP smoke и negative/retention tests.
- A mock UI checkpoint `3033a2a9bbcb6444a04ac8929c953bb45d1c24fe` → `integration/e2` `c14bc7ac4dce590c66b3414bf2bccf2e5af83d59`. Координатор повторил `npm ci` (133 пакета), Vitest `6 passed`, TypeScript/Vite build OK, production JS без dev/mock маркеров; A сообщил Chrome 360×800 mock flow upload→poll→review→409→edit→confirm→explain→401 с сохранением URL. Review выявил редактируемый `settlement.formula_kind`, который B канонизирует как серверное поле; дефект возвращён A на read-only UI. A также заменяет literal mock upload bytes на синтетический fixture и затем проверит живой API.
- E2-A/B остаются `in_progress`, E2-C `accepted`. Следующее: принять fixes A/B, прогнать HTTP smoke на PG17 и повторное чтение после restart, затем живой браузерный UI. Release SHA/VM/MAX пока отсутствуют; прежние внешние доступы не появились.
## E2 container OCR and cross-component review (2026-09-27)

- Pushed integration SHA `b8438db9cc3a975f6299df0b9c19cc4ae8353ad9`. [GitHub Actions run 36322770140](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36322770140) completed `success`: isolated Compose/PostgreSQL 17, real worker, PDF-text upload/edit/confirm/explain, API/worker restart and persistence check; separate synthetic PNG upload asserted `source=ocr`, `needs_review=true`, `OCR_REVIEW_REQUIRED` before and after restart. Earlier run `36322481263` proved only PDF-text, so OCR claim applies to the later run.
- Accepted E2-C code `6b251b0e1770a2ca19c169943da38099c7076b7f`, report `056ea2e576d2fbf7be4dfae5733fc158eced4e17`; integrated at `2d94e9283ad30b251034426eb399c3102452f74f` and `5b94e1f90d150fdd5323d6f34acdafd8db750ab9`. Independent engine verifier OK, 25 unit tests OK, manifest 21/21 bytes and SHA OK, local Tesseract 5.5.3 synthetic raster checks OK. B E2 candidate `dcb880009b3f59b5ae7f415657cde2d06df8b0cd` integrated at `b8438db`; independent PostgreSQL 16 backend run `17 passed, 1 skipped` (legacy E1 test), HTTP verifier `28 operations/24 examples` OK. A candidate `b1a68b39861b7e6f5b1588f3c0453b079cd59c51` integrated at `ff650b9`, six frontend tests/build OK.
- Pending acceptance: live browser at 360 px on real API/DB/engine; B fixes for confirmed-edit AT-12, hidden validation warning ACK codes, §12.3 bounded OCR child and heartbeat; A read-only server fields and final E2 report; B final E2 report. E2-A/B still in progress. E3 has not been assigned. `main` has only accepted E1 runtime; no release SHA, VM deployment or MAX acceptance.
- External blockers remain VM public-key authentication and absent MAX credentials; no real resident receipt or pilot territory was supplied. Local instruction and unrelated uncommitted files remain preserved outside these commits.
