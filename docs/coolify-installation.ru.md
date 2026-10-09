# Установка и доступ к Coolify

Solo VPS устанавливает Coolify, не передавая upstream installer управление SSH, Docker или firewall configuration. Хост остаётся под управлением Ansible; Coolify отвечает за application/runtime state в `/data/coolify`.

## Текущая зафиксированная платформа

```text
Coolify:           {{ solo_vps_coolify_target }}
image:             docker.io/coollabsio/coolify:{{ solo_vps_coolify_target }}
Docker support:    29.x
management bind:   127.0.0.1
management ports:  8000, 6001, 6002
data root:          /data/coolify
```

Версия и first-install artifacts — зависимости проекта, а не per-host configuration knobs.

## До установки

Сначала завершите этапы host и SSH:

```bash
make apply
make secure
```

Переподключитесь как `admin.user`, затем выполните:

```bash
make doctor
make verify
make audit
```

Fresh-install path ожидает, что `/data/coolify` не используется посторонней установкой Coolify.

## Установите платформу

**Где: управляемый VPS/контроллер под `admin.user`**

```bash
make platform
```

На чистом VPS `make platform` проверяет готовность, устанавливает зафиксированный release и проверяет первоначальный запуск и закрытые порты. Создайте первый аккаунт, настройте HTTPS-панель и Sentinel перед `make verify-coolify`. На уже управляемом VPS `make platform` также выполняет полную проверку.

Отдельный proxy Traefik публикует только **TCP 80/443**. Solo VPS сохраняет ограничения портов через штатную конфигурацию proxy Coolify до проверки установки. Host-порт 8080 и UDP 443 не публикуются; HTTP/3 не входит в базовый сетевой профиль. Маршрутизацией, сертификатами и основным конфигом proxy продолжает управлять Coolify.

На существующей установке `make platform` также исправляет работающий proxy с лишними публикациями портов. Proxy пересоздаётся, поэтому HTTP/HTTPS кратковременно прерывается. Новый образ proxy не скачивается, контейнеры приложений не перезапускаются, credentials Coolify не пересоздаются. Если сохранённый Compose-конфиг изменит образ или потеряет дополнительные сети приложений, автоматическое пересоздание остановится для проверки; после проверки конфигурации перезапустите proxy через Coolify UI и повторите verification.

Readiness gate проверяет текущую admin identity, поддерживаемые версии Docker/Compose, host Docker config, минимальные CPU/RAM/disk, доступность management ports и существующее состояние Coolify.

## Чем владеет installer

Solo VPS создаёт зафиксированный filesystem/runtime skeleton Coolify, генерирует first-install secrets без вывода в терминал, создаёт localhost SSH identity для Coolify, запускает pinned Compose model и записывает managed marker только после успешных health и exposure checks.

Management/realtime publications намеренно остаются на loopback:

```text
127.0.0.1:8000 → Coolify web/API
127.0.0.1:6001 → realtime service
127.0.0.1:6002 → realtime service
```

Не добавляйте публичные firewall rules для этих портов.

## Создайте первый аккаунт Coolify

**Где: рабочая станция**

Откройте SSH tunnel из PowerShell или терминала Linux/macOS. Локальный порт 18000 оставляет порт 8000 свободным для сайта документации:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 <admin.user>@<server>
```

Затем откройте:

```text
http://127.0.0.1:18000
```

Оставьте терминал туннеля открытым: `-N` не запускает удалённую оболочку, поэтому ожидание без приглашения — нормально. Если SSH сообщает об ошибке перенаправления, устраните конфликт локального порта до открытия страницы. Создайте первый аккаунт через этот приватный path.

После настройки HTTPS-домена панели укажите этот адрес в **Servers → `server.hostname` → Sentinel → Configuration → Coolify URL**, оставьте debug выключенным, включите Sentinel и выполните Sync. Дождитесь **Sentinel In Sync**. Raw management ports и порт Sentinel `8888` остаются приватными. См. [домен панели Coolify и browser terminal](operations/coolify-dashboard-domain.md).

## Проверьте Coolify

**Где: VPS/контроллер**

```bash
make verify-coolify
make audit
```

Запускайте проверку после настройки Sentinel. Она проверяет managed marker, зафиксированные образы Coolify и Sentinel, health endpoints, HTTPS-настройку Sentinel, localhost SSH integration, ограниченные права на файлы, Docker daemon ownership и закрытые management ports, не печатая секретные значения. В панели отдельно подтвердите **Sentinel In Sync**.

## Второй idempotent run

После того как установка отмечена как Solo VPS-managed, повторный:

```bash
make platform
```

reconciles только поддерживаемое integration state и проверяет его. Он не должен заново генерировать first-install secrets и не рассматривает rerun как upgrade.


## Если proxy/resource paths дают permission errors

Не выполняйте рекурсивный `chmod`/`chown` для `/data/coolify` и не исправляйте один resource UUID вручную.

Повторно приведите поддерживаемую интеграцию к desired state:

```bash
make platform
make verify-coolify
```

Если ошибка относится к локальному backup и содержит `/data/coolify/backups/...: Permission denied`, тот же `make platform`/`make verify-coolify` восстанавливает отдельную private write+traverse boundary для non-root backup jobs. Не расширяйте права всего `/data/coolify`.

Если ошибка остаётся, сохраните точный Coolify deployment/proxy/backup log и используйте его как воспроизводимый bug report.

## Прерванная первая установка

Прерванный unmarked first install — recovery case, а не обычный rerun. Используйте явный проверенный recovery path из command reference; никогда не принимайте неизвестное состояние `/data/coolify` автоматически.

## Обновления

Обычный `make platform` не обновляет Coolify. Поддерживаемый alpha lifecycle: previous-supported `{{ solo_vps_coolify_origin }}` → current-supported `{{ solo_vps_coolify_target }}`; safety-gated procedure описана в [руководстве по обновлению](upgrades.md).

## Связанные страницы

- [Первое приложение](operations/first-app.md)
- [Ежедневная работа](operations/operator-ui.md)
- [Архитектура](architecture.md)

При повторном `make platform` readiness первой установки пропускается для готовой платформы. Своя прерванная установка с marker `.solo-vps-installing` продолжается автоматически: существующие секреты и SSH-ключ сохраняются. Для старой незавершённой установки используется ограниченный recovery. Если marker отсутствует или identity не совпадает, исследуйте исходную ревизию/конфиг; чужой `/data/coolify` не принимается. Прерванное обновление требует отдельного `make coolify-upgrade-resume`.
