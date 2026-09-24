# 1. Настройте VPS и Coolify

В этой части вы подготовите Ubuntu VPS и откроете панель Coolify через HTTPS. Во второй — запустите приложение и настроите автоматический деплой.

Выполняйте шаги по порядку. Перед командами указано, где их вводить: **на компьютере**, **на VPS** или **в браузере**.

## Перед началом

Подготовьте:

- чистый VPS с **Ubuntu 24.04 LTS**, **2 vCPU**, **2 GiB RAM** и минимум **30 GiB свободного места**;
- SSH-доступ под `root` и доступ к консоли восстановления у провайдера;
- разрешённые у провайдера входящие TCP-порты **22, 80, 443**;
- компьютер с Windows PowerShell или Linux, командами `ssh` и `scp`;
- домен и доступ к его DNS-записям;
- исходники Solo VPS: URL репозитория и выбранный полный commit ID либо ZIP-архив для тестирования; одна и та же версия проекта должна остаться и на компьютере, и на VPS.

**PRE-ALPHA:** пока используйте тестовый VPS. [Репозиторий исходников](https://github.com/paracosm17/solo-vps) открыт, но проверенного релиза ещё нет. Запишите полный commit ID версии, выбранной для проверки.

Это поддерживаемый alpha-путь для одного VPS. В следующих шагах Make/Ansible запускаются на VPS, а Windows PowerShell служит для SSH/SCP с компьютера. Если на Windows нужны локальные Linux-инструменты проекта, используйте WSL. Точная версия релиза ещё не прошла проверки на чистом сервере и восстановления; эта инструкция пока не подтверждает готовность к production.

До начала выберите значения:

| Имя | Значение |
| --- | --- |
| `SERVER_IP` | IPv4 вашего VPS |
| `ADMIN_USER` | Имя Linux-администратора, которого создаст Solo VPS |
| `COOLIFY_DOMAIN` | Домен панели Coolify, например `coolify.example.com` |
| `REPOSITORY_URL` | `https://github.com/paracosm17/solo-vps.git` |
| `REVIEWED_REVISION` | Выбранный полный commit ID |

Каталог проекта остаётся `solo-vps`. В командах ниже переменные определяются перед использованием; заменяйте все значения `YOUR_...`. Внешнее хранилище резервных копий, Grafana и второй сервер здесь не нужны.

## 1. Подключитесь к чистому серверу

**На компьютере:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    ssh "root@$ServerIp"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ssh "root@${SERVER_IP}"
    ```

При первом подключении сравните отпечаток SSH-ключа сервера с консолью провайдера, подтвердите подключение и введите выданный провайдером пароль.

Вы попали в терминал Ubuntu. Следующие команды выполняются на VPS.

## 2. Установите необходимые пакеты и получите Solo VPS

**На VPS под root:**

```bash
apt-get update
apt-get install -y --no-install-recommends make git nano ca-certificates
```

Первая команда обновляет список пакетов. Вторая устанавливает инструменты для загрузки и настройки проекта.

Используйте путь Git с публичным URL репозитория и полным commit ID версии, выбранной для этой проверки. После выхода `v0.1.0` используйте полный commit ID, на который указывает тег. Путь с ZIP остаётся для отдельно предоставленного тестового архива.

=== "Git"

    **На VPS под root:**

    ```bash
    REPOSITORY_URL='https://github.com/paracosm17/solo-vps.git'
    REVIEWED_REVISION='YOUR_REVIEWED_FULL_COMMIT_ID'
    git clone "$REPOSITORY_URL" solo-vps
    cd solo-vps
    git checkout --detach "$REVIEWED_REVISION"
    ```

    Теперь вы в каталоге выбранной версии Solo VPS.

=== "ZIP"

    Для текущего тестирования используйте полученный `solo-vps.zip`, в котором файлы проекта лежат прямо в корне архива. Автоматический source ZIP GitHub содержит вложенный каталог и не подходит для этих команд; для публичного релиза используйте путь Git.

    **На VPS под root:**

    ```bash
    apt-get install -y --no-install-recommends unzip
    ```

    **На компьютере, в каталоге с архивом:**

    === "Windows PowerShell"

        ```powershell
        $ServerIp = 'YOUR_SERVER_IP'
        scp solo-vps.zip "root@${ServerIp}:/root/solo-vps.zip"
        ```

    === "Linux"

        ```bash
        SERVER_IP='YOUR_SERVER_IP'
        scp solo-vps.zip "root@${SERVER_IP}:/root/solo-vps.zip"
        ```

    **Вернитесь в терминал VPS под root:**

    ```bash
    unzip -q solo-vps.zip -d /root/solo-vps
    cd /root/solo-vps
    ```

    В этом каталоге находятся `Makefile`, `scripts` и `ansible`. Сохраните ту же копию исходников на компьютере: она понадобится во второй части.

Перед продолжением убедитесь, что **та же версия Solo VPS есть и на компьютере**. В следующих главах часть project helpers запускается локально. Если Git-копию пока клонировали только на VPS, клонируйте `REPOSITORY_URL` на компьютер и выберите тот же `REVIEWED_REVISION`. Если используете ZIP, оставьте этот же архив распакованным локально.

## 3. Подготовьте проект и заполните конфигурацию

**На VPS под root, в каталоге solo-vps:**

```bash
make setup
nano ~/.local/share/solo-vps/config/config.yml
```

`make setup` устанавливает инструменты автоматизации и создаёт конфигурацию. В открывшемся файле измените значения `server` и имя администратора:

```yaml
server:
  host: YOUR_SERVER_IP
  hostname: solo-vps-01
  timezone: UTC

admin:
  user: YOUR_ADMIN_USER
```

Это поля для редактирования, а не замена всего файла. Остальные настройки сохраните, в том числе поля SSH-ключей внутри `admin`.

`hostname` — короткое имя сервера. Часовой пояс `timezone` можно оставить `UTC`.

Сохраните файл: **Ctrl+O → Enter → Ctrl+X**.

## 4. Передайте публичный ключ администратора

С этим ключом вы будете входить с компьютера под пользователем из `admin.user`. Приватный ключ остаётся на компьютере.

**На компьютере, в новом терминале:**

=== "Windows PowerShell"

    Укажите путь к обычному ключу `id_ed25519`:

    ```powershell
    $SshDir = Join-Path $HOME '.ssh'
    $AdminKey = Join-Path $SshDir 'id_ed25519'
    ```

    Если SSH-ключа ещё нет, создайте его следующими командами. На запрос passphrase задайте пароль для своего личного ключа.

    ```powershell
    New-Item -ItemType Directory -Force -Path $SshDir | Out-Null
    ssh-keygen -t ed25519 -f $AdminKey -C 'Solo VPS admin'
    ```

    Если ключ уже существует, используйте его без повторного создания. Передайте публичную часть:

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    Get-Content -Raw -LiteralPath "$AdminKey.pub" | ssh "root@$ServerIp" 'cd ~/solo-vps && make human-admin-key-stdin'
    ```

=== "Linux"

    Если ключа `~/.ssh/id_ed25519` ещё нет, создайте его. На запрос passphrase задайте пароль для своего личного ключа.

    ```bash
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -C 'Solo VPS admin'
    ```

    Если ключ уже существует, используйте его без повторного создания. Передайте публичную часть:

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    cat ~/.ssh/id_ed25519.pub | ssh "root@${SERVER_IP}" 'cd ~/solo-vps && make human-admin-key-stdin'
    ```

Ожидайте `PASS human admin workstation key configuration` и `private_key_received: false`.

## 5. Настройте сервер

Не закрывайте терминал root. Убедитесь, что можете открыть консоль восстановления у провайдера.

**В оставленном терминале VPS под root:**

```bash
cd ~/solo-vps
make apply
```

Команда создаёт администратора, настраивает фаервол, автоматические обновления безопасности и Docker. Проверка результата уже включена.

Дождитесь `PASS Solo VPS host apply`.

## 6. Войдите под администратором

**На компьютере, в другом терминале:**

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

**В новой SSH-сессии на VPS:**

```bash
sudo -n id -u
```

Ожидаемый ответ — `0`. Значит, новый администратор может выполнять команды через sudo без пароля. Оставьте эту сессию открытой.

## 7. Защитите SSH и перейдите под администратора

После успешного входа под администратором и ответа `0` можно отключить вход по паролю и прямой вход под root. Консоль провайдера должна оставаться доступной.

**В оставленном терминале VPS под root:**

```bash
cd ~/solo-vps
SSH_HARDENING_CONFIRM=I_HAVE_VERIFIED_PROVIDER_RECOVERY SSH_HARDENING_ADMIN_LOGIN_CONFIRM=I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN make secure
```

Дождитесь `PASS Solo VPS SSH security transition`. Команда также подготавливает копию проекта для настроенного администратора.

**На компьютере, в новом терминале:**

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

**В этой новой SSH-сессии на VPS:**

```bash
cd ~/solo-vps
```

Дальнейшие серверные команды выполняйте здесь под настроенным администратором.

## 8. Установите Coolify

**На VPS под администратором, в каталоге solo-vps:**

```bash
make platform
make verify
```

Первая команда устанавливает Coolify, подготавливает сервер localhost и proxy, проверяет платформу. Вторая один раз проверяет весь настроенный хост.

Дождитесь `PASS Solo VPS application platform`, затем завершения проверки без ошибок. Повторно запускать установку не нужно.

## 9. Зарегистрируйтесь в Coolify

**На компьютере, в отдельном терминале:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 "${AdminUser}@${ServerIp}"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 "${ADMIN_USER}@${SERVER_IP}"
    ```

Оставьте терминал открытым. Отсутствие приглашения командной строки нормально: работает SSH-туннель. Локальный порт `18000` оставляет `8000` свободным для сайта документации.

**В браузере:**

1. Откройте [http://127.0.0.1:18000](http://127.0.0.1:18000).
2. Создайте первого администратора: имя, email и пароль.
3. На экране **Welcome to Coolify** выберите **Skip Setup**.
4. Откройте **Servers → localhost**.

Solo VPS уже создал этот сервер. Ожидайте **Server is reachable and validated** и **Proxy Running**. Используйте существующий `localhost`.

## 10. Настройте домен панели

**В DNS-панели вашего домена** создайте запись:

| Тип | Имя | Значение |
| --- | --- | --- |
| A | `coolify` | IPv4 VPS |

В примере получится `coolify.example.com`. В Cloudflare выберите **DNS only**. Добавляйте AAAA-запись только при настроенном рабочем IPv6.

**В Coolify:**

1. Нажмите **Settings со значком шестерёнки внизу левого меню**.
2. Откройте **Configuration → General**.
3. В поле **URL** укажите `https://coolify.example.com`, заменив домен своим.
4. Нажмите **Save**.
5. Откройте этот HTTPS-адрес в новой вкладке и войдите.

Это настройки всей панели. Поле **Servers → localhost → IP Address/Domain** отвечает за SSH-подключение к серверу; в нём остаётся `host.docker.internal`.

Панель должна открыться по HTTPS с действующим сертификатом. Используйте домен для повседневного доступа. Туннель можно закрыть сочетанием **Ctrl+C** в его терминале.

## Готово: сервер и панель работают

У вас есть настроенный администратор, защищённый SSH, Docker и Coolify через HTTPS.

**Продолжайте: [2. Запустите приложение и настройте CI/CD](operations/first-app.md).** Там собраны все обязательные шаги для приложения, автоматического деплоя, переменных окружения и логов.
