# Отчёт агента C — E2-C-01

- Этап E2, ветка `agent-c/e2`, статус `review`.
- BASE_SHA `dae14d9a838154b72e4cf122881b190032ae0a74`; TASK_COMMIT `f613288e5b0a9bc733e6653ba9706bea7e3313d9`; engine/HTTP 1.0, DTO/schema v1 не менялись.
- Pushed code SHA: checkpoint `7242082cb940c8b05c0435b4802d2220710fa8e7`; итоговый `6b251b0e1770a2ca19c169943da38099c7076b7f`. SHA commit отчёта передаётся координатору после push.
- E1-C-01 принят до начала E2. Чужие компоненты, main, Dockerfile B и VM не менялись.

## Реализовано

`explain_receipt(ExplainRequest, KnowledgeBundle)` объясняет подтверждённый BillData через Decimal и общий `calculate_bill`: формула строки, разница с напечатанной суммой, услуги и отдельные перерасчёты без повторного учёта, долг, платежи, кредитовый остаток и три сверки итогов. Недостаток данных даёт `incomplete`, неподдерживаемая формула — `unsupported`, расхождение — `mismatch` с сохранением напечатанного числа. Ошибочная квитанция и агрегат вне Money вызывают безопасный `EngineError(INVALID_BILL)`; слишком большое произведение строки остаётся неизвестным с предупреждением. Проверенных нормативов/тарифов/ссылок нет: `sources=[]`, `actions=[]`, `ARITHMETIC_ONLY`.

`extract_receipt` читает только bytes. Шесть текстовых PDF учебного DEMO-BILL-V1 покрывают 200.00, изменение объёма/тарифа до 270.00, отдельный -50.00 перерасчёт, долг 100.00 с оплатой 80.00, переплату с закрытием -30.00 и неизвестную услугу `other`. Шесть PNG/JPEG рендеров и image-only PDF покрывают OCR. Для текстового PDF возвращаются page и нормализованный bbox найденной строки, иначе bbox=null. OCR возвращает page, bbox=null и `needs_review=true` для распознанных полей. Неизвестная услуга сохраняется как `other`, отмечается `SERVICE_UNMAPPED` и даёт `partial`.

Негативные fixtures: пустой растр, обрезанный PDF без итогов, чужой макет, повреждённый PDF и PDF с напечатанным 271.00 против рассчитанного 270.00. Сымитированный сырой OCR `2O0.00` на bytes PNG не исправляется скрыто до 200.00: результат `partial` без строки. Это unit проверка парсера после подмены текста OCR, а не фактическое чтение такого символа Tesseract. Все образцы перечислены с SHA-256/provenance в manifest, генератор закреплён lock файлом.

## Проверки

Среда: Windows, Python 3.13.14, временная venv вне Git по `requirements.lock`; для генератора добавлен `generator-requirements.lock`. Из корня checkout:

```powershell
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" packages/housing_engine/verify_contract.py
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m unittest discover -s packages/housing_engine/tests -q
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m pip check
$env:PATH = "$env:TEMP\zhkh-ocr-tesseract;$env:PATH"
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" packages/housing_engine/tests/smoke_e2_ocr.py
```

Результат: verifier 0 (schemas, SHA manifest, 200→270, knowledge structure OK); unittest 0 (`Ran 25 tests ... OK`); pip check 0 (`No broken requirements found`); Git staged diff check 0. Текстовые PDF bytes отдают реальные 200.00/270.00 и `source=pdf_text`; adjustment 270-50=220, долг/платёж 100+270-80=290, кредит max(-30,0)=0. Mismatch сохраняет напечатанное 271.00 и `unexplained_difference=1.00`.

Фактический OCR smoke: локальный user-scoped Tesseract `v5.5.3.20260724`; `--list-langs`: `eng`, `osd`, `rus`. Семь синтетических raster/scan inputs: пять обычных/adjustment/debt/credit PNG/JPEG `recognized` с ожидаемыми 200.00/270.00/220.00/290.00/0.00, unknown-service JPEG `partial` с `other`, image-only PDF `recognized` 200.00. У всех OCR evidence `needs_review=true`, есть `OCR_REVIEW_REQUIRED`. Это реальный OCR по сгенерированным изображениям, не проверка настоящих квитанций, телефонных фото, Docker, VM или MAX.

## Зависимости и ограничения для B

Python зависимости строго заданы `packages/housing_engine/requirements.lock`; runtime нужны pydantic, pypdf, pypdfium2, Pillow. Системно нужен Tesseract 5 с `eng+rus`, устанавливаемый в образ при сборке; проверить `tesseract --version` и `tesseract --list-langs`. `ExtractionConfig.workspace` — существующий доверенный временный каталог. Лимиты: 10 MiB bytes, 3 PDF страницы, 25 млн пикселей на страницу, OCR до 90 секунд. B отвечает за 120-секундный внешний timeout, RSS/контейнерный лимит и завершение дочерних процессов. Реальная пилотная территория, проверенные внешние источники и реальные макеты отсутствуют; объяснение остаётся арифметическим. Python 3.12 и Linux-контейнер этим отчётом не проверены.

Координатору проверить pushed SHA, схему/manifest, тесты и OCR evidence, затем передать B итоговый public API SHA. E3 самостоятельно не начинаю.
