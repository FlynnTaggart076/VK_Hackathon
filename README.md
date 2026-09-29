# Помощник ЖКХ в MAX — E4 кандидат с DeepSeek

Текущий release `a0844ee049a3213b078918eebc00dcdba3bab69b` развёрнут на VM:
production — `https://flynntaggart075.asuscomm.com/team/zhkh/`, отдельный
учебный preview — `https://flynntaggart075.asuscomm.com/team/zhkh-preview/`.
Это импорт переданного владельцем `release-005015c` с обновлённым просмотром
квитанций и справочником услуг. Код прошёл
[E2 Compose/PG17](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36621394896)
и [E4 preview/PG17](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36621395229)
на integration `47190ff`; release отличается только документацией. Публичный
preview проверен в Chrome на 360/1280 px с реальным API, отдельными гостями и
учебными квитанциями Москвы/Люберец за два месяца после этого обновления.
MAX Android чат ранее подтверждён владельцем; запуск mini-app и полный сценарий
в MAX Web/Android требуют отдельной приёмки и привязки production URL к боту.
Подробности обновления — [отчёт VM](reports/release-a0844ee-vm.md).

Каталог и демонстрационные квитанции синтетические. Локальный текстовый ЕПД
Московской области извлечён на 19 начисленных строк, но требует проверки и
подтверждения пользователем. Иные реальные форматы и локальные инструкции
УК/поставщиков не подтверждены. Городская статистика показывается лишь при
пяти сопоставимых подтверждённых квитанциях жителей с согласием; такой реальной
выборки пока нет.
В preview доступно числовое сравнение только с фиксированной синтетической
выборкой, явно помеченной как учебная; это не статистика жителей города.
Голос, транскрибация и реальная отправка обращения не входят в продукт.
Уровни проверок и оставшиеся блокеры — в [интеграционном отчёте](reports/integration.md) и
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
