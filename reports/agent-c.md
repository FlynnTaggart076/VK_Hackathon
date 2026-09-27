# Отчёт агента C — E3-C-01

- Ветка `agent-c/e3`; BASE_SHA `b33ed1e0493d76dfd7051a141e2075c698f8e967`; TASK_COMMIT `c11b5235319c12ecb18a6c4ca05c35a54f5c0560`.
- Статус: E3-C-01 передан координатору на review. Контракт engine/HTTP 1.0, DTO и JSON Schema v1 не изменены.
- Pushed code SHA: ранний compare checkpoint `5c1adc523d19f4e5c9ea3fabb1f27c71bfb1cd73`; исправление §7.5 и математические tests `b2cdf1b41ed50319e5e91a451fdcfc2511a4160d`; основной E3 код/каталог `8d4cd0cd49134735b05c6957c98c6ac5525cdbba`; проверенные generic sources `f43df01518b3aa717bea8725b71d82e5f76511a3`; названия пилотных регионов и проверка местного ограничения `13952b704986f37777bbe01be96332b0bdd71979`. Предыдущий source report SHA `68de83b617ed8f182f598083e774019ef5e97a0c`; новый report SHA сообщу после push.
- Изменены только разрешённые C пути. Main, backend/web, Dockerfile B и VM не менялись. E4 не начат.

## Публичный compare checkpoint

`compare_receipts(CompareRequest, KnowledgeBundle)` сортирует по периоду, блокирует один месяц, явные разные счёт/поставщик/адрес и редакции одного документа. Счёт нормализуется удалением пробелов/дефисов с сохранением ведущих нулей; адрес — только регистр, пробелы, знаки разделения и словарные `ул./д./кв.`. Когда реквизит отсутствует и `identity_acknowledged=false`, возвращает `needs_identity_confirmation`: older/newer и конкретные `IDENTITY_UNVERIFIED` paths, action проверки, все `delta_*`/`unexplained_delta=null`, строки и settlement deltas пусты. ACK=true разрешает предупреждённый расчёт; явное противоречие остаётся ошибкой `INCOMPARABLE_RECEIPTS`.

По байтам двух сгенерированных текстовых PDF через публичный `extract_receipt` и две confirmed DTO получено: август `5 × 40 = 200.00`, сентябрь `6 × 45 = 270.00`; `delta_current_charges=70.00`, `delta_total_due=70.00`, `quantity_effect=40.00`, `tariff_effect=30.00`, `rounding_effect=0.00`, `unexplained_delta=0.00`, `status=complete`. Ожидания независимо заданы в `fixtures/receipts/water-comparison.json`. Это синтетические bytes, не реальная квитанция и не измерение потребления.

Сопоставление строк по коду, области, единице, поставщику и сегменту; для `other` учитывает название и подпись единицы. Отдельные день/ночь не объединяются, несовместимые единицы не получают эффект объёма/тарифа, дубликаты дают `ambiguous`, а не произвольную пару. `added/removed` описывают присутствие строки в документах, не факт подключения услуги. Проверены только объём, только тариф, дробное округление с `rounding_effect=-0.01`, несоседние периоды и явные реквизитные противоречия.

`delta_current_charges` включает adjustment один раз. Отдельный `delta_adjustments` раскрывает его долю, не добавляя второй раз. `settlement_deltas` разделяют opening balance, оплаты со знаком отрицательного вклада, пени, прочие изменения и credit clamp. В синтетическом случае 200→190: услуги 200→270, новый adjustment -50, оплаты 0→30: текущие начисления +20, вклад оплаты -30, итог -10, остаток 0. Если оплаты неизвестны, `unexplained_delta=null` и status partial; переплата 0 к оплате объясняется clamp; напечатанные итоги сохраняются независимо. Mismatch 220 рассчитано / 230 напечатано даёт partial и видимый residual 10 без обвинения организации.

## Каталог, вопросы и черновик

`load_knowledge` читает только локальные YAML, проверяет 15 уникальных тем, территории, ссылки на источники, сроки и host allowlist; `knowledge_version` меняется вместе с содержимым. Текущая allowlist содержит только `cdn.dom.gosuslugi.ru`. `answer_question` использует явный topic_id либо контролируемые utterances/keywords/aliases (`MIN_SCORE=2`, `MIN_MARGIN=2`), не вызывает сеть. Неизвестная тема даёт unsupported либо уточнение из максимум трёх вариантов. «Справка» сначала уточняет вид документа, затем территорию и роль по одному полю. Просроченная карточка, синтетический/просроченный/чужой источник не превращается в местную инструкцию. Две generic карточки теперь имеют SourceRef и явный переход на конкретную справку ГИС ЖКХ; локальные темы не выдают непроверенный порядок действий.

## Дополнительная проверка общих источников

2026-09-27 в 14:46 UTC фактически открыты и прочитаны две официальные страницы справки ГИС ЖКХ для граждан:

- [«Как перейти к списку лицевых счетов»](https://cdn.dom.gosuslugi.ru/webhelp/topics/accounts/cit/t_navigate-grazhd.html): раздел «Подключенные ЛС к Личному кабинету» и список подключённых счетов. Основание для общего маршрута в `account_number`, без обещания, что конкретный счёт там уже есть.
- [«История платежей»](https://cdn.dom.gosuslugi.ru/webhelp/topics/_citizen/payment/payment_history-grazhd.html): меню «Оплата ЖКУ» → «История платежей», сведения о внесении платы и просмотр сопоставления с начислениями. Основание для `payment_history`, без утверждения об учёте конкретной оплаты.

Для обоих `territory_id=null`, `is_synthetic=false`, `verified_at=2026-09-27T14:46:15Z`, `review_after=2026-12-27T14:46:15Z`. `knowledge/sources.yaml`, URL allowlist и provenance зафиксированы в Git. Вопросы `account_number`/`payment_history` возвращают актуальный SourceRef и `open_link` только пока источник действует; после expiry ответ `unsupported` без ссылки. Тесты показывают generic ссылку при контексте Москва и Московская область и `unsupported` для местной передачи показаний. Эти источники не подтверждают местную УК, срок показаний, тариф, порядок выдачи документов или канал получателя.

После ответа владельца в `knowledge/territories.yaml` и manifest добавлены `moscow` («Москва») и `moscow-oblast` («Московская область») как названия выбранных регионов: `is_synthetic=false`, `source_id=null`. `demo-territory` сохранён; `pilot_territory_id=null` до конкретного дома/УК. Это область пилота от владельца, а не проверка местного порядка действий. Для всех шести LOCAL_TOPICS теперь требуется актуальный региональный source_id: при его отсутствии Москва и МО возвращают `unsupported` без ссылки и действий. Оба generic источника ГИС ЖКХ доступны для этих регионов с `territory_id=null`. Тесты проверяют оба региона и все шесть местных тем.

`compose_draft` берёт только подтверждённые поля текущих receipt refs и `line_id`. Пользовательский вопрос показан как отдельная неподтверждённая формулировка и не управляет алгоритмом. Неизвестные поля не подставляются. Без проверенного канала `recipient=null`, `actions=[]`, `RECIPIENT_UNVERIFIED`; отправки нет. B остаётся владельцем проверки актуальности ревизий, сохранения/stale черновика, UI копирования и внешних переходов.

## Проверки

Чистая временная Windows Python 3.13 venv вне Git: `$env:TEMP\zhkh-c-e3-venv`. Установка из `packages/housing_engine/requirements.lock`, затем `pip install --no-build-isolation --no-deps -e packages/housing_engine` прошла. Из корня checkout:

```powershell
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" packages/housing_engine/verify_contract.py
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" -m unittest discover -s packages/housing_engine/tests -q
& "$env:TEMP\zhkh-c-e3-venv\Scripts\python.exe" -m pip check
git diff --cached --check
```

Результат после region code SHA: verifier 0 (`15 schema-valid topics`, DTO/schema/fixtures/manifest и source allowlist OK; точные названия двух регионов, `source_id=null`, `pilot_territory_id=null` проверены), unittest 0 (`Ran 43 tests ... OK`), pip check 0 (`No broken requirements found`), staged diff check 0. `EOF marker not found` дважды выводится существующими негативными PDF fixtures при общем unittest, но suite завершается успешно. Проверка synthetic OCR на Tesseract выполнена и задокументирована в принятом E2 отчёте; E3 сравнение использовало PDF text bytes. Не проверялись реальная квитанция, фото, Python 3.12/Linux, Docker, VM или MAX.

## Ограничения и передача B

Владелец назвал пилотные регионы Москва и Московская область, их ID теперь `moscow` и `moscow-oblast`. Конкретный дом/УК и локальные первоисточники не предоставлены. `pilot_territory_id=null`, каталог включает также `demo-territory`; `sources` содержит две проверенные общие страницы, `organizations=[]`, host allowlist ограничена одним официальным доменом. Срок карточки — редакционный, не подмена фактического `verified_at` страницы. Два точно названных вида жилищных справок для пилотных регионов (§10.1) остаются заблокированы без локального первоисточника; местные сроки/каналы и получатель черновика не объявляются готовыми.

B может принимать engine SHA после ревью, вызывать публичные функции без dev stub и проверять владельца/актуальность ревизий перед каждым запросом. Для source/knowledge deployment нужно включить каталог `knowledge/` рядом с пакетом и передать локальный путь в `load_knowledge`; runtime сеть не нужна. Готовность E3 в интеграции и E4 выдаёт только координатор после проверки B/A. Следующий шаг C — устранить конкретные замечания ревью E3 или принять новое задание E4 после общей приёмки.
