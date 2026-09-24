# Справочник команд

Solo VPS намеренно показывает небольшой normal lifecycle. Начинайте с него; subsystem targets используйте только для diagnostics, recovery или проверенной advanced operation.

> Выполните `make help` для поддерживаемого operator surface, `make help-ops` для operational commands и `make help-all` только когда нужен полный implementation catalog.

## Обычный lifecycle

| Команда | Меняет state? | Назначение |
| --- | --- | --- |
| `make setup` | workstation/controller | Подготовить prerequisites, persistent state, SSH identity и pinned QA tooling |
| `make apply` | **да — VPS** | Применить/продолжить host baseline, проверить его и переключить inventory на managed admin |
| `make secure` | **да — access-critical** | Активировать SSH hardening после доказательства provider recovery и свежего workstation login |
| `make platform` | **да — VPS** | Установить/проверить pinned Coolify platform |
| `make verify` | нет | Выполнить read-only local/remote verification и показать состояние платформы |

Предполагаемый порядок:

```text
setup -> apply -> secure -> platform -> verify
```

Для первой установки используйте [Быстрый старт](quick-start.md), а не эту reference page.

## Setup и access helpers

### `make paths`

Показывает source checkout и paths постоянного Solo VPS state. Полезно перед сменой checkout или при диагностике активного config/inventory.

### `make controller-check`

Read-only проверка first-run prerequisites контроллера.

### `make ssh-key`

Создаёт или повторно использует default SSH key **контроллера**. Он никогда не заменяет human workstation recovery identity.

### `make init`

Инициализирует persistent config/inventory вне Git checkout без перезаписи существующего operator state.

### `make human-admin-key-file`

Сохраняет **public** key human admin из явно указанного `.pub` file.

### `make human-admin-key-stdin`

Сохраняет **public** key human admin из stdin. Это удобно, когда project/controller работает на VPS, но recovery identity принадлежит workstation:

```bash
SERVER_IP='YOUR_SERVER_IP'
BOOTSTRAP_USER='YOUR_BOOTSTRAP_USER'
cat ~/.ssh/id_ed25519.pub | ssh "${BOOTSTRAP_USER}@${SERVER_IP}" \
  'cd ~/solo-vps && make human-admin-key-stdin'
```

Не передавайте private key.

### `make use-bootstrap` / `make use-admin`

Синхронизируют inventory с bootstrap SSH identity или managed admin identity. Это recovery/diagnostic helpers; normal `make apply` выполняет handoff автоматически.

## Diagnostics и verification

### `make doctor`

Запускает platform-aware diagnostics и remote preflight. Используйте, когда lifecycle command отказывается продолжать или перед рискованным subsystem change.

### `make preflight`

Read-only checks совместимости target и configuration.

### `make verify`

Read-only aggregate verification реализованного baseline.

### `make audit`

Read-only security audit реализованных host controls и exposure.

### `make ops-status`

Bounded fallback-статус host/container.

### `make ops-logs`

Read-only recent logs одного явно выбранного container:

```bash
make ops-logs CONTAINER=<container-name> TAIL=100
```

Для обычной работы с logs используйте Coolify или observability UI; эта команда — diagnostic fallback.

## Подсистемы хоста

Normal install использует `make apply`, `make secure` и `make platform`. Более узкие targets полезны при намеренной работе с одной subsystem:

| Apply target | Read-only verifier |
| --- | --- |
| `make firewall` | `make verify-firewall` |
| `make updates` | `make verify-updates` |
| `make docker` | `make verify-docker` |
| `make ssh-harden` | `make verify-ssh` |
| `make coolify` | `make verify-coolify` |

`make bootstrap` применяет текущий host bootstrap baseline, но **не активирует SSH hardening** и **не устанавливает Coolify**. Это lower-level recovery/engineering surface; first-time users должны предпочитать `make apply`.

## Команды backup

До использования настройте off-site storage и credentials по [руководству restic backup](backups-restic.md).

| Команда | Поведение |
| --- | --- |
| `make backup-readiness` | local/source-policy readiness; без обращения к storage |
| `make backup-tooling` | установить только pinned restic binary |
| `make verify-backup-tooling` | проверить restic tooling |
| `make backup-runtime` | установить root-only runtime + timer units; timer автоматически не включается |
| `make verify-backup-runtime` | проверить runtime files/timer state |
| `make backup-repository-init` | **external write** — инициализировать новый пустой encrypted repository |
| `make backup-repository-adopt` | прочитать/проверить существующий repository до adoption |
| `make backup-status` | read-only repository/freshness summary |
| `make backup-check` | read-only integrity + freshness check |
| `make backup-now` | **external write** — создать один off-site snapshot |
| `make backup` | выполнить настроенный backup и проверить repository/freshness |
| `make backup-restore-test` | восстановить latest matching snapshot во временное test tree |
| `make backup-retention-plan` | read-only retention dry run |
| `make backup-retention-apply` | **destructive external write** — применить reviewed forget/prune policy |

Scheduling включается отдельно:

```bash
make backup-schedule-enable
```

Weekly retention/prune также требует отдельного reviewed path; не включайте destructive maintenance только потому, что snapshots работают.

## Database backup и restore

Coolify владеет PostgreSQL logical backup schedule для Coolify-managed databases. Solo VPS не добавляет второй dump scheduler.

Полезные targets:

```bash
make database-backup-plan
make database-backup-configure
make database-backup-trigger
make database-backup-verify
```

Restore exercise намеренно отделён и destructive для **disposable target database**:

```bash
make database-restore-inspect
make database-restore-exercise
```

Следуйте [руководству PostgreSQL backup и restore](database-backups.md), а не запускайте restore targets по памяти.

## Recovery

### `make recover`

Печатает safety-gated entry point lost-VPS recovery. Сам по себе host не изменяет.

Full-host recovery требует больше, чем restic snapshot: следуйте [Disaster recovery](disaster-recovery.md), включая recovery inputs database экземпляра Coolify и application databases.

## Platform lifecycle и upgrades

### `make update`

Read-only review entry point для source-контракта Solo VPS и lifecycle Docker/Coolify. Команда **не** выполняет `git pull` и не обновляет хост вслепую.

### `make source-update-plan`

Печатает контракт обновления исходников через reviewed tag и новый checkout. Исполняемый пример и границы rollback находятся в [руководстве по обновлению Solo VPS и Coolify](upgrades.md).

### `make platform-lifecycle-plan`

Показывает reviewed Docker/Coolify support window.

### `make coolify-upgrade-preflight`

Read-only preflight для единственного поддерживаемого previous → current Coolify transition.

### `make coolify-upgrade`

**Mutating, confirmation-gated** поддерживаемое обновление Coolify. Требует backup checks и точных acknowledgements.

### `make coolify-upgrade-resume`

Явно продолжает известное interrupted supported upgrade. Это никогда не означает «автоматически downgrade».

Перед любым mutating upgrade target прочитайте [руководство по обновлению](upgrades.md).

## External uptime

Показать provider-neutral monitor policy без создания ресурсов:

```bash
make uptime-plan UPTIME_HEALTH_URL=https://app.example.com/healthz
```

После реального external outage/recovery exercise `make uptime-evidence` записывает sanitized operator-attested summary вне tracked source. См. [External uptime](operations/external-uptime.md).

## Optional retained logs

Если вы намеренно включаете Grafana Cloud retained logs:

```bash
make observability-secrets-init
make observability-secrets-check
make observability-secrets-push
make verify-observability-credentials
make observability-runtime
make verify-observability-runtime
```

Сначала прочитайте [главу 3: история логов](operations/observability.md). Core Quick Start этот module не требует.

## Optional метрики VPS

Если вы включаете профиль Grafana Cloud host metrics из главы 7:

```bash
make metrics-secrets-init
make metrics-secrets-check
make metrics-secrets-push
make verify-metrics-credentials
make metrics-runtime
make verify-metrics-runtime
```

Полный путь с credentials, интерфейсом Grafana и реальной проверкой alert описан в [главе 7: метрики VPS](operations/metrics.md).

## CI/CD transport

Для application path GitHub Actions → Coolify:

```bash
make plan-ci-deploy-transport
make ci-deploy-transport
make verify-ci-deploy-transport
```

Команды устанавливают отдельную forwarding-only deployment identity; они не входят в `make bootstrap`. См. [GitHub Actions + GHCR](ci-ghcr.md).

## Документация

### `make docs`

Создаёт/обновляет isolated documentation environment и запускает локальный preview server Material for MkDocs. Сайт собирается на английском и русском; язык переключается в header.

### `make docs-build`

Собирает обе локали через `mkdocs build --strict`. Используйте перед documentation commit.

См. [Сайт документации](documentation-site.md) для ручного setup и публикации GitHub Pages.

## Project validation

Для обычной local source validation:

```bash
make validate
```

Когда установлен pinned QA environment:

```bash
make qa-check
make qa-static
```

Maintainers могут посмотреть полный validator/test catalog:

```bash
make help-dev
make help-all
```

Полный internal target list намеренно не дублируется здесь: `make help-all` остаётся executable source of truth и уменьшает documentation drift.
