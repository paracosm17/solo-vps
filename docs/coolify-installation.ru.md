# Установка и доступ к Coolify

Solo VPS устанавливает Coolify, не передавая upstream installer управление SSH, Docker или firewall configuration. Хост остаётся под управлением Ansible; Coolify отвечает за application/runtime state в `/data/coolify`.

## Текущая зафиксированная платформа

```text
Coolify:           4.1.2
image:             ghcr.io/coollabsio/coolify:4.1.2
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

`make platform` выполняет readiness checks, устанавливает/reconciles зафиксированный release Coolify и запускает `make verify-coolify`.

Отдельный proxy Traefik публикует только **TCP 80/443**. Solo VPS устанавливает постоянный Compose override портов до первого запуска Coolify. Host-порт 8080 и UDP 443 не публикуются; HTTP/3 не входит в базовый сетевой профиль. Маршрутизацией, сертификатами и основным конфигом proxy продолжает управлять Coolify.

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

Когда позже появится обычный HTTPS domain панели, raw management ports всё равно должны оставаться приватными. См. [домен панели Coolify и browser terminal](operations/coolify-dashboard-domain.md).

## Проверьте Coolify

**Где: VPS/контроллер**

```bash
make verify-coolify
make audit
```

Verification проверяет managed marker, pinned image/artifacts, health endpoints, localhost SSH integration, bounded filesystem permissions, Docker daemon ownership boundary и loopback-only publications, не печатая секретные значения.

## Второй idempotent run

После того как установка отмечена как Solo VPS-managed, повторный:

```bash
make platform
```

reconciles только поддерживаемое integration state и проверяет его. Он не должен заново генерировать first-install secrets и не рассматривает rerun как upgrade.

Реальный повторный `platform` после исправления портов proxy прошёл без изменений. Полный пользовательский проход и первая установка с уже включённым исправлением остаются release-проверками.

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

Обычный `make platform` не обновляет Coolify. Поддерживаемый alpha lifecycle сейчас различает только `4.1.1` и `4.1.2`; safety-gated procedure описана в [руководстве по обновлению](upgrades.md).

## Связанные страницы

- [Первое приложение](operations/first-app.md)
- [Ежедневная работа](operations/operator-ui.md)
- [Архитектура](architecture.md)

При повторном `make platform` readiness первой установки пропускается для готовой платформы. Своя прерванная установка с marker `.solo-vps-installing` продолжается автоматически: существующие секреты и SSH-ключ сохраняются. Для старой незавершённой установки используется ограниченный recovery. Если marker отсутствует или identity не совпадает, исследуйте исходную ревизию/конфиг; чужой `/data/coolify` не принимается. Прерванное обновление требует отдельного `make coolify-upgrade-resume`.

При повторном `make platform` readiness первой установки пропускается для готовой платформы. Своя прерванная установка с marker `.solo-vps-installing` продолжается автоматически: существующие секреты и SSH-ключ сохраняются. Для старой незавершённой установки используется ограниченный recovery. Если marker отсутствует или identity не совпадает, исследуйте исходную ревизию/конфиг; чужой `/data/coolify` не принимается. Прерванное обновление требует отдельного `make coolify-upgrade-resume`.
