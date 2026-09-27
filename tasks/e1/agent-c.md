TASK_ID: E1-C-01
AGENT: C
STAGE: E1
BASE_SHA: feb1fc7ab12201e6d5a93989d64a8374fe44a139
BRANCH: agent-c/e1
CONTRACT_VERSION: engine/HTTP 1.0
SPEC_REF: feb1fc7ab12201e6d5a93989d64a8374fe44a139
GOAL: Сделать устанавливаемый housing_engine с реальной валидацией и арифметикой синтетической квитанции, чтением PDF-text и первой проверяемой OCR-тропой одного макета.
INPUTS: Принятые C DTO/fixtures и `contracts/engine/v1` из BASE_SHA; ТЗ §§8–9, 14.3 E1, 15.1. B использует публичный API пакета, а не внутренние функции.
ALLOWED_PATHS: packages/housing_engine/**, knowledge/**, contracts/engine/**, fixtures/**, docs/engine.md, docs/data-provenance.md, reports/agent-c.md, docs/contract-changes/agent-c/**.
SUBTASKS:
  - Реализовать `validate_bill(BillData)` и чистые Decimal-проверки строк, текущих начислений и трёх печатных итогов по §9.4; `null` не превращать в 0. Покрыть fixtures 5×40=200, 6×45=270, -50 adjustment, долг/оплату, переплату, неподдерживаемую формулу и mismatch.
  - Добавить один документированный учебный макет и синтетический PDF с текстовым слоем, созданный в разрешённых fixtures, manifest с SHA-256/ожидаемыми полями. Реализовать чтение PDF-text из bytes, признаки пригодности текстового слоя и ограниченный вход Tesseract для изображения/скана того же макета с тайм-аутом и без shell; на неизвестном/нечитаемом формате `manual_required` или `partial`, без ответа по filename.
  - Не реализовывать в E1 полное объяснение/сравнение/15 тем/черновики E2–E3; публичные точки остаются явными и не притворяются готовыми. Документировать системные OCR-зависимости для B без правки Dockerfile B.
  - Добавить значимые unit/fixture tests и команды установки/запуска в `docs/engine.md`; синтетический PDF/скан отличать от настоящих квитанций.
ACCEPTANCE: `pip install` из lock и тесты проходят без БД/MAX/HTTP; v1 DTO не меняются молча; 200→270 и частичные/отрицательные случаи дают точные Decimal-результаты; извлечение вызывается с bytes, а не путём/именем; текстовый PDF даёт проверяемые поля, image OCR реально вызывает Tesseract либо точный блокер системной зависимости зафиксирован; corrupted/unknown не дают выдуманного `recognized`.
REPORT: reports/agent-c.md
STOP_WHEN: Отдельные pushed code/report SHA и фактические результаты E1 переданы координатору для review либо указан точный блокер; E2 не начинать без задания.
