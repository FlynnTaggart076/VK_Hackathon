TASK_ID: E0-C-01
AGENT: C
STAGE: E0
BASE_SHA: 522757f58ad61951c7d66c4e97f2d5e65a433624
BRANCH: agent-c/e0
CONTRACT_VERSION: 1.0
SPEC_REF: 522757f58ad61951c7d66c4e97f2d5e65a433624
GOAL: Опубликовать проверяемый v1 контракт housing_engine с точными синтетическими fixtures и схемой knowledge, пригодный для встраивания B.
INPUTS: TECHNICAL_SPEC.md v1.1 §§6–10, 13.4, 14.3–14.6; канонический BillData `water-2026-08` и изменение `water-2026-09` из §7.7.
ALLOWED_PATHS: packages/housing_engine/**, knowledge/**, contracts/engine/**, fixtures/**, docs/engine.md, docs/data-provenance.md, reports/agent-c.md, docs/contract-changes/agent-c/**.
SUBTASKS:
  - C-01: формализовать DTO/JSON Schema v1 для BillData, FieldEvidence, Issue, входов/выходов всех семи публичных функций §8.2; закрепить enums, nullable, Money, Period, UUID, запрет лишних входных полей и версии.
  - Описать сигнатуры функций, EngineError, границу bytes/временной папки и поля, которые добавляет только B. Реальную OCR/математику E1–E3 сейчас не выдавать за готовую.
  - Добавить синтетические JSON fixtures двух квитанций 200.00 → 270.00 и ожидаемые delta 70.00, quantity_effect 40.00, tariff_effect 30.00; при необходимости включить остальные эталоны §9.8 как данные для будущих тестов.
  - Зафиксировать схему knowledge из §10.2, пилотную территорию как пока не выбранную; не выдумывать действующие ссылки, тарифы и даты проверки. Указать происхождение каждого fixture.
  - Опубликовать простую команду проверки схем и fixtures без DB, MAX, HTTP, сети и API ключей.
ACCEPTANCE: JSON fixtures валидируются своими schemas; проверка различает 200 и 270, точную разницу 70 и эффекты 40/30; нет недостоверных источников или настоящих персональных данных; интерфейс DTO согласуется с §6–8; команда завершается ненулевым кодом при испорченном fixture.
REPORT: reports/agent-c.md
STOP_WHEN: Два commit (сначала реализация, затем отчёт) pushed в agent-c/e0 и переданы оба SHA для review либо указан точный блокер push/контракта. Следующий этап без задания не начинать.
