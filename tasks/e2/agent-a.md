TASK_ID: E2-A-01
AGENT: A
STAGE: E2
BASE_SHA: dae14d9a838154b72e4cf122881b190032ae0a74
BRANCH: agent-a/e2
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: dae14d9a838154b72e4cf122881b190032ae0a74
GOAL: Провести одну платёжку через UI от загрузки и ожидания job до проверки/правки, подтверждения и объяснения без выдачи stub за OCR.
INPUTS: Принятые E1 main/контракты, `reports/integration.md`, `contracts/http/openapi.yaml`, `fixtures/receipts/manifest.json`, ТЗ §§7–9, 14.3 E2, 17.4. Разрешённые UI mock данные синтетические. Вызовы живого B E2 подключать после принятого координатором checkpoint; изменения формата только через владельца HTTP B.
ALLOWED_PATHS: apps/web/**, docs/frontend.md, docs/demo.md, docs/user-validation.md, reports/agent-a.md, docs/contract-changes/agent-a/**.
SUBTASKS:
  - По существующему OpenAPI реализовать состояния upload/polling и страницы receipt review: видимый исходник/доступный preview, evidence и issues, поля и строки BillData, маркировка OCR/partial/manual, явная возможность исправить распознанное. После reload восстановить состояние по ID через GET, не полагаться на память клиента.
  - Отправлять `PUT /receipts/{id}/draft` с `expected_revision`, затем `POST /receipts/{id}/confirm`; 409 revision conflict показывать с перезагрузкой данных без потери черновых правок пользователя. Не подтверждать при серверных ошибках/незаполненных обязательных полях.
  - После подтверждения показать `GET /receipts/{id}/explanation`: начисления, итог к оплате, различия и ограничения/источники в соответствии с полями ответа, без самостоятельной арифметики. Удаление/сравнение/FAQ/черновики обращений остаются E3.
  - Сохранить 360 px доступность, 401 восстановление маршрута, loading/empty/error/unsupported/offline, синтетическую/dev маркировку; MSW использовать только в dev mock и не включать в production dist. Добавить проверки реального поведения UI, mock сценария и позже живого B API, отдельные уровни evidence.
ACCEPTANCE: локальный mock сценарий upload→poll→review/edit→confirm→explain проходит на синтетическом fixture; после принятого B checkpoint тот же UI вызывает живые E2 endpoints, сохраняет receipt после reload; `npm ci`, `npm test`, `npm run build` проходят; production dist без mock/dev auth. Полная сквозная E2 приёмка остаётся у координатора после C→B→A интеграции и restart теста.
REPORT: reports/agent-a.md
STOP_WHEN: отдельные pushed code/report SHA и точные mock/live проверки переданы координатору для review либо описан конкретный блокер; E3 не начинать.
