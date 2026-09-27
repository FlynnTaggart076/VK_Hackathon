# E1 Compose и маршрутизация

Статус: конфигурация первого dev стенда; контейнерный runtime и VM пока не
проверены. Развёртывание на общей VM требует принятого release SHA и порядка
из `TECHNICAL_SPEC.md` §12.8.

## Локальная схема

`compose.yaml` задаёт PostgreSQL 17, отдельный `migrate`, API, worker и web без
host ports. `compose.local.yaml` публикует только `web` на
`127.0.0.1:${LOCAL_WEB_PORT:-8080}` и монтирует `infra/nginx/app-local.conf`.
Приватные данные в именованных томах `postgres_data` и `source_documents`.
Имя Compose проекта для проверки должно быть отдельным от `vk-zhkh`.

```sh
docker compose -p vk-zhkh-test-b -f compose.yaml -f compose.local.yaml config --quiet
docker compose -p vk-zhkh-test-b -f compose.yaml -f compose.local.yaml up --build -d
curl -f http://127.0.0.1:8080/team/zhkh/api/v1/meta
curl -f http://127.0.0.1:8080/team/zhkh/health/ready
```

Локальный Nginx удаляет `/team/zhkh/`, затем проксирует `/api/`,
`/integrations/` и `/health/` в API. `/assets/` имеет строгий 404 для
отсутствующих файлов; SPA fallback действует только для UI. Multipart лимит
Nginx 12 MiB допускает файл 10 MiB с обрамлением, окончательный лимит проверяет
backend. Внутренний `app-vm.conf` получает уже очищенный от внешнего префикса
путь. Он сохраняет `X-Forwarded-Proto`, если тот передан доверенным внешним
прокси; production trust policy ещё требует VM-проверки.

## Граница VM

`compose.vm.yaml` добавляет только web в external сеть `vk-zhkh-edge` под
alias `vk-zhkh-web`. API и БД остаются в частной сети. Файлы в `infra/` не
заменяют общий Compose или Nginx команды. Изменение общего входа, backup
конфигурации, проверка `nginx -t`, reload/recreate и публичный smoke test
выполняются только назначенным оператором в последовательности §12.8.

Для будущего принятого release SHA проверка конфигурации из deploy checkout:

```sh
docker compose --env-file ../runtime/app.env -p vk-zhkh -f compose.yaml -f compose.vm.yaml config --quiet
```

`runtime/app.env` и реальные токены живут вне Git. `.env.example` содержит
только placeholder значения. E1 dev image не содержит Tesseract и не выполняет
OCR; настоящий engine и MAX будут интегрированы в последующих этапах.
