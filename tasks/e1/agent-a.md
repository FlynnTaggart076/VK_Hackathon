TASK_ID: E1-A-01
AGENT: A
STAGE: E1
BASE_SHA: feb1fc7ab12201e6d5a93989d64a8374fe44a139
BRANCH: agent-a/e1
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: feb1fc7ab12201e6d5a93989d64a8374fe44a139
GOAL: Превратить E0 shell в работающий первый запуск и навигацию со всеми базовыми состояниями, сохранив заменяемый mock и подключив dev meta/auth/upload B после принятого checkpoint.
INPUTS: Принятый OpenAPI/fixtures из BASE_SHA; E1 dev API B и его SHA координатор передаст после проверки. ТЗ §§7, 11, 14.3 E1. MAX Bridge ещё не считается проверенным клиентом.
ALLOWED_PATHS: apps/web/**, docs/frontend.md, docs/demo.md, docs/user-validation.md, reports/agent-a.md, docs/contract-changes/agent-a/**.
SUBTASKS:
  - Реализовать onboarding по `GET /meta`, `GET /catalog`, `GET/PUT /me/profile`: роль, территория, версия/текст privacy notice, явное согласие и сохранение; при неполном профиле показывать доступный общий вопрос, а upload блокировать по серверному состоянию.
  - Реализовать навигацию, loading/empty/error/401/409/413/422/offline состояния и переключение mock ↔ real dev API без изменения экранов. Сессия только в памяти, expired ведёт к повторному входу без потери уже сохранённого документа.
  - Добавить dev upload entry и отображение queued job из API B после передачи принятого SHA; не выдавать E2 review/confirm/explanation за готовые. До backend checkpoint можно независимо выполнить UI и MSW покрытие по контракту.
  - Сохранять `/team/zhkh/` для route/assets/API, 360 px доступность и отсутствие mocks/demo code в production build. Тесты должны проверять поведение onboarding и ошибки, а не копировать реализацию.
ACCEPTANCE: mock onboarding проходит с серверными meta/catalog/profile; ошибки и восстановление видимы; локально A вызывает реальные dev meta/auth/upload B после готового checkpoint с явной пометкой stub; `npm ci`, `npm test`, `npm run build` проходят и production dist без mock; реальный MAX не заявляется проверенным.
REPORT: reports/agent-a.md
STOP_WHEN: Отдельные pushed code/report SHA переданы координатору с результатами и уровнем mock/real; E2 не начинать без задания.
