# Помощник ЖКХ в MAX — E4 технический кандидат

На командной VM из принятого SHA `d3fa9b2fc4ea3ae89a0691c331945d2a6d1354f9`
развёрнут технический E4-кандидат: PostgreSQL 17, миграции, API, worker с
реальным OCR, web под
`https://flynntaggart075.asuscomm.com/team/zhkh/`. Production отключает
демовход и engine stub. Webhook MAX зарегистрирован на публичный HTTPS URL;
сценарий в MAX Web/мобильном MAX ещё не принят. Организаторы должны привязать
mini-app к боту после подачи опубликованного URL. Не путать наличие страницы и
webhook с проверенным входом из MAX.
После исправления чата очередь ответов MAX обработана, но их отображение в
клиенте Android ожидает подтверждения владельца.

Каталог и демонстрационные квитанции синтетические. OCR на VM проверен только
на семи синтетических растровых образцах одного учебного макета; качество на
реальных квитанциях и локальные инструкции УК/поставщиков не подтверждены.
Голос, транскрибация и реальная отправка обращения не входят в продукт.
Уровни проверок и оставшиеся блокеры — в [отчёте B](reports/agent-b.md) и
[плане](IMPLEMENTATION_PLAN.md).

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

Повторное развёртывание выполняется только из нового принятого release SHA по
`TECHNICAL_SPEC.md` §12.8 с закрытым `runtime/app.env` вне Git. Порядок,
проверки, backup/restore и границы общего Nginx — в
[инструкции развёртывания](docs/deployment.md). Локальный Compose выше остаётся
dev-средой и не подтверждает MAX Web/mobile.
