# E4-C-PREVIEW: отчёт исполнителя C

- Task: `tasks/e4/agent-c-preview.md`.
- Base SHA: `61080a73fd23afd6ef6031dd893196a7cf212ed3`.
- Code SHA: `8e2fd2a776e67489bf344b37e8b4e00845959bda`.
- Ветка/checkout: `agent-c/e4-preview`, `.checkouts/agent-c-e4-preview`.
- Статус: готово к интеграционной проверке; **живой preview HTTP и браузер ещё не выполнялись**. VM не менял.

## Передано

- `packages/housing_engine/preview_acceptance.py` — исполняемая stdlib HTTP-проверка только для точного `/team/zhkh-preview/` на HTTPS либо loopback HTTP. Без логина получает двух разных виртуальных гостей, проверяет территорию Москва/МО и уведомление о данных, блокировку байтовой загрузки `403 PREVIEW_SYNTHETIC_ONLY`, две синтетические JSON-квитанции, review/confirm, объяснение, сравнение, FAQ, черновик, историю, owner isolation и удаление. Использует существующие `water-2026-08`, `water-2026-09` и `manifest.json`; суммы сравнивает с независимым `water-comparison.json`. Токены и ID гостей не выводит.
- `packages/housing_engine/PREVIEW_ACCEPTANCE.md` — команда запуска и ручной браузерный чеклист с разделением HTTP/browser/VM/MAX доказательств.
- Новых реальных данных, УК, местных каналов, исходников OCR или зависимостей нет.

## Проверки на кодовом SHA

| Проверка | Результат |
|---|---|
| `python -m py_compile packages/housing_engine/preview_acceptance.py` | pass |
| `.venv/Scripts/python.exe packages/housing_engine/verify_contract.py` | pass: Engine v1 schemas, synthetic 200→270 fixtures, knowledge source allowlist |
| `.venv/Scripts/python.exe -m pytest packages/housing_engine/tests -q` | **46 passed** за 1.63 с |
| Прямой вызов engine для трёх вопросов из скрипта | `answered`, `unsupported`, `unsupported` |
| Запуск скрипта без `PREVIEW_BASE_URL` | отказ до сетевого запроса: требуется `/team/zhkh-preview/` |
| `git diff --check` | pass |

`.venv` создан только внутри checkout и игнорируется Git. Preview-контракт `POST /api/v1/auth/preview` с пустым JSON и отдельным guest ID, `meta.mode=preview`, `403 PREVIEW_SYNTHETIC_ONLY` на raw upload подтверждён B при подготовке. Доказательство работы самого скрипта с live API ожидается после интеграции A/B и развёртывания принятого preview release SHA. Если script остановится до очистки, его синтетические записи могут остаться в preview БД; это описано в чеклисте.

## Границы вывода

46 локальных engine-тестов и синтетические данные не подтверждают точность реальных квитанций, работу mini-app в MAX, общедоступный HTTPS маршрут и сохранение production `/team/zhkh/`. В браузере и на VM сценарий должен быть проверен отдельно. E4 и E5 по этому отчёту не закрываются.
