TASK_ID: E0-B-01
AGENT: B
STAGE: E0
BASE_SHA: 522757f58ad61951c7d66c4e97f2d5e65a433624
BRANCH: agent-b/e0
CONTRACT_VERSION: 1.0
SPEC_REF: 522757f58ad61951c7d66c4e97f2d5e65a433624
GOAL: Опубликовать полный P0 HTTP OpenAPI и канонические success/error examples, согласованные с принятыми DTO C, и план хранения/очереди.
INPUTS: TECHNICAL_SPEC.md v1.1 §§6–8, 11–14; задание C и будущий принятый integration SHA его DTO координатор передаст отдельно. Локальная «Работа с сервером.md» и актуальные инструкции VM — только для проверки доступа и границ, не копировать целиком в Git.
ALLOWED_PATHS: apps/backend/**, contracts/http/**, infra/**, scripts/**, compose.yaml, compose.local.yaml, compose.vm.yaml, .env.example, .dockerignore, .gitignore, README.md, DATA-API.yaml, THIRD_PARTY_NOTICES.md, docs/backend.md, docs/deployment.md, reports/agent-b.md, docs/contract-changes/agent-b/**.
SUBTASKS:
  - B-01: описать в contracts/http/openapi.yaml все P0 endpoints §7 и webhook §11.5, request/response, auth, idempotency, revision, pagination, MIME, errors и OpenAPI.servers с /team/zhkh. Добавить канонические JSON examples успеха и ошибок с валидными UUID.
  - Отдельно описать архитектуру таблиц §6.2, worker lease/retry/cancellation §12.3, файловой изоляции, двух пользователей, конфигурации dev/demo и границы адаптера C. Это проектная схема E0, без заявления о готовой БД/worker.
  - Проверить доступ на push и безопасно, без вывода секретов, наличие пути входа в VM и MAX-учётных данных. Не менять VM, общий Nginx, подписки MAX или production в E0. Если доступ отсутствует, указать точный уровень блокера.
  - До SHA C делать только независимые HTTP envelopes и каркас; после сообщения координатора включить принятые nested schemas C без ручного дублирования смысла и проверить examples. В споре о контракте предложить изменение координатору, не переписывать C.
  - Дать воспроизводимую проверку OpenAPI/JSON examples; записать точные команды и результат.
ACCEPTANCE: Спецификация покрывает все строки §7 и webhook; examples валидны, nested DTO совпадают с принятым C; ошибок 401/409/413/422/429/503 и unknown/partial/unsupported достаточно для A; в документах нет секретов, личной VM инструкции и заявлений о проведённом deploy. Если C ещё не принят, зависимый пункт остаётся явно review/blocked, а независимая часть передаётся отдельно.
REPORT: reports/agent-b.md
STOP_WHEN: Реализация и отдельный отчёт pushed в agent-b/e0 с обоими SHA для review либо конкретный блокер; не переходить к E1 или VM deploy без задания.
