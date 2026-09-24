# Руководство по обновлению

Solo VPS находится в статусе **PRE-ALPHA**. Обновления — это осознанные операции с определённым support window, preflight, verification и recovery path. Универсальной команды «обновить всё» нет.

## Safety model обновлений

Для любого runtime-sensitive изменения используйте последовательность:

```text
identify exact current + target versions
-> read the component's recovery boundary
-> prove required backups/recovery inputs
-> run read-only preflight
-> change one subsystem
-> verify that subsystem
-> make verify
-> make audit
```

Если для изменения невозможно описать recovery path, оно не готово к production execution.

Предыдущий checkout проекта **не** является generic runtime rollback. Возврат source revision не отменяет package changes, database migrations или external state changes.

## Обновление исходников Solo VPS

Исходники Solo VPS обновляются через **новый checkout проверенного релиза**, а не через `git pull` в активном каталоге. Конфигурация конкретной установки, inventory и зашифрованное состояние оператора находятся вне исходников, поэтому оба checkout используют одно persistent state.

Пока проект PRE-ALPHA, release tag ещё не опубликован. До первого релиза используйте только проверенный commit или архив, подготовленный для тестирования. После публикации релиза выбирайте его точный tag:

```bash
REPOSITORY_URL='YOUR_SOLO_VPS_REPOSITORY_URL'
RELEASE_VERSION='v0.1.0'
git clone --branch "$RELEASE_VERSION" --depth 1 "$REPOSITORY_URL" "solo-vps-${RELEASE_VERSION}"
cd "solo-vps-${RELEASE_VERSION}"
test "$(git describe --tags --exact-match)" = "$RELEASE_VERSION"
```

До изменения VPS проверьте новые исходники:

```bash
make setup
make paths
make validate
make doctor
make verify
make audit
```

Сравните вывод `make paths` со старым checkout. Пути config и inventory должны совпадать. Прочитайте release notes целевой версии и выполните только явно указанную subsystem migration или lifecycle-команду. Смена исходников сама по себе не требует `make secure`, обновления Docker или обновления Coolify.

Сохраняйте предыдущий checkout, пока новые исходники не пройдут проверки и приложение не останется healthy. Возврат к старому каталогу возвращает только automation source и не отменяет runtime-изменения, уже выполненные subsystem upgrade.

## Project automation и host configuration

Per-installation **controller state теперь хранится вне checkout**. Перед переключением source revision проверьте активные paths:

```bash
make paths
```

Для проверенного изменения source Solo VPS:

```bash
make validate
make doctor
# apply only the intended subsystem/lifecycle operation
make verify
make audit
```

Если меняется config schema, сравните persistent configuration с `config/config.example.yml`. Сохраняйте source checkpoint, но не путайте его с rollback хоста/данных.

### Повторная проверка существующего VPS после исправления кода

Этот порядок подходит для проверенного исправления автоматизации, при котором установленные версии Docker/Coolify остаются поддерживаемыми. Сохраните вторую рабочую SSH-сессию и доступ к консоли восстановления провайдера.

1. Войдите под существующим управляемым администратором. В старом каталоге исходников выполните `make paths` и запишите пути config/inventory. Сохраните старые исходники и необходимые резервные копии данных.
2. Распакуйте или клонируйте проверенную версию в новый каталог. Запишите commit ID: `git rev-parse HEAD` для клона или ревизию, указанную вместе с архивом. Под тем же пользователем выполните там `make paths`. Пути persistent config/inventory должны совпадать; не инициализируйте вторую установку и не заменяйте активную конфигурацию примером. Если контроллер работает на самом VPS, сохраните старый `~/solo-vps` под отдельным именем резервной копии, поместите новые исходники в `~/solo-vps` и продолжайте из этого стандартного admin workspace.
3. Выполните `make setup` для согласования зависимостей контроллера. Существующие ключи и конфигурация сохраняются. Для регрессионной проверки разработчиком выполните `make qa-tools`, затем `make qa-static`. QA проверяет разбор версий Docker и диагностику слушающих портов на закреплённом движке Ansible, без обращения к VPS через SSH.
4. По одной выполните `make doctor`, `make verify` и `make audit`. Это исходное состояние, которое видит новый код. Зафиксируйте и разберите любую ошибку до изменения сервера.
5. Для исправления разбора версии Docker выполните `make docker`, затем `make verify-docker`. Поддерживаемые установленные пакеты Docker должны сохраниться. Выполните `make apply`, чтобы повторить весь host baseline через существующий admin inventory.
6. Выполните `make platform` для согласования и проверки управляемой установки Coolify. После успеха ещё раз выполните `make apply` и `make platform`, проверяя повторяемость, затем `make verify` и `make audit`. Не запускайте `make secure` только из-за смены исходников: на уже защищённом хосте эта политика действует.
7. Проверьте URL приложения и логи. Только после успеха всех предыдущих шагов выполните запланированную перезагрузку, снова подключитесь под администратором и повторите `make verify`, `make audit` и проверку приложения.

Останавливайтесь на первой упавшей команде и сохраняйте полный вывод вместе с ревизией исходников. `make update` показывает план; переход версии Coolify — отдельная операция ниже. Успешный проход на существующем хосте не заменяет последующую проверку [Quick Start на чистом VPS](quick-start.md).

## Docker Engine и Compose

Текущий alpha support window намеренно узкий: **Docker 29.x** на Ubuntu 24.04. Непроверенный major **Docker 30** отклоняется — role должна **fail closed**, а не молча пересекать major-version boundary.

Docker role использует package state `present`. Поэтому **`make docker` не обновляет уже установленный Docker Engine** только потому, что в repository появилась новая package version.

До расширения Docker window:

1. изучите upstream release/security notes;
2. одновременно обновите lifecycle policy и role defaults;
3. запустите Docker contract/unit/QA checks;
4. на disposable target докажите Coolify, exposure, application delivery, backup/restore, `make verify` и `make audit`;
5. только после этого меняйте supported window.

После проверенного Docker package change:

```bash
make verify-docker
make verify
make audit
```

Source rollback не является downgrade Docker package.

## Coolify

Solo VPS управляет Coolify через закреплённую и проверяемую интеграцию. Управление хостом и Docker остаётся у Solo VPS, а не передаётся непроверенному установщику.

Поддерживаемая lifecycle pair в этой source revision:

```text
previous supported Coolify: `4.1.1`
current supported Coolify: `4.1.2`
transition:                 4.1.1 -> 4.1.2
AUTOUPDATE=false
```

`make update` и `make platform-lifecycle-plan` — read-only planning surfaces.

### Preflight

Перед поддерживаемым transition:

```bash
make coolify-upgrade-preflight
```

Preflight проверяет managed installation, exact version pair, Docker support window, current runtime health, loopback-only management ports, `AUTOUPDATE=false` и отсутствие незавершённой install/upgrade transaction.

### Upgrade

Mutating path намеренно защищён explicit confirmations:

```bash
COOLIFY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN \
make coolify-upgrade
```

Перед обновлением автоматически создаётся локальная копия в `/var/lib/solo-vps/checkpoints/coolify-*`: custom-format dump БД Coolify, архив `source` (включая `.env`), SSH-ключей и marker, SHA-256 manifest. Проверяется `pg_restore --list`; при ошибке обновление не начинается. Каталог доступен только root. Он сохраняется после успеха или сбоя, его путь записан в `.solo-vps-upgrading`. S3 и restic не требуются.

Копия содержит секреты и не включает данные пользовательских приложений. Она не переживёт потерю VPS, а проверка архива не доказывает успешное восстановление. Перед обновлением остановите деплои и изменения ENV в UI. Если forward resume невозможен, сохраните копию и исследуйте восстановление на отдельном тестовом экземпляре той же исходной версии. Автоматический restore этой локальной копии пока не предоставляется. Удаляйте старые копии вручную только после проверки обновления и нужного периода хранения.

### Прерванное обновление

Solo VPS **не выполняет автоматический downgrade Coolify** после interrupted/failed transition. **Database migrations Coolify** уже могли выполниться, поэтому слепой возврат только старого container image может создать некорректную app/schema pairing.

Сначала исследуйте failure. Чтобы явно продолжить тот же поддерживаемый forward transition:

```bash
COOLIFY_UPGRADE_RESUME_CONFIRM=I_HAVE_REVIEWED_THE_INTERRUPTED_COOLIFY_UPGRADE \
make coolify-upgrade-resume
```

Иначе используйте disaster-recovery path с проверенными recovery inputs. Никогда не удаляйте transaction marker только ради обхода safety gate.

## Pinned controller и project dependencies

Изменения dependencies рассматривайте как source-maintenance changes. Authoritative sources:

| Компонент | Source of truth |
| --- | --- |
| `community.general` | `ansible/requirements.yml` |
| Ansible QA stack | `tools/qa-requirements.txt` |
| SOPS + age | `tools/secrets-toolchain.json` |
| restic | `ansible/roles/backup/defaults/main.yml` |
| sample Python image | `examples/hello-app/Dockerfile` |
| consumer GitHub Actions | `templates/github-actions/hello-app-ci.yml` |
| Docker/Coolify lifecycle | `docs/contracts/platform-lifecycle-policy.yml` |

Обновляйте один dependency class за раз: review upstream notes → change authoritative pin → run validators/tests → `make validate` → получите real integration evidence, если изменилось runtime behavior.

Не заменяйте exact pins на floating `latest` ради удобства.

## SOPS, age и restic

Для SOPS/age обновляйте `tools/secrets-toolchain.json` на основании проверенных releases и повторно запускайте project crypto/toolchain checks до отказа от known-good binaries.

Для restic обновляйте `ansible/roles/backup/defaults/main.yml` и hashes. Не используйте `restic self-update` как management path Solo VPS.

После проверенного restic change:

```bash
make validate-backup-tooling
make backup-tooling
make verify-backup-tooling
```

Когда существует реальный repository, дополнительно докажите repository readability и restore behavior до заявления об operational verification.

## Optional modules

Опциональные capabilities не входят в core upgrade path, если вы их не включали. Tailscale, Grafana/Alloy, error tracking, pgAdmin и shell customization не должны тянуть несвязанные core upgrades.

Каждому включённому optional module нужны собственный version source, verification step и recovery/data-impact note.

## Rollback и recovery

Универсального `make rollback` нет.

| Изменение | Recovery boundary |
| --- | --- |
| Solo VPS source | вернуться к проверенному source checkpoint; runtime всё ещё может требовать subsystem recovery |
| SSH/firewall/sudo | provider recovery + доказанный human-admin access |
| Docker | package/runtime-specific recovery |
| Coolify | explicit forward resume или disaster recovery; без automatic downgrade |
| SOPS/age | сохранять предыдущий verified tooling, пока новые crypto checks не пройдут |
| restic | сохранять known-compatible client, пока не доказаны repository + restore compatibility |
| application image | только container image rollback |
| database/schema/data | database backup/restore; image rollback не откатывает data |

Если для изменения нельзя описать recovery path, оно не готово к production execution.

## Checklist обновления

До:

```text
[ ] exact current and target versions are known
[ ] target is inside the reviewed support window
[ ] release/security notes were reviewed
[ ] backup/recovery prerequisites are proven
[ ] make validate passes
[ ] make doctor passes
[ ] read-only subsystem preflight passes
[ ] disposable proof is planned for runtime/data-sensitive changes
```

После:

```text
[ ] subsystem verifier passes
[ ] make verify passes
[ ] make audit has no unexplained new finding
[ ] public application behavior is checked
[ ] recovery inputs are retained
[ ] source/version evidence is recorded
```

## Текущие ограничения

На этом PRE-ALPHA checkpoint:

- контракт обновления через tagged checkout описан, но публичного release channel и release tag пока нет;
- Docker support намеренно ограничен 29.x вместо generic package auto-upgrades;
- текущий lifecycle source представляет только transition Coolify 4.1.1 → 4.1.2;
- source-level implementation не заменяет disposable upgrade/recovery evidence;
- off-site backup и изолированный restore подтверждены интеграционно, но полное восстановление потерянного VPS ещё требует clean replacement-host exercise;
- optional modules сохраняют отдельные lifecycle contracts.

Перед любым изменением, способным повлиять на data или control-plane recovery, прочитайте [Disaster recovery](disaster-recovery.md).
