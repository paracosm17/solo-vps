# Backup Solo VPS через restic

Solo VPS использует restic для зашифрованного **off-site filesystem recovery material**. Если настраиваете внешние копии впервые, идите по [главе 6: резервные копии вне VPS](operations/offsite-backups.md): там Backblaze B2, копия PostgreSQL, backup панели Coolify и restic restore-test собраны в одну последовательность.

Эта страница — технический справочник по restic.

> Off-site storage не означает второй VPS. Достаточно managed S3-compatible object store; администрировать по-прежнему нужно только один application VPS.

## Что защищает core restic backup

Источник filesystem по умолчанию:

```text
/data/coolify
```

с исключениями:

```text
/data/coolify/ssh/mux
/data/coolify/databases
/data/coolify/backups
```

Это **Coolify filesystem/control-plane recovery material**, а не полный backup application data.

Application PostgreSQL защищается отдельно logical database backups. Произвольным application persistent volumes нужна собственная application-aware backup procedure.

## Что нужно заранее

Перед включением backup понадобятся:

- S3-compatible bucket вне failure domain VPS;
- bucket-scoped credentials;
- workstation age identity и SOPS policy;
- non-secret repository coordinates в Solo VPS config;
- рабочий managed admin path.

Если external storage пока нет, продолжайте использовать core platform и **пропустите backup на этом этапе**. Компромисс явный: disaster recovery остаётся неполным.

Основной пример провайдера: [Backblaze B2](backup-storage-backblaze-b2.md). [Cloudflare R2](backup-storage-cloudflare-r2.md) оставлен как альтернативный вариант.

## 1. Настройте repository metadata

**Где: persistent Solo VPS config**

```yaml
backup:
  repository:
    endpoint: https://s3.example.com
    bucket: solo-vps-backups
    prefix: solo-vps
    region: us-east-1
```

Это публичные repository coordinates. Credentials здесь не хранятся.

Effective repository path вычисляется отдельно для каждого host из endpoint, bucket, prefix и `server.hostname`.

## 2. Установите и проверьте restic

**Где: управляемый VPS/контроллер**

Solo VPS сейчас pin-ит restic `0.19.1` и устанавливает checksum-verified binary как `/usr/local/bin/restic`.

```bash
make backup-tooling
make verify-backup-tooling
make backup-readiness
```

`backup-readiness` read-only и не обращается к repository.

Существующая конфликтующая установка restic рассматривается как ownership/migration decision, а не заменяется молча.

## 3. Создайте зашифрованные backup credentials

Secret bundle содержит:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN   optional
RESTIC_PASSWORD
```

Ciphertext хранится вне source checkout как `backup.enc.yaml`. **Age private key остаётся на рабочей станции**.

### Рабочая станция Windows

Если это один раз требуется для checkout, скачанного из Интернета:

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
```

Инициализируйте/перепроверьте persistent public SOPS policy:

```powershell
.\scripts\windows\init-sops-policy.ps1
```

Создайте и протестируйте encrypted bundle:

```powershell
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
```

Передайте decrypted values через SSH stdin без создания plaintext-файла на рабочей станции:

```powershell
.\scripts\windows\push-backup-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

### Рабочая станция Linux

```bash
make secrets-tools
make check-secrets-tools
make backup-secrets-init
make backup-secrets-check
make backup-secrets-push BACKUP_VPS_HOST=<VPS-IP> BACKUP_VPS_USER=<admin-user>
```

### Проверьте на VPS

```bash
make verify-backup-credentials
```

Runtime file на VPS:

```text
/etc/solo-vps/backup/credentials.json
```

с root-only permissions. Helper проверяет schema/metadata без вывода secret values.

## 4. Установите backup runtime

**Где: управляемый VPS/контроллер**

```bash
make backup-runtime
make verify-backup-runtime
```

Команды устанавливают root-only runtime и systemd units. Schedules не включаются автоматически до прохождения repository/snapshot safety gates.

## 5. Инициализируйте или примите repository

Выберите **один** путь.

### Новый пустой repository

```bash
make backup-repository-init
```

Это external write. Команда падает, если repository уже открывается как существующий restic repository.

### Существующий repository

```bash
make backup-repository-adopt
```

Команда проверяет, что настроенный repository является рабочим существующим restic repository, прежде чем Solo VPS начнёт его использовать.

## 6. Создайте первый реальный backup

```bash
make backup
```

`make backup` создаёт один encrypted snapshot, затем выполняет repository/freshness check.

Для отдельных операций:

```bash
make backup-now
make backup-status
make backup-check
```

**Ожидаемый результат**

Последний подходящий snapshot свежий, repository открывается успешно, а check завершается без раскрытия credentials.

## 7. Докажите реальный restore

Snapshot не является recovery evidence, пока restore не работает.

```bash
make backup-restore-test
```

Test восстанавливает последний подходящий snapshot во временную приватную директорию под `/var/tmp`, проверяет ожидаемый scope и удаляет temporary test tree. Он никогда не накладывает восстановленные данные поверх работающего `/data/coolify`.

Для lost-VPS recovery отдельный staged restore path намеренно сохраняет приватные recovered materials для replacement-host procedure. См. [восстановление потерянного VPS](disaster-recovery.md).

## 8. Включите schedules только после proof

После доказанного доступа к repository, свежего snapshot и restore verification:

```bash
make backup-schedule-enable
```

Default daily backup timer запускается примерно в `03:15` с randomized delay.

Перед destructive maintenance просмотрите retention plan:

```bash
make backup-retention-plan
```

Только после review dry run:

```bash
BACKUP_RETENTION_CONFIRM=I_HAVE_REVIEWED_THE_BACKUP_RETENTION_PLAN \
make backup-maintenance-schedule-enable
```

Retention/prune path намеренно отделён от обычного создания backup.

## Security model backup

- credentials и restic password не появляются в public config;
- production age private key остаётся на workstation;
- VPS получает только root-only runtime credential material, который ему нужен;
- restic secrets не передаются command-line arguments;
- `/var/lib/docker` и `/var/lib/postgresql` не используются как raw backup sources;
- restic tree никогда не считается безопасным direct overlay на свежий Coolify.

## Что restic не заменяет

Вам всё ещё нужны:

- backup database экземпляра Coolify;
- logical application PostgreSQL backups;
- immutable Git/GHCR artifacts для redeployment;
- recovery kit вне VPS;
- application-specific procedures для важных persistent volumes.

См. [database-aware backups](database-backups.md) и [recovery потерянного VPS](disaster-recovery.md).
