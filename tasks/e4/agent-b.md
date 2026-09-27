# E4 — B: развёртывание принятого SHA и MAX

- Роль: backend/MAX/VM по §18.3. Remote: `https://github.com/FlynnTaggart076/VK_Hackathon.git`.
- BASE_SHA = принятый E3 release SHA `d223c4e49a12c4ebc5d98c3c8da8fc6c0202e16f`; только этот SHA допускается для первого deploy, следующий — лишь после отдельной приёмки координатором.
- Ветка: `agent-b/e4`; checkout: `.checkouts/agent-b-e4`. Контракт engine/HTTP v1.0 + E3. Разрешённые записи: `apps/backend/**`, `infra/**`, `compose*.yaml`, `.env.example`, `docs/backend.md`, `docs/deployment.md`, `reports/agent-b.md`, HTTP contract proposal. Не менять frontend/engine/секреты в Git.

## Порядок и проверяемый результат

1. Прочитать `TECHNICAL_SPEC.md` §12.8, локальную «Работа с сервером.md» и на VM актуальные `/srv/team/README.md`, `/srv/team/web/README.md`. Сначала read-only preflight: `/team/`, `/healthz`, диски/память, каталоги/имена, сеть, существующие Compose и Nginx. Отчёт без чужих данных.
2. Подготовить собственный VM Compose и `docs/deployment.md`: приватная сеть приложения, отдельная external `vk-zhkh-edge`, alias `vk-zhkh-web`, закрытые API/БД, точные пути `/srv/team/vk-hackathon/{deploy,runtime}` и `/team/zhkh/`. Локально проверить `docker compose config`, миграции, test/backup restore в отдельной БД, безопасность ошибочных настроек. Не трогать соседние проекты.
3. До записи в VM проверить через защищённый канал наличие MAX bot token, webhook secret, связанного mini-app/`MAX_WEB_APP` и права регистрации; значения не печатать/не коммитить. Если условия есть: из чистого checkout точного release SHA выполнить §12.8, перед изменением общего Nginx сделать закрытые копии, `nginx -t`/Compose config, изменить только собственный маршрут/сетевое подключение, проверить до/после `/team/` и `/healthz`. Из dev-машины отдельно проверить публичный HTTPS, UI/assets/deep link/API, webhook без секрета. Зарегистрировать MAX mini-app/webhook и пройти живой MAX Web/mobile с A. Отчёт разделяет VM, внешний HTTPS и MAX.
4. Если credentials/регистрация отсутствуют, не запускать production с фиктивными значениями и не объявлять VM/MAX принятыми. Продолжить независимые config/docs/negative checks и указать точный блокер. Голос и реальная отправка обращений запрещены.

Любое изменение runtime-кода push отдельно и передать координатору на проверку до нового release SHA. Секреты, дампы, ключи и полные чужие конфиги вне Git. Code commit и отдельный report commit push; указать фактический deployed SHA или `not deployed`.
