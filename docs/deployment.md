# Развёртывание ЖКХ MVP: Compose и командная VM

Статус E4: на VM приложение ещё не развёрнуто. Исходный E3 SHA
`d223c4e49a12c4ebc5d98c3c8da8fc6c0202e16f` не подходит для production
MAX: у worker не было исходящей сети. Для первого deploy нужен новый принятый
координатором release SHA, реальные MAX token/webhook secret и связанный
mini-app target вне Git. Порядок и границы — `TECHNICAL_SPEC.md` §12.8.

## Историческая E1 проверка

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

Первоначальная E1 VM схема добавляла только web в external сеть
`vk-zhkh-edge` под alias `vk-zhkh-web`. Актуальная E4 схема ниже также
даёт worker отдельный outbound путь. API и БД остаются в частной сети.
Файлы в `infra/` не
заменяют общий Compose или Nginx команды. Изменение общего входа, backup
конфигурации, проверка `nginx -t`, reload/recreate и публичный smoke test
выполняются только назначенным оператором в последовательности §12.8.

Для будущего принятого release SHA проверка конфигурации из deploy checkout:

```sh
docker compose --env-file ../runtime/app.env -p vk-zhkh -f compose.yaml -f compose.vm.yaml config --quiet
```

`runtime/app.env` и реальные токены живут вне Git. `.env.example` содержит
только пример значений. Ниже записан исторический E1 dev результат; текущий
образ включает Tesseract и реальный engine, проверенный в E2/E3 CI.

## Проверка E1 в CI

[Actions run #6](https://github.com/FlynnTaggart076/VK_Hackathon/actions/runs/36318770691)
на integration SHA `0b0daaf994315c63de8f0db7d458de6411a31d81` завершился
успешно. В изолированном Compose project он выполнил `config --quiet`,
`up --build --detach`, проверил PostgreSQL major version 17, HTTP 200 для
`/team/zhkh/health/ready`, `/team/zhkh/` и `/team/zhkh/api/v1/meta`,
запущенный worker, `nginx -t`, загрузку JS asset и refresh вложенной SPA
страницы. Meta подтвердил явные `engine_stub=true` и `receipt_ocr=false`.
Эта проверка не является приёмкой VM или реального клиента MAX.

## E4 production topology

Корневой сертификат Минцифры для исходящего HTTPS worker закреплён в образе
backend: источник, два SHA-256 и правило обновления — в
[`infra/certs/README.md`](../infra/certs/README.md). `update-ca-certificates`
обновляет только trust store образа; проверка TLS и имени хоста остаётся включённой.

`/srv/team/vk-hackathon/deploy` — чистый checkout принятого SHA;
`/srv/team/vk-hackathon/runtime` — приватные `app.env`, backup и запись SHA.
Compose project `vk-zhkh`; публичный путь `/team/zhkh/`; общий вход остаётся
`10.203.77.10:8080` в отдельном проекте `/srv/team/web` (`team-web`).

| Сервис | Сети | Host ports |
|---|---|---|
| db, migrate, api | `private` (`internal: true`) | нет |
| worker | `private`, собственная `max_egress` для DNS/HTTPS MAX | нет |
| web | `private`, external `vk-zhkh-edge` с alias `vk-zhkh-web` | нет |
| общий Nginx | своя `default` и добавленная `vk-zhkh-edge` | существующий `10.203.77.10:8080:80` |

`max_egress` не подключается к API/БД и не публикует worker. Выход worker
нужен для `POST https://platform-api2.max.ru/messages`; MAX token не передаётся
в web. Участники VM с sudo/Docker могут читать окружения контейнеров:
`/srv/team` не является границей от операторов VM.

Внутренний Nginx приложения `infra/nginx/app-vm.conf` получает уже очищенный
префикс. Только `/api/`, `/integrations/` и `/health/` идут к API;
несуществующие `/assets/` отвечают 404, SPA fallback действует для UI.
Общий Nginx получает **только** две location из
`infra/nginx/team-web-route.conf.example`; сеть добавляется по
`infra/team-web-compose-network.yaml.example` в актуальные файлы VM, не
заменяя другие services, location, healthcheck, mounts или порты. Лимит
12 MiB в обоих Nginx покрывает файл 10 MiB с multipart обрамлением.

## Read-only preflight и условия записи

Сначала прочитать актуальные `/srv/team/README.md` и
`/srv/team/web/README.md`. SSH только с проверкой host key. Не выводить
чужие конфиги целиком, Docker environment или `.env`. Зафиксировать время,
HTTP коды и обезличенный инвентарь:

```sh
hostname; id; df -h /; free -h
ls -ld /srv/team /srv/team/web /srv/team/vk-hackathon
docker compose ls; docker ps --format '{{.Names}} {{.Status}}'
docker network ls --format '{{.Name}}'; docker volume ls --format '{{.Name}}'
curl -sS -o /dev/null -w 'team=%{http_code}\n' http://10.203.77.10:8080/team/
curl -sS -o /dev/null -w 'healthz=%{http_code}\n' http://10.203.77.10:8080/healthz
```

Проверить занятость `vk-zhkh`, `vk-zhkh-edge`, `vk-zhkh-web` и директорий.
При чужом объекте остановить только эту операцию и запросить новые имена у
координатора. До любой записи нужен новый accepted release SHA и реальные
MAX prerequisites; пустые/синтетические значения не годятся.

## Первый запуск из принятого SHA

Оператор создаёт `runtime` с режимом 0700, `app.env` с 0600 вне checkout.
Значения вводятся приватным редактором/каналом без echo в команде или логах:
`POSTGRES_PASSWORD` (URL-safe случайное значение), `MAX_BOT_TOKEN`,
`MAX_WEBHOOK_SECRET`, `MAX_WEB_APP` (username или max.ru ссылка бота с
привязанным mini-app). `DEMO_AUTH_ENABLED=false`, `ENGINE_MODE=real` и
`APP_MODE=production` принудительно задаёт `compose.vm.yaml`; демовход
недоступен. `runtime/app.env` не добавлять в Git или общий архив исходников.

До обновления общего входа сохранить закрытые копии только
`/srv/team/web/{compose.yaml,nginx.conf}` в `runtime/backup` с временем и
контрольными суммами. Проверить текущие файлы и соседние маршруты заново:
команда могла изменить их после preflight. Не перезаписывать их полным
примером из репозитория. Подготовить clean deploy checkout из GitHub в
`/srv/team/vk-hackathon/deploy`, проверить пустой `git status --porcelain` и
`git rev-parse HEAD == RELEASE_SHA`. При незакоммиченных/чужих файлах создать
отдельный checkout, ничего не сбрасывать. Только после проверки отсутствия
коллизий создать external сеть `vk-zhkh-edge`.

Из `deploy` выполнять последовательно; `RELEASE_SHA` берётся из задания
координатора, а не из подвижного `main`/`latest`:

```sh
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml config --quiet
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml up --build -d
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml ps
```

Не печатать `docker compose config` без `--quiet`: он разворачивает секреты.
`migrate` должен завершиться успешно, API стать healthy, worker продолжать
работать. Проверить PostgreSQL 17, версию миграции и HTTP внутри изолированной
сети без вывода окружения. DNS/HTTPS worker к `platform-api2.max.ru`
проверить без отправки боту; если TLS не доверяет endpoint, остановить MAX
регистрацию и исправить trust store только приложения по официальному
сертификату, не отключать TLS verification. [Официальный MAX API](https://dev.max.ru/docs-api)
указывает `platform-api2.max.ru` и необходимость доверенного сертификата
Минцифры (проверено 2026-09-27).

После готового web добавить сеть и route в **текущие** файлы общего проекта.
Из `/srv/team/web` по порядку: `docker compose config --quiet`, затем
`docker compose run --rm --no-deps -T nginx nginx -t`, затем при успехе
`docker compose up -d --force-recreate nginx` и `docker compose ps`.
Пересоздание Nginx кратко затрагивает весь командный вход; выполнять его
одному оператору. При ошибке сохранить чужие параллельные изменения и
откатить только своё добавление по закрытой копии. Не выполнять `down -v`,
global prune, перезапуск Docker, изменение внешнего HTTPS/SSH/DNS или
чужих каталогов.

## Приёмка маршрута и MAX

Из VM проверить `http://10.203.77.10:8080/team/zhkh/`, `/health/ready`,
`/api/v1/meta`, JS asset, вложенный SPA URL с refresh, 404 для отсутствующего
API/asset и 403 webhook без secret. Повторно проверить `/team/` и `/healthz`.
На машине разработчика отдельно проверить те же пути через
`https://flynntaggart075.asuscomm.com/team/zhkh/`; VM может не открыть свой
публичный адрес из-за сетевой петли. Сверить TLS и отсутствие ошибочного
корневого `/api/v1` в браузере. `docker compose ps` этого не доказывает.

Только после публичного HTTPS smoke настроить URL mini-app и webhook
`https://flynntaggart075.asuscomm.com/team/zhkh/integrations/max/webhook`
в MAX, используя тот же секрет из приватного `app.env`. Настройку подписки
и права бота подтвердить без вывода token/secret. С A пройти полный сценарий
в MAX Web и реальном мобильном MAX: подпись initData, загрузка, проверка,
сравнение, FAQ, копирование черновика, восстановление после закрытия.
Голос, транскрибация и отправка обращения отсутствуют. В отчёте разделить
internal VM, external HTTPS, live MAX и CI/synthetic.

## Обновление, backup и restore

Перед миграцией на следующий принятый SHA записать предыдущий SHA, сделать
`pg_dump -Fc` текущей БД в `runtime/backup` (режим 0600), проверить размер,
код завершения и `pg_restore --list`. Отдельно сохранить приватный source
documents volume: Git не содержит ни БД, ни загруженные документы. Дамп
внутри той же VM не защищает от потери VM; нужна отдельная защищённая копия
по правилам владельца. Дамп и исходники не публиковать в Git/CI logs.

Пример DB-only проверки из `deploy` с приватным `runtime/backup`:

```sh
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="../runtime/backup/zhkh-${stamp}.dump"
restore_db="zhkh_restore_${stamp}"
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml exec -T db \
  pg_dump -U zhkh -d zhkh -Fc > "$backup"
test -s "$backup"
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml exec -T db \
  pg_restore --list < "$backup" >/dev/null
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml exec -T db \
  createdb -U zhkh "$restore_db"
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml exec -T db \
  pg_restore -U zhkh -d "$restore_db" --no-owner --no-acl < "$backup"
docker compose --env-file ../runtime/app.env -p vk-zhkh \
  -f compose.yaml -f compose.vm.yaml exec -T db \
  psql -U zhkh -d "$restore_db" -Atqc 'SELECT version_num FROM alembic_version'
```

Не использовать проверочную БД в приложении; не выводить таблицы с данными.

Restore проверить в **новой отдельной тестовой БД**, не поверх `zhkh`:
создать уникальное имя `zhkh_restore_<timestamp>`, восстановить dump,
проверить `alembic_version` и контрольные количества таблиц без вывода
персональных строк. Тестовую БД удалять только по согласованному плану
очистки. Миграции E1→E3 добавляющие, но Alembic destructive downgrade
отключён. Откат кода к SHA с иной ожидаемой версией схемы может сломать
readiness; сначала проверить совместимость на восстановленной тестовой БД.
Рабочую БД не заменять старым dump после новых пользовательских записей без
отдельного решения владельца.

Останавливать/перезапускать только `vk-zhkh` сервисы. `down` сохраняет
volumes, но не служит backup; `down -v` запрещён.
