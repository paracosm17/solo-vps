# Восстановление после потери VPS

Это поддерживаемая recovery model для ситуации, когда **старый VPS потерян** и нужно восстановиться на **свежем Ubuntu 24.04** replacement host.

> Текущий статус: source-side процедура реализована, но alpha release всё ещё требует полного destroyed-VPS replacement exercise с реальными off-site data.

## Последовательность восстановления

```text
old VPS lost
↓
fresh Ubuntu 24.04 replacement
↓
restore Solo VPS operator inputs
↓
apply host baseline + harden SSH
↓
install the same pinned Coolify version fresh
↓
restore Coolify instance database + identity material
↓
restore application PostgreSQL
↓
redeploy immutable application images
↓
repoint DNS if required
↓
verify + audit + public health checks
```

## Что должно пережить потерю старого VPS

До заявления о disaster-recovery readiness независимо восстанавливаемыми должны быть:

1. проверенный Solo VPS release/source revision;
2. off-VPS recovery kit;
3. workstation age private identity и её отдельный backup;
4. managed off-site restic repository и encrypted backup credentials;
5. **backup database экземпляра Coolify** вне VPS;
6. logical backups PostgreSQL приложений вне VPS;
7. Git repositories и **immutable** GHCR image artifacts;
8. доступ к DNS/provider account.

Если приложение хранит важные данные в **произвольных persistent volumes**, core alpha автоматически их не защищает. Добавьте application-specific backup/restore procedure.

## 1. Экспортируйте recovery kit и скопируйте его до аварии

Создайте kit в защищённом path:

```bash
make recovery-kit-export \
  RECOVERY_KIT_OUTPUT="$HOME/solo-vps-recovery-kit.tar.gz" \
  RECOVERY_SOURCE_REVISION='<release-or-reviewed-revision>'
```

Скопируйте archive **за пределы VPS**, затем там же проверьте копию:

```bash
make recovery-kit-verify \
  RECOVERY_KIT_OUTPUT=/path/to/copied/solo-vps-recovery-kit.tar.gz
```

Kit может содержать config, SOPS public policy/ciphertext и небольшой controller state. Он никогда не содержит age private key, SSH private keys или plaintext storage credentials.

## 2. Подготовьте replacement VPS

Создайте чистый Ubuntu 24.04 target и получите проверенный Solo VPS source revision.

Распакуйте verified recovery inputs во внешний Solo VPS data root без перезаписи существующих файлов:

```bash
make recovery-kit-extract \
  RECOVERY_KIT_OUTPUT=/path/to/copied/solo-vps-recovery-kit.tar.gz
```

Обновите `server.host` на replacement address. Если восстанавливаете ту же installation identity, сохраните intended hostname.

Пройдите normal host lifecycle до hardened administrator path:

```bash
make apply
make secure
```

## 3. Установите Coolify заново

Установите **ту же поддерживаемую pinned версию Coolify** как новую платформу:

```bash
make platform
```

Не накладывайте старое дерево `/data/coolify` поверх работающей свежей установки.

## 4. Подготовьте restic filesystem material в staging

Установите backup runtime/credentials на replacement host и восстановите выбранный snapshot в **новую приватную staging directory**:

```bash
RECOVERY_STAGING_ROOT=/var/tmp/solo-vps-disaster-recovery/recovery-<id> \
RECOVERY_STAGING_CONFIRM=I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY \
make backup-restore-staging
```

Target должен быть новым пустым private path. Staged tree — input recovery procedure, а не direct overlay.

## 5. Проверьте backup экземпляра Coolify и restore plan

```bash
make coolify-instance-restore-inspect \
  COOLIFY_INSTANCE_BACKUP_ARCHIVE=/path/to/coolify-instance.dmp

make coolify-instance-restore-plan \
  COOLIFY_INSTANCE_BACKUP_ARCHIVE=/path/to/coolify-instance.dmp \
  RECOVERY_STAGING_ROOT=/var/tmp/solo-vps-disaster-recovery/recovery-<id>
```

Фактический destructive restore намеренно защищён safety gate и предназначен только для проверенного replacement target.

Поддерживаемый restore сохраняет **свежие** platform secrets там, где это нужно, восстанавливает старую database экземпляра Coolify, возвращает предыдущий Coolify application encryption key через `APP_PREVIOUS_KEYS` и необходимые Coolify SSH identities, не авторизуя каждый recovered key для localhost login.

## 6. Восстановите PostgreSQL приложений

Каждая защищённая application database должна быть восстановлена из logical archive в replacement database и проверена application-relevant read-only query.

Используйте процедуру [backup и restore PostgreSQL](database-backups.md).

Restore database экземпляра Coolify **не** восстанавливает содержимое PostgreSQL приложений.

## 7. Заново разверните приложения

Redeploy выполняйте из проверенных Git/GHCR sources с точными **immutable** image identities. Не используйте mutable tag как disaster-recovery evidence.

Container-image rollback остаётся отдельным от database/schema recovery.

## 8. Перенаправьте DNS и проверьте систему

Если public address изменился, обновите DNS/provider routing. Затем выполните:

```bash
make verify-coolify
make verify
make audit
```

После этого снаружи VPS проверьте:

- public health endpoint приложения;
- ожидаемые application data после PostgreSQL restore;
- external uptime recovery notification;
- optional retained logs, если они настроены.

## Recovery завершён только когда приложение снова полезно

Replacement host, который просто загружается, не является успешным recovery. Proof должен подтвердить, что:

- metadata Coolify пригодны к использованию;
- PostgreSQL приложений содержит ожидаемые данные;
- immutable applications redeploy успешно;
- public routing работает;
- host verification и audit проходят;
- внешне видимый service healthy.

## Важная граница

Restic filesystem snapshot, database экземпляра Coolify, application PostgreSQL backups, recovery kit, Git/GHCR artifacts и provider access намеренно являются отдельными inputs. Потеря единственного VPS не должна уничтожать все authority, необходимые для его восстановления.
