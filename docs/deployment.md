# E1 Compose и маршрутизация

Статус: первый dev стенд проверен в изолированном GitHub Actions runtime на
PostgreSQL 17; общая VM и MAX пока не проверены. Развёртывание на общей VM
требует принятого release SHA и порядка из `TECHNICAL_SPEC.md` §12.8.

## Локальная схема

`compose.yaml` задаёт PostgreSQL 17, отдельный `migrate`, API, worker и web без
host ports. `compose.local.yaml` публикует только `web` на
`127.0.0.1:${LOCAL_WEB_PORT:-8080}` через отдельную обычную сеть `local_edge`
и монтирует `infra/nginx/app-local.conf`. Web также подключён к закрытой
`private` сети для связи с API; БД, API и worker остаются только в ней.
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
отсутствующих файлов; SPA fallback действует только для UI. Оба server config
явно задают `root /usr/share/nginx/html` для собранного Vite `dist`.
Multipart лимит
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

## Проверка E1 в CI

[Actions run #6](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36318770691)
на integration SHA `0b0daaf994315c63de8f0db7d458de6411a31d81` завершился
успешно. В изолированном Compose project он выполнил `config --quiet`,
`up --build --detach`, проверил PostgreSQL major version 17, HTTP 200 для
`/team/zhkh/health/ready`, `/team/zhkh/` и `/team/zhkh/api/v1/meta`,
запущенный worker, `nginx -t`, загрузку JS asset и refresh вложенной SPA
страницы. Meta подтвердил явные `engine_stub=true` и `receipt_ocr=false`.
Эта проверка не является приёмкой VM или реального клиента MAX.
