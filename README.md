# Помощник ЖКХ в MAX — E1 dev-сборка

Текущий backend реализует демонстрационный вход, профиль, загрузку квитанции,
сохраняемую очередь и обработчик **dev stub**. OCR пользовательских файлов пока
отключён. Явный импорт двух синтетических образцов доступен после подтверждения
privacy notice. `GET /api/v1/meta` показывает `engine_stub: true`,
`receipt_ocr: false` и `comparison: false`. Режимы `demo` и `production`
заблокированы до интеграции MAX и реального engine.

## Локальный Compose

Скопируйте `.env.example` в приватный `.env`, замените оба placeholder-секрета
и запустите из корня checkout:

```sh
docker compose -p vk-zhkh-test-b -f compose.yaml -f compose.local.yaml config --quiet
docker compose -p vk-zhkh-test-b -f compose.yaml -f compose.local.yaml up --build -d
docker compose -p vk-zhkh-test-b -f compose.yaml -f compose.local.yaml ps
```

URL: `http://localhost:8080/team/zhkh/`. Публичен только loopback порт web;
API, PostgreSQL и worker находятся в частной сети. Сервис `migrate` запускает
Alembic до API и worker. Для проверки: `GET /team/zhkh/api/v1/meta` и
`GET /team/zhkh/health/ready`. Готовность требует heartbeat worker.

`apps/backend/Dockerfile` и `infra/web.Dockerfile` используют общий корневой
build context. Nginx local снимает `/team/zhkh/`; VM вариант принимает уже
очищенный путь от внешнего прокси. `Vite` собран с префиксом `/team/zhkh/`.

## Проверки без Docker

Установите `apps/backend/requirements.lock` в изолированное Python окружение,
добавьте `apps/backend` в `PYTHONPATH`, затем:

```sh
python -m pytest apps/backend/tests -q
python scripts/check_http_contract.py
```

PostgreSQL тест запускается только при `TEST_POSTGRES_URL` на отдельную локальную
тестовую базу `zhkh_e1_test` на `127.0.0.1`; каждый прогон создаёт свой
уникальный schema внутри неё. Без переменной тест отмечен как skipped.
Подробности миграций и ограничений — [docs/backend.md](docs/backend.md),
схема развёртывания — [docs/deployment.md](docs/deployment.md).

Рабочая VM, общий Nginx и MAX в E1 не изменяются. Финальное развёртывание
выполняется только из принятого release SHA по `TECHNICAL_SPEC.md` §12.8.
