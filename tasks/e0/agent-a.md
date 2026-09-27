TASK_ID: E0-A-01
AGENT: A
STAGE: E0
BASE_SHA: 522757f58ad61951c7d66c4e97f2d5e65a433624
BRANCH: agent-a/e0
CONTRACT_VERSION: 1.0
SPEC_REF: 522757f58ad61951c7d66c4e97f2d5e65a433624
GOAL: Сделать карту экранов и минимальный запускаемый React/TypeScript клиент с типизированным HTTP слоем и явным MSW mock для E0.
INPUTS: TECHNICAL_SPEC.md v1.1 §§6–7, 11, 13.2, 14.3–14.6; канонический OpenAPI B и fixtures C координатор передаст принятым integration SHA после проверки. До него опираться на примеры §7.7, не вводить новую семантику API.
ALLOWED_PATHS: apps/web/**, docs/frontend.md, docs/demo.md, docs/user-validation.md, reports/agent-a.md, docs/contract-changes/agent-a/**.
SUBTASKS:
  - A-01: карта экранов/состояний по §11.1 и пути навигации под /team/zhkh/; стартовый Vite React/TS shell с React Router, минимальными экранами и доступными подписями.
  - A-01/A-03: typed fetch client для /team/zhkh/api/v1, единый error envelope, bearer token только в памяти, AbortController; MSW mock явно включён только в dev: meta, demo auth и один receipt/answer example, включая хотя бы 401, 409 и partial/unsupported.
  - Обозначить синтетические данные. Не считать деньги в JS, не добавлять голос, отправку обращений, секреты или production demo auth.
  - После принятого OpenAPI B сгенерировать/сверить TS types и примеры; если контракт ещё не принят, передать независимый shell в review и перечислить зависимую проверку отдельно.
  - Записать команды npm ci, dev:mock, test/build и фактические результаты; lock-файл обязателен при выборе зависимостей.
ACCEPTANCE: Минимальный shell запускается на 360 px и маршруты сохраняют /team/zhkh/; mock API включается явным dev-флагом, production build не содержит активного mock/секретов; error envelope и типы согласованы с принятым OpenAPI, когда он передан; карта экранов покрывает §11.1 без заявления о готовом пользовательском пути E1–E3.
REPORT: reports/agent-a.md
STOP_WHEN: Реализация и отдельный отчёт pushed в agent-a/e0 с обоими SHA для review либо конкретный блокер; E1 не начинать без нового задания.
