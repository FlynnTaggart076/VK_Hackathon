# Помощник ЖКХ в MAX — E4 кандидат с DeepSeek

Код новой версии с DeepSeek, разбором ЕПД и городским сравнением прошёл
[E2 Compose/PG17](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36481270712)
и [E4 preview/PG17](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36481270745)
на integration SHA `9293b21`. Развёртывание новой версии на VM и её проверка
в MAX ещё не выполнены. Production по адресу
`https://flynntaggart075.asuscomm.com/team/zhkh/` пока работает из SHA
`d3fa9b2fc4ea3ae89a0691c331945d2a6d1354f9`, отдельный preview — из
`af2b066ab7d2854dc0138a0e0ef838598d8b76b4`. Организаторы должны привязать
mini-app к боту после подачи опубликованного production URL.

Каталог и демонстрационные квитанции синтетические. Локальный текстовый ЕПД
Московской области извлечён на 19 начисленных строк, но требует проверки и
подтверждения пользователем. Иные реальные форматы и локальные инструкции
УК/поставщиков не подтверждены. Городская статистика показывается лишь при
пяти сопоставимых подтверждённых квитанциях жителей с согласием; такой реальной
выборки пока нет.
Голос, транскрибация и реальная отправка обращения не входят в продукт.
Уровни проверок и оставшиеся блокеры — в [отчёте B](reports/agent-b.md) и
[плане](IMPLEMENTATION_PLAN.md).

## Локальный Compose

Скопируйте `.env.example` в приватный `.env`, замените placeholder-секреты
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
