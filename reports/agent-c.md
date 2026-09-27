# Отчёт агента C

- Task ID: `E1-C-01`; этап E1; ветка `agent-c/e1`; статус: `review`.
- BASE_SHA: `feb1fc7ab12201e6d5a93989d64a8374fe44a139`; TASK_COMMIT: `4449864e24686472130b2569be04b349ed862834`; контракт: engine/HTTP 1.0, DTO v1 не менялись.
- Code commits: `e58a28aedddad3a8433368f19f3db45c299cd0da` (основная реализация), `d1d6426502a5ddbc0591302903b0e311036fc3d3` (точность Decimal на максимальных значениях). Документация фактического OCR: `ed649aa3c3d4f2850f67ff3b84b5161351c72a3d` (последний pushed SHA до отчёта). SHA отдельного commit отчёта передаётся координатору после push.
- Принятая история E0: code `8114fd6de0d7112f529012967aaadb6fadedbf92`, report `09a20b1ea6b271138351775b5c38a7d5465e718b`.

## Реализовано

`validate_bill` проверяет период, непустое название услуги, суммы строк/перерасчётов, IDs и ссылки перерасчётов. Внутренний `calculate_bill` на `Decimal` считает строки, текущие начисления, баланс и сумму к оплате с `ROUND_HALF_UP`; неизвестные операнды остаются `null`. Три напечатанных итога сверяются отдельно. Mismatch даёт предупреждение и не закрывает подтверждение автоматически.

`extract_receipt` принимает только `DocumentInput.content` bytes и проверяет SHA-256, сигнатуру MIME, размер, число страниц PDF и число пикселей. Учебный `demo-bill-v1` читает текстовый PDF через pypdf, а PNG/скан направляет в Tesseract `rus+eng` без shell, с временным PNG только в каталоге задания и тайм-аутом. Неизвестный макет возвращает `manual_required`, повреждённый документ — `EngineError`, не ложный `recognized`. Публичные `explain_receipt`, `compare_receipts`, `answer_question`, `compose_draft`, `load_knowledge` пока явно не реализованы.

Учебные PDF, PNG и image-only PDF созданы из генератора; `fixtures/receipts/manifest.json` фиксирует SHA-256, размер, представление, происхождение и ожидаемые поля всех шести образцов. `.gitattributes` сохраняет PDF/PNG побайтно в Git. Системные зависимости OCR и границы макета задокументированы в `docs/engine.md`; происхождение — в `docs/data-provenance.md`. Чужие компоненты и VM не менялись.

## Проверки и фактический уровень доказательства

Windows, Python 3.13.14; новая временная venv вне Git. Из корня checkout:

```powershell
python -m venv "$env:TEMP\zhkh-c-e1-lockcheck"
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m pip install -r packages/housing_engine/requirements.lock
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m pip install --no-build-isolation --no-deps -e packages/housing_engine
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" packages/housing_engine/verify_contract.py
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m unittest discover -s packages/housing_engine/tests -v
& "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -m pip check
```

Факт: установка 0, verifier 0 (`schemas and synthetic 200 -> 270 fixtures: OK`, knowledge structure OK), unittest 0 (`Ran 17 tests ... OK`), `pip check` — `No broken requirements found`. Тесты покрывают 200/270, -50 adjustment, долг+оплату, переплату, неизвестную оплату, unsupported formula, mismatch, округление и предельную точность Decimal, непустое название, неверную ссылку перерасчёта и испорченный fixture. Git staged diff проверен, ошибки пробелов в исходниках отсутствуют. Индексированные в Git bytes PDF/PNG сверены с SHA-256 manifest.

**PDF-text:** реальное извлечение из синтетического текстового PDF вернуло `recognized`, период `2026-08`, объём `5.000000`, тариф `40.000000`, сумму `200.00`, evidence `pdf_text`. **Синтетический image OCR:** после исходного блокера отсутствующего бинарника координатор подготовил локальный Tesseract `v5.5.3.20260724`; `--list-langs` подтвердил `eng`, `osd`, `rus`. С `PATH` на этот бинарник я вызвал `extract_receipt(DocumentInput(bytes,SHA256), ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=['demo-bill-v1']))` отдельно на PNG и image-only PDF. Оба результата: `recognized`, период `2026-08`, объём `5.000000`, тариф `40.000000`, сумма строки и к оплате `200.00`. Координатор независимо повторил этот прогон на принятом integration SHA `27465869ec507b409e18d867245a034af61a2612`, получил 25 evidence, 18 с `needs_review`, и предупреждение `OCR_REVIEW_REQUIRED`. Это проверка фактического Tesseract на синтетических рендерах того же макета, не измерение качества на реальных квитанциях или телефонных фото. Python 3.12, VM и MAX не проверялись.

Команда фактического OCR из checkout (локальный Tesseract находится вне Git):

```powershell
$env:PATH = "$env:TEMP\zhkh-ocr-tesseract;$env:PATH"
& "$env:TEMP\zhkh-ocr-tesseract\tesseract.exe" --version
& "$env:TEMP\zhkh-ocr-tesseract\tesseract.exe" --list-langs
@'
from pathlib import Path
from uuid import UUID
import hashlib
import tempfile
from housing_engine import DocumentInput, ExtractionConfig, extract_receipt
config = ExtractionConfig(workspace=tempfile.gettempdir(), enabled_templates=["demo-bill-v1"])
for name, mime in [("demo-bill-2026-08.png", "image/png"), ("demo-bill-2026-08-scan.pdf", "application/pdf")]:
    content = (Path("fixtures/receipts") / name).read_bytes()
    document = DocumentInput(receipt_id=UUID("10000000-0000-4000-8000-000000000001"), content=content, mime_type=mime, sha256=hashlib.sha256(content).hexdigest())
    result = extract_receipt(document, config)
    line = result.bill_data.services[0] if result.bill_data.services else None
    print(name, result.outcome, result.bill_data.period, line.quantity if line else None, line.tariff if line else None, line.charge_amount if line else None, result.bill_data.document_total_due)
'@ | & "$env:TEMP\zhkh-c-e1-lockcheck\Scripts\python.exe" -
```

## Ограничения и следующий шаг

Распознаётся только английский синтетический учебный макет. PDF-text, PNG и image-only PDF проверены на нём; качество на квитанциях настоящей УК и телефонных фото неизвестно. Рабочий контейнер B ещё должен включить Tesseract 5 с `rus` и `eng`; локальный пользовательский тест не подтверждает сборку Docker или VM. Пилотная территория, проверенные источники и реальные макеты отсутствуют. B может потреблять `validate_bill`/`extract_receipt` через публичный API пакета, а для оставшихся пяти функций держать явный dev stub. Реальное объяснение/сравнение/FAQ/черновик — задачи E2–E3 после отдельного задания.

Для приёмки координатору проверить SHA реализации, v1-схемы/fixture manifest, результаты тестов и границу OCR. Отдельного предложения изменения контракта нет. Следующий этап самостоятельно не начинаю.
