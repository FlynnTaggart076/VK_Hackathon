# Отчёт агента C

- Task ID: `E0-C-01`; этап E0; ветка `agent-c/e0`; статус: `review`.
- BASE_SHA: `522757f58ad61951c7d66c4e97f2d5e65a433624`; TASK_COMMIT: `b5f0d55d96761fdb4fe495f719ad6eaa2a0fee94`; контракт: engine v1 / BillData schema_version 1.0.
- Commit первичного DTO/fixture checkpoint: `1710e8555678e56b3e931e04987b94e1fbbb2852`.
- Проверенный финальный commit реализации, последний pushed SHA до отчёта: `8114fd6de0d7112f529012967aaadb6fadedbf92`.

## Результат

Опубликованы Pydantic DTO, JSON Schema для BillData, FieldEvidence, Issue и входов/выходов семи функций §8.2, сигнатуры и EngineError. Оба BillData из §7.7 и самостоятельный эталон сравнения фиксируют 200.00 → 270.00, разницу 70.00 и эффекты 40.00/30.00. Добавлены схема и пустой безопасный каркас knowledge, `demo-territory`, `pilot_territory_id: null`, описание учебного макета и происхождения каждого fixture. Точные версии Python-зависимостей закреплены в `packages/housing_engine/requirements.lock`.

Основные пути: `packages/housing_engine/**`, `contracts/engine/v1/**`, `fixtures/receipts/**`, `knowledge/**`, `docs/engine.md`, `docs/data-provenance.md`. Чужие области и VM не менялись.

## Проверки и среда

Windows, Python 3.13.14; новая временная venv вне Git. Из корня checkout последовательно:

```powershell
python -m venv "$env:TEMP\zhkh-c-e0-lockcheck"
& "$env:TEMP\zhkh-c-e0-lockcheck\Scripts\python.exe" -m pip install -r packages/housing_engine/requirements.lock
& "$env:TEMP\zhkh-c-e0-lockcheck\Scripts\python.exe" -m pip install --no-build-isolation --no-deps -e packages/housing_engine
& "$env:TEMP\zhkh-c-e0-lockcheck\Scripts\python.exe" packages/housing_engine/verify_contract.py
& "$env:TEMP\zhkh-c-e0-lockcheck\Scripts\python.exe" -m unittest discover -s packages/housing_engine/tests -v
```

Факт: установка завершилась с кодом 0; verifier: `Engine v1 schemas and synthetic 200 -> 270 fixtures: OK`, `Knowledge catalog structure: OK; real pilot territory and verified sources pending`; unittest: `Ran 1 test ... OK`. Негативный тест меняет сумму августовского fixture только во временной копии и требует ненулевого exit code verifier. `git diff --cached --check` перед обоими commit не выявил ошибок. Проверка выполнена локально на синтетических данных, без DB, HTTP, MAX, VM, сети при запуске verifier, OCR и реального документа. Python 3.12 в этой среде не проверялся.

## Ограничения, зависимости, следующий шаг

E0 публикует интерфейс: семь функций пока явно выбрасывают `NotImplementedError`. Реальные OCR, математика, знание по 15 темам и черновики не объявлены готовыми. Нет PDF/изображения, выбранной реальной территории, проверенных URL или даты проверки источника. Файл `knowledge/manifest.yaml` описывает контрактный каркас, не рабочий справочник для ответа пользователю. В E1 после отдельного задания нужны реализация пакета и содержимое согласно принятому контракту. B может использовать схему/fixtures и явный dev stub, но не вызывать функции C как готовые.

Предложения изменения публичного формата сейчас отсутствуют. До приёмки координатору нужно проверить code SHA `8114fd6de0d7112f529012967aaadb6fadedbf92` и совместимость с OpenAPI B; затем выдать отдельное E1 задание. SHA commit этого отчёта передаётся координатору сообщением после push.
