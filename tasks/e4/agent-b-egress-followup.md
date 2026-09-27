# E4 B: исходящий доступ worker к MAX

В `compose.yaml` worker подключён только к сети `private` с `internal: true`. Это защищает API/БД, но не даёт worker исходящий HTTPS к `platform-api2.max.ru` для ответа бота. Отсутствие живого MAX токена не позволяет списать риск на сервис MAX; это дефект локальной сетевой схемы до deploy.

В своей E4 ветке добавь только worker отдельную сеть исходящего доступа без published ports; API/БД остаются в private, web — private плюс `vk-zhkh-edge`. Проверь результирующий Compose, отсутствие внешних портов worker/API/БД, доступ worker к DNS/HTTPS в изолированном тесте без реальной отправки боту. Документируй разграничение в `docs/deployment.md`, не меняй общий Nginx или соседние сети ради этого теста.

Исходный E3 release SHA `d223c4e49a12c4ebc5d98c3c8da8fc6c0202e16f` принят по E3, но **не допускается к production MAX deploy до исправления исходящего пути**. B публикует code SHA и отдельный отчёт; координатор проверяет и назначает новый accepted release SHA для VM. Без production credentials и связанного mini-app deploy остаётся заблокированным; секреты вне Git.
