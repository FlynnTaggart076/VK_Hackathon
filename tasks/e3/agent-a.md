TASK_ID: E3-A-01
AGENT: A
STAGE: E3
BASE_SHA: b33ed1e0493d76dfd7051a141e2075c698f8e967
BRANCH: agent-a/e3
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: b33ed1e0493d76dfd7051a141e2075c698f8e967
GOAL: Провести основной сценарий §17.4 после E2: две подтверждённые квитанции, сравнение 200→270 (70=40+30), вопрос/уточнение/источник, редактируемый черновик только с копированием, история и удаление.
INPUTS: принятый E2 main, OpenAPI/examples, DTO C и synthetic fixtures. Реальные пилотные данные, VM/MAX доступы пока отсутствуют.
ALLOWED_PATHS: apps/web/**, docs/frontend.md, docs/demo.md, docs/user-validation.md, reports/agent-a.md, docs/contract-changes/agent-a/**.
DEPENDENCIES: первый mock/UI checkpoint независим. Подключать реальный compare/answers/drafts только после pushed и проверенного B HTTP checkpoint, основанного на публичных функциях C. Если контракт неполон, предложить точный diff владельцу B/C через координатора, не вводить собственные DTO/формулы.
SUBTASKS:
  - Ранний pushed checkpoint: mock UI маршруты и тесты для выбора двух текущих confirmed квитанций, сравнения суммы/начислений/объёма/тарифа, identity acknowledgement, incompatible/ambiguous/partial/stale. Серверные эффекты отображать без клиентского пересчёта. Обозначать synthetic.
  - FAQ/помощник: все 15 topic_id доступны в каталоге; unknown и неясная «справка» дают уточнение или честное unsupported; показывать фактические source/территорию/актуальность, без выдуманного проверенного канала.
  - Черновик: показать факты из текущей confirmed строки, recipient/actions, дать редактировать и копировать текст. После изменения исходной ревизии показать stale и отдельное предупреждение перед копированием. Нет кнопки «отправить» и внешнего POST обращения.
  - История: pagination/empty, возобновление job, выбор двух документов, удаление с подтверждением, expired source (410) при сохранении derived цифр. 401/409/422/offline/clipboard unavailable и 360 px состояния.
  - После B checkpoint подключить реальные endpoints тем же API-клиентом без переключения экранных моделей. Проверить §17.4 в Chrome 360 px с двумя synthetic bytes, включая разницу 70 и unknown-вопрос; отделить mock от реального API в отчёте. MAX Bridge/mobile остаются E4.
CHECKS: npm test; npm run build; production dist без MSW/dev auth/секретов; browser mock полный §17.4; после реального B checkpoint browser на Compose PG17 и повторное чтение после restart. Сохранять чужие/CRLF-only изменения, stage только свои файлы.
STOP_AND_REPORT: code SHA первого checkpoint, затем итоговый code SHA и отдельный report SHA в origin/agent-a/e3; фактические команды/результаты и оставшиеся зависимости. Не начинать E4 и не объявлять E3 принятым самому.
