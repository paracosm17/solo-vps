# 2. Запустите приложение и настройте CI/CD

Продолжаем [первую часть](../quick-start.md): VPS настроен, панель Coolify открывается через HTTPS. Теперь создадим тестовое приложение, запустим его и настроим автоматический деплой из GitHub. Затем изменим переменную окружения и посмотрим логи.

Все обязательные действия находятся на этой странице. Справочник понадобится только для дополнительных настроек после завершения.

## Перед началом

На компьютере нужны Git, Python 3.12 или новее и та же копия Solo VPS, которую вы использовали на сервере. Для ZIP распакуйте исходники в отдельный каталог `solo-vps`. Команды запускаются из каталога с `Makefile` и `scripts`.

Нужен аккаунт GitHub с настроенным доступом для `git push`. В примере используем новый публичный репозиторий и публичный образ: без приватного кода, настоящих секретов и дополнительных паролей реестра на VPS.

| Имя | Значение |
| --- | --- |
| `SERVER_IP` | IPv4 VPS из первой части |
| `ADMIN_USER` | Значение `admin.user` из первой части |
| `APP_DOMAIN` | Домен тестового приложения, например `app.example.com` |
| `GITHUB_OWNER` | Ваш логин или организация GitHub |
| `APPLICATION_REPOSITORY_URL` | URL нового репозитория, скопированный с GitHub |

Приложение называем `solo-vps-demo`. Его каталог будет рядом с `solo-vps`, а не внутри него. База данных для примера не нужна.

## 1. Создайте репозиторий на GitHub

**В браузере, на GitHub:**

1. Нажмите **+ → New repository**.
2. В **Repository name** укажите `solo-vps-demo`.
3. Выберите **Public**.
4. Оставьте создание README, `.gitignore` и лицензии выключенным.
5. Нажмите **Create repository**.
6. На странице пустого репозитория скопируйте его HTTPS или SSH URL — тот, для которого у вас настроен `git push`.

Оставьте эту вкладку открытой. Используйте новый пустой репозиторий: правила и файлы старого проекта могут помешать первому push.

## 2. Создайте приложение на компьютере

**На компьютере, откройте терминал в каталоге solo-vps:**

=== "Windows PowerShell"

    ```powershell
    python scripts/create_app.py ../solo-vps-demo
    ```

=== "Linux"

    ```bash
    python3 scripts/create_app.py ../solo-vps-demo
    ```

Дождитесь `Created application:` с путём нового каталога. Только после этого переходите дальше. Если каталог уже существует, helper ничего не перезаписывает: выберите другое свободное имя и используйте его в последующих шагах.

**В том же терминале компьютера, PowerShell или Linux:**

```bash
cd ../solo-vps-demo
git init -b main
git add .
git commit -m "Create demo application"
```

Теперь в отдельном репозитории есть приложение, Dockerfile и готовый workflow `.github/workflows/app.yml`.

## 3. Отправьте приложение и дождитесь первого образа

**На компьютере, в каталоге solo-vps-demo:**

```bash
APPLICATION_REPOSITORY_URL='YOUR_APPLICATION_REPOSITORY_URL'
git remote add origin "$APPLICATION_REPOSITORY_URL"
git push -u origin main
```

**На GitHub, в репозитории solo-vps-demo → Actions:**

1. Откройте запуск **Hello app CI** для первого коммита.
2. Дождитесь зелёных **Application tests**, **Application migration preflight**, **Publish main image** и **Verify published image by digest**.
3. В summary запуска скопируйте значение **Published immutable image**. Оно выглядит так:

```text
ghcr.io/<github-owner>/solo-vps-demo@sha256:<64-hex-digest>
```

Это точная ссылка на собранный образ. Сохраните её для следующего шага. **Build pull request image** и **Deploy immutable image to Coolify** сейчас пропущены — это ожидаемо. Переменную `SOLO_VPS_DEPLOY_ENABLED` пока не создавайте.

**На GitHub, в профиле владельца репозитория → Packages:**

1. Откройте пакет `solo-vps-demo`, затем **Package settings**.
2. В **Danger Zone → Change visibility** выберите **Public** и подтвердите изменение видимости именно этого демонстрационного пакета.

Если пакет уже Public, ничего менять не нужно. Видимость репозитория и пакета настраивается отдельно.

## 4. Подготовьте домен приложения

**В DNS-панели вашего домена** создайте запись:

| Тип | Имя | Значение |
| --- | --- | --- |
| A | `app` | IPv4 VPS |

В примере получится `app.example.com`. В Cloudflare выберите **DNS only**. AAAA-запись нужна только при настроенном рабочем IPv6.

## 5. Создайте приложение в Coolify

**В Coolify:**

1. Откройте **Projects** и создайте проект `solo-vps-demo`.
2. Откройте его окружение `production`.
3. Нажмите **+ New Resource → Docker Image** и выберите существующий сервер **localhost**.
4. В **Image Name** вставьте только имя образа: `ghcr.io/<github-owner>/solo-vps-demo`, подставив своего владельца.
5. Завершите создание ресурса.

**В созданном приложении → Configuration → General** задайте:

| Поле | Значение |
| --- | --- |
| Name | `solo-vps-demo` |
| Docker Image | Имя из опубликованной ссылки до `@`: `ghcr.io/<github-owner>/solo-vps-demo` |
| Docker Image Tag or Hash | `sha256-`, затем все 64 символа после `sha256:` в опубликованной ссылке |
| Domains | `https://app.example.com`, замените домен своим |
| Ports Exposes | `8080` |
| Ports Mappings | Оставьте пустым |
| Custom Docker Options | Оставьте пустым |

В поле **Docker Image Tag or Hash** нужен **дефис** после `sha256`, а не двоеточие. Настраивайте эти два поля **после создания ресурса**: форма создания Coolify 4.1.2 может неверно разобрать целую ссылку с digest.

Дополнительный **Health Check** Coolify оставьте выключенным: Dockerfile уже проверяет `/healthz`. Порт `8080` используется внутри контейнера; приложение будет доступно через HTTPS без `8080:8080` в Ports Mappings.

Нажмите **Save**.

## 6. Выполните первый деплой

**В Coolify, в приложении:**

1. Нажмите **Deploy**.
2. Откройте **Deployments** и лог текущего запуска.
3. Дождитесь успешного завершения и состояния **Running / Healthy**.

**В браузере** откройте свой домен:

- `https://app.example.com/` — JSON с `version: "1"` и `message: "Hello from Solo VPS"`;
- `https://app.example.com/healthz` — `{"status":"ok"}`.

В приложении Coolify откройте **Logs**: там должны появиться строки этих HTTP-запросов.

Продолжайте после успешного первого деплоя. Он нужен, чтобы CI мог обновлять уже работающее приложение.

## 7. Создайте отдельный SSH-ключ для CI {#ci-key}

**На компьютере, в новом терминале:**

Этот ключ будет использовать GitHub Actions. Ваш личный ключ администратора для CI не нужен. Если такой CI-ключ уже создан, пропустите `ssh-keygen` и используйте существующий. Не подтверждайте перезапись ключа.

=== "Windows PowerShell"

    ```powershell
    $SshDir = Join-Path $HOME '.ssh'
    $CiKey = Join-Path $SshDir 'solo-vps-demo-ci'
    New-Item -ItemType Directory -Force -Path $SshDir | Out-Null
    ssh-keygen -t ed25519 -f $CiKey -C 'solo-vps-demo CI'
    ```

    На оба запроса passphrase нажмите **Enter**, оставив пароль пустым: CI работает без интерактивного ввода.

    Передайте на VPS только публичную часть:

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    scp "$CiKey.pub" "${AdminUser}@${ServerIp}:/home/${AdminUser}/.ssh/solo-vps-demo-ci.pub"
    ```

=== "Linux"

    ```bash
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    ssh-keygen -t ed25519 -f ~/.ssh/solo-vps-demo-ci -C 'solo-vps-demo CI'
    ```

    На оба запроса passphrase нажмите **Enter**, оставив пароль пустым: CI работает без интерактивного ввода.

    Передайте на VPS только публичную часть:

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    scp ~/.ssh/solo-vps-demo-ci.pub "${ADMIN_USER}@${SERVER_IP}:/home/${ADMIN_USER}/.ssh/solo-vps-demo-ci.pub"
    ```

Приватный файл без `.pub` остаётся на компьютере.

## 8. Создайте ограниченного CI-пользователя на VPS

**На компьютере, подключитесь к VPS:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    ssh "${AdminUser}@${ServerIp}"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    ssh "${ADMIN_USER}@${SERVER_IP}"
    ```

**В этой SSH-сессии на VPS под администратором:**

```bash
cd ~/solo-vps
nano ~/.local/share/solo-vps/config/config.yml
```

Добавьте в конец файла, без отступа перед `ci_deploy`:

```yaml
ci_deploy:
  ssh_public_key_file: ~/.ssh/solo-vps-demo-ci.pub
```

Если такой раздел уже есть, измените его поле вместо создания второго. Закомментированный пример начинается с `#` и не является активной настройкой. Остальной файл сохраните. В nano: **Ctrl+O → Enter → Ctrl+X**.

**На VPS под администратором, в том же каталоге:**

```bash
SERVER_IP='YOUR_SERVER_IP'
make plan-ci-deploy-transport CI_DEPLOY_SERVER_HOST="$SERVER_IP" CI_DEPLOY_PUBLIC_KEY_FILE="$HOME/.ssh/solo-vps-demo-ci.pub"
```

Проверьте в плане: ваш `server_host`, пользователь `solo-vps-ci`, адрес API `127.0.0.1:8000`. Теперь примените его:

```bash
CI_DEPLOY_TRANSPORT_CONFIRM=I_HAVE_REVIEWED_THE_RESTRICTED_CI_SSH_TRANSPORT make ci-deploy-transport
```

Ожидайте итог `failed=0`, `unreachable=0` и сообщение, что CI identity ограничена forwarding к `127.0.0.1:8000`. Проверка уже включена в команду.

Создан пользователь `solo-vps-ci` без shell, sudo и доступа к Docker. Он позволяет CI обращаться к Coolify API через SSH-туннель. Настроенный администратор остаётся обычным доступом для человека.

## 9. Подготовьте два публичных значения для GitHub

**В открытой доверенной SSH-сессии на VPS под администратором:**

Сейчас получите два значения для шага 11. Оставьте вывод в этом терминале или сохраните значения с их именами в заметку: через несколько минут вставите их в GitHub в том же порядке.

**Первое — `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`, отпечаток CI-ключа:**

```bash
ssh-keygen -lf ~/.ssh/solo-vps-demo-ci.pub -E sha256 | awk '{print $2}'
```

Команда выводит только готовое значение `SHA256:...`. Скопируйте его **целиком, вместе с `SHA256:`**. Этот префикс обязателен; одни символы после двоеточия не подойдут. Отдельное число `256` в полном выводе `ssh-keygen` — длина ключа, его эта команда уже убрала.

**Второе — `SOLO_VPS_SSH_KNOWN_HOSTS`, строка ключа самого сервера:**

```bash
SERVER_IP='YOUR_SERVER_IP'
awk -v host="$SERVER_IP" '{print host " " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

Скопируйте всю одну строку `IP ssh-ed25519 ...`. Это значение для `SOLO_VPS_SSH_KNOWN_HOSTS`. IP должен совпадать с `SOLO_VPS_DEPLOY_HOST`.

Первое значение проверяет ключ, с которым входит CI. Второе позволяет CI узнать ваш сервер. Оба публичные; приватный серверный ключ не нужен.

## 10. Создайте API-токен в Coolify

**В Coolify под администратором:**

1. Откройте **Settings** в левом меню, затем **Configuration → Advanced**.
2. Включите **API Access** и сохраните изменение.
3. В левом меню нажмите **Keys & Tokens**, затем вкладку **API Tokens**. Заголовок открывшейся страницы — **Security**.
4. В **Description** укажите `solo-vps-demo CI`.
5. Оставьте срок **30 days**. До его окончания нужно будет создать новый токен и обновить secret в GitHub.
6. Сначала отметьте **deploy**, затем **write** и **read**. В строке **Permissions** должны быть все три права. `root` и `read:sensitive` оставьте выключенными.
7. Нажмите **Create** и сразу скопируйте токен в свой менеджер паролей: повторно он не показывается.

Токен действует в рамках текущей команды Coolify, а не только одного приложения. Для демонстрации используйте команду, в которой создан `solo-vps-demo`.

Откройте приложение и скопируйте его UUID из адресной строки — часть после `/application/` и до следующего `/` или `?`, если они есть. Не берите UUID проекта, окружения или сервера. Это значение для `COOLIFY_RESOURCE_UUID`.

## 11. Заполните окружение production в GitHub {#github-production}

**На GitHub, в репозитории solo-vps-demo:**

1. Откройте **Settings → Environments**.
2. Нажмите **New environment**, введите `production`, затем **Configure environment**. Если оно уже существует, откройте его.
3. В **Environment secrets → Add Secret** создайте два секрета:

| Name | Secret |
| --- | --- |
| `SOLO_VPS_DEPLOY_SSH_KEY` | Весь приватный CI-ключ, включая строки `BEGIN OPENSSH PRIVATE KEY` и `END OPENSSH PRIVATE KEY` |
| `COOLIFY_API_TOKEN` | Токен из предыдущего шага |

Чтобы скопировать приватный **CI-ключ**, выполните **на компьютере**:

Если ранее создали ключ в другом каталоге, используйте его фактический путь: в PowerShell задайте его в `$CiKey`, в Linux подставьте в `cat`. Новый ключ создавать не нужно.

=== "Windows PowerShell"

    ```powershell
    $CiKey = Join-Path (Join-Path $HOME '.ssh') 'solo-vps-demo-ci'
    Get-Content -Raw -LiteralPath $CiKey | Set-Clipboard
    ```

    Вставьте содержимое буфера в `SOLO_VPS_DEPLOY_SSH_KEY` и сохраните secret.

=== "Linux"

    ```bash
    cat ~/.ssh/solo-vps-demo-ci
    ```

    Скопируйте весь вывод в `SOLO_VPS_DEPLOY_SSH_KEY` и сохраните secret. Это приватный ключ: не отправляйте вывод в чат и не сохраняйте его в репозиторий.

**На той же странице GitHub → production**, в **Environment variables → Add Variable** создайте:

| Name | Value |
| --- | --- |
| `SOLO_VPS_DEPLOY_HOST` | Только значение `SERVER_IP`, без пользователя, протокола и порта |
| `SOLO_VPS_DEPLOY_SSH_FINGERPRINT` | Первое значение из шага 9: отпечаток CI-ключа целиком, **включая `SHA256:`** |
| `SOLO_VPS_SSH_KNOWN_HOSTS` | Второе значение из шага 9: полная строка `IP ssh-ed25519 ...` |
| `COOLIFY_RESOURCE_UUID` | UUID приложения из шага 10 |

Результат: в `production` есть **два secrets и четыре variables**.

## 12. Включите автоматический деплой

**На GitHub, в репозитории solo-vps-demo:**

1. Откройте **Settings → Secrets and variables → Actions → Variables**.
2. Нажмите **New repository variable**.
3. В **Name** укажите `SOLO_VPS_DEPLOY_ENABLED`, в **Value** — `true`.
4. Нажмите **Add variable**.

Эта единственная переменная должна быть **на уровне репозитория**, а не внутри `production`: она включает deploy job. Само сохранение переменной не запускает деплой. Его проверим следующим изменением приложения.

## 13. Выпустите вторую версию через pull request

**На компьютере, в терминале каталога solo-vps-demo:**

```bash
git switch -c demo-version-2
```

В редакторе откройте `app.py`. Замените только эту строку:

```python
APP_VERSION: Final = "1"
```

на:

```python
APP_VERSION: Final = "2"
```

Сохраните файл. **В том же терминале компьютера:**

```bash
git add app.py
git commit -m "Show application version 2"
git push -u origin demo-version-2
```

**На GitHub:**

1. Откройте **Pull requests → New pull request**.
2. Выберите base `main`, compare `demo-version-2` и нажмите **Create pull request**.
3. Дождитесь зелёных тестов, migration preflight и **Build pull request image**. PR ещё не публикует и не деплоит приложение.
4. Нажмите **Merge pull request → Confirm merge**.
5. Откройте **Actions** и запуск для нового коммита в `main`.
6. Дождитесь успешных публикации, проверки digest и **Deploy immutable image to Coolify**. Если для окружения настроено согласование, сначала подтвердите ожидающий deployment.

**В браузере** обновите `https://app.example.com/`. Теперь должно быть `version: "2"`. В **Coolify → приложение → Deployments** появится новый деплой.

Это и есть рабочий CI/CD: изменение в GitHub прошло проверки и попало на VPS автоматически. Во время работающего deploy job не запускайте ручной Deploy этого же приложения.

## 14. Измените переменную окружения

**В Coolify → приложение → Environment Variables:**

1. В разделе переменных обычного приложения, не Preview Deployments, нажмите **+ Add**.
2. В **Name** укажите `APP_MESSAGE`.
3. В **Value** укажите `Hello from Coolify`.
4. Включите **Available at Runtime**, выключите **Available at Buildtime**.
5. Нажмите **Save**.
6. Когда CI уже завершился, нажмите **Redeploy** приложения и дождитесь успешного запуска.

Обновите `https://app.example.com/`. Версия останется `2`, а сообщение станет `Hello from Coolify`. Пересобирать образ или менять Git для этого не требуется.

Настоящие пароли и API-токены приложения добавляйте здесь таким же способом, только для runtime. Демонстрационная `APP_MESSAGE` не секрет: приложение специально выводит её в ответе. Секреты нельзя выводить в HTTP-ответах или логах, добавлять в `app.py`, Dockerfile либо коммитить в Git.

GitHub хранит два секрета **для деплоя**. Coolify хранит переменные и секреты **работающего приложения**.

## 15. Найдите логи и результат деплоя

**В браузере** ещё раз откройте `/` и `/healthz` приложения.

**В Coolify → приложение → Logs** найдите свежие строки `GET /` и `GET /healthz` с кодом `200`. Здесь вывод работающего приложения.

| Что произошло | Где смотреть |
| --- | --- |
| Не прошли тесты, сборка или автоматический деплой | GitHub → репозиторий → Actions → запуск → красный job |
| Контейнер не запустился | Coolify → приложение → Deployments → последний деплой |
| Ошибка в работающем приложении | Coolify → приложение → Logs |
| Нужно изменить ENV или секрет | Coolify → приложение → Environment Variables |

## Готово: базовая настройка завершена

После успешного прохождения у вас есть настроенный VPS, Coolify и приложение через HTTPS, CI/CD из GitHub, отдельный доступ для деплоя, runtime-переменные и место для секретов, живые логи приложения.

Можно переходить к собственному приложению. Демо не содержит БД, а просмотр живых логов не настраивает их долговременное хранение.

Продолжение — [После базовой настройки](after-basic-setup.md): история логов, резервные копии и уведомления. Если хотите сначала понять, как работать с готовой платформой, откройте [Ежедневную работу](operator-ui.md).

Дальнейшие задачи выбирайте по необходимости:

- [Настройки и секреты приложения](application-config-and-secrets.md) — дополнительные runtime-настройки.
- [Внешние уведомления о недоступности](external-uptime.md) — узнавать о сбоях независимо от VPS.
- [Внешние резервные копии](../backups-restic.md) — настройте до размещения ценных данных.
- [Резервные копии и восстановление PostgreSQL](../database-backups.md) — когда появится база данных.
- [Сохранённые логи и метрики](observability.md) — когда понадобится история.

## Если шаг не завершился

### Deploy упал из-за fingerprint после merge

Если после успешной публикации образа Deploy остановился до SSH-подключения, проверьте `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`. В старом workflow неправильный формат мог дать только `Process completed with exit code 1` сразу после `PASS release revision`; сам по себе этот код не определяет причину.

1. Откройте **GitHub → репозиторий → Settings → Environments → production → Environment variables**.
2. Измените `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`: вставьте первое значение из шага 9 целиком, с **`SHA256:`**, и сохраните.
3. Откройте **Actions → упавший запуск после merge → Re-run jobs → Re-run failed jobs**. Новый PR и повторная сборка образа для исправления переменной не нужны.
4. Дождитесь успешного Deploy, затем обновите адрес приложения: ожидается `version: "2"`. После этого продолжайте с шага 14.

Повторный запуск относится к исходному коммиту. Если `main` уже продвинулся, проверка актуальности пропустит старый деплой — используйте запуск текущего `main`. Если ошибка другая или деплой уже начался в Coolify, сначала прочитайте его лог.

| Симптом | Что проверить |
| --- | --- |
| Starter пишет, что каталог уже существует | Не переходите в него вслепую. Используйте новое имя каталога и повторите создание |
| Первый push отклонён | URL должен вести в новый пустой репозиторий; проверьте доступ Git и правила репозитория |
| Coolify не скачивает образ | Пакет GHCR должен быть Public; проверьте имя и `sha256-…` после создания ресурса |
| Домен не открывается | A-запись, отсутствие ошибочной AAAA, порты 80/443 у провайдера, Proxy Running и лог деплоя |
| Deploy job пропущен после merge | `SOLO_VPS_DEPLOY_ENABLED=true` нужна в repository variables; смотрите запуск `main`, не PR |
| SSH-проверка CI не прошла | Secret должен содержать приватный CI-ключ; fingerprint — от него; known_hosts — от сервера с тем же IP |
| API отвечает 401/403 | API Access, срок токена и все три права: `read`, `write`, `deploy` |
| CI сообщает timeout или неизвестный статус | Сначала откройте Coolify Deployments: исходный деплой ещё может идти. Порядок дальнейших действий — в [инструкции по откату](deployment-rollback.md) |

Названия UI сверены с Coolify 4.1.2. Для уточнений: [API-токены Coolify](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Livewire/Security/ApiTokens.php), [окружения GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
