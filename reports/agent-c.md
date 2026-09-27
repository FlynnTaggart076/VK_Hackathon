# Отчёт агента C — E3-C-01

- Ветка `agent-c/e3`; BASE_SHA `b33ed1e0493d76dfd7051a141e2075c698f8e967`; TASK_COMMIT `c11b5235319c12ecb18a6c4ca05c35a54f5c0560`.
- Статус: E3-C-01 передан координатору на review. Контракт engine/HTTP 1.0, DTO и JSON Schema v1 не изменены.
- Pushed code SHA: ранний compare checkpoint `5c1adc523d19f4e5c9ea3fabb1f27c71bfb1cd73`; исправление §7.5 и математические tests `b2cdf1b41ed50319e5e91a451fdcfc2511a4160d`; итоговый код/каталог/документация `8d4cd0cd49134735b05c6957c98c6ac5525cdbba`. SHA commit этого отчёта сообщу отдельно после push.
- Изменены только разрешённые C пути. Main, backend/web, Dockerfile B и VM не менялись. E4 не начат.

## Публичный compare checkpoint

`compare_receipts(CompareRequest, KnowledgeBundle)` сортирует по периоду, блокирует один месяц, явные разные счёт/поставщик/адрес и редакции одного документа. Счёт нормализуется удалением пробелов/дефисов с сохранением ведущих нулей; адрес — только регистр, пробелы, знаки разделения и словарные `ул./д./кв.`. Когда реквизит отсутствует и `identity_acknowledged=false`, возвращает `needs_identity_confirmation`: older/newer и конкретные `IDENTITY_UNVERIFIED` paths, action проверки, все `delta_*`/`unexplained_delta=null`, строки и settlement deltas пусты. ACK=true разрешает предупреждённый расчёт; явное противоречие остаётся ошибкой `INCOMPARABLE_RECEIPTS`.

По байтам двух сгенерированных текстовых PDF через публичный `extract_receipt` и две confirmed DTO получено: август `5 × 40 = 200.00`, сентябрь `6 × 45 = 270.00`; `delta_current_charges=70.00`, `delta_total_due=70.00`, `quantity_effect=40.00`, `tariff_effect=30.00`, `rounding_effect=0.00`, `unexplained_delta=0.00`, `status=complete`. Ожидания независимо заданы в `fixtures/receipts/water-comparison.json`. Это синтетические bytes, не реальная квитанция и не измерение потребления.

Сопоставление строк по коду, области, единице, поставщику и сегменту; для `other` учитывает название и подпись единицы. Отдельные день/ночь не объединяются, несовместимые единицы не получают эффект объёма/тарифа, дубликаты дают `ambiguous`, а не произвольную пару. `added/removed` описывают присутствие строки в документах, не факт подключения услуги. Проверены только объём, только тариф, дробное округление с `rounding_effect=-0.01`, несоседние периоды и явные реквизитные противоречия.

`delta_current_charges` включает adjustment один раз. Отдельный `delta_adjustments` раскрывает его долю, не добавляя второй раз. `settlement_deltas` разделяют opening balance, оплаты со знаком отрицательного вклада, пени, прочие изменения и credit clamp. В синтетическом случае 200→190: услуги 200→270, новый adjustment -50, оплаты 0→30: текущие начисления +20, вклад оплаты -30, итог -10, остаток 0. Если оплаты неизвестны, `unexplained_delta=null` и status partial; переплата 0 к оплате объясняется clamp; напечатанные итоги сохраняются независимо. Mismatch 220 рассчитано / 230 напечатано даёт partial и видимый residual 10 без обвинения организации.

## Каталог, вопросы и черновик

`load_knowledge` читает только локальные YAML, проверяет 15 уникальных тем, территории, ссылки на источники, сроки и host allowlist; `knowledge_version` меняется вместе с содержимым. Текущая allowlist пуста. `answer_question` использует явный topic_id либо контролируемые utterances/keywords/aliases (`MIN_SCORE=2`, `MIN_MARGIN=2`), не вызывает сеть. Неизвестная тема даёт unsupported либо уточнение из максимум трёх вариантов. «Справка» сначала уточняет вид документа, затем территорию и роль по одному полю. Просроченная карточка, синтетический/просроченный/чужой источник не превращается в местную инструкцию. Все 15 карточек дают только общий безопасный текст; локальные темы явно сообщают об отсутствии проверенной местной инструкции.

`compose_draft` берёт только подтверждённые поля текущих receipt refs и `line_id`. Пользовательский вопрос показан как отдельная неподтверждённая формулировка и не управляет алгоритмом. Неизвестные поля не подставляются. Без проверенного канала `recipient=null`, `actions=[]`, `RECIPIENT_UNVERIFIED`; отправки нет. B остаётся владельцем проверки актуальности ревизий, сохранения/stale черновика, UI копирования и внешних переходов.

## Проверки

Чистая временная Windows Python 3.13 venv вне Git: `$env:TEMP\zhkh-c-e3-venv`. Установка из `packages/housing_engine/requirements.lock`, затем `pip install --no-build-isolation --no-deps -e packages/housing_engine` прошла. Из корня checkout:

```powershell
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" packages/housing_engine/verify_contract.py
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" -m unittest discover -s packages/housing_engine/tests -q
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" -m pip check
git diff --cached --check
```

Результат после итогового code SHA: verifier 0 (`15 schema-valid topics`, DTO/schema/fixtures/manifest OK), unittest 0 (`Ran 42 tests ... OK`), pip check 0 (`No broken requirements found`), staged diff check 0. `EOF marker not found` дважды выводится существующими негативными PDF fixtures при общем unittest, но suite завершается успешно. Проверка synthetic OCR на Tesseract выполнена и задокументирована в принятом E2 отчёте; E3 сравнение использовало PDF text bytes. Не проверялись реальная квитанция, фото, Python 3.12/Linux, Docker, VM или MAX.

## Ограничения и передача B

Пилотная территория, реальные квитанции, проверенные источники, организации и каналы не предоставлены. `pilot_territory_id=null`, `sources=[]`, `organizations=[]`, `source-host-allowlist=[]`; ни один `verified_at` не выдуман. Карточки generic/synthetic, `review_after` — редакционный срок, не факт проверки внешнего материала. Два точно названных вида жилищных справок для пилотной территории (§10.1) пока заблокированы отсутствием территории/первичных источников; локальные инструкции и получатель черновика не объявляются готовыми.

B может принимать engine SHA после ревью, вызывать публичные функции без dev stub и проверять владельца/актуальность ревизий перед каждым запросом. Для source/knowledge deployment нужно включить каталог `knowledge/` рядом с пакетом и передать локальный путь в `load_knowledge`; runtime сеть не нужна. Готовность E3 в интеграции и E4 выдаёт только координатор после проверки B/A. Следующий шаг C — устранить конкретные замечания ревью E3 или принять новое задание E4 после общей приёмки.
