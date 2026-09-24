# Backup и restore PostgreSQL

Solo VPS делегирует плановые logical backup **PostgreSQL под управлением Coolify** самому Coolify, а сверху добавляет policy/verification и намеренно отдельное restore exercise.

Главное правило простое: **успешной backup job недостаточно; recovery должен восстановить данные в disposable database и проверить факт, значимый для приложения.**

## Граница ответственности

**Операционный слой Coolify API** управляет одним явно принадлежащим проекту backup schedule и проверяет его свежесть. Он **не запускает второй database dump scheduler**.

```text
Coolify
  → database lifecycle
  → pg_dump/custom-format backup
  → S3 upload and schedule

Solo VPS
  → desired schedule/retention policy
  → loopback-only API ownership and verification
  → archive inspection
  → disposable restore safety checks
  → application-relevant read-only verification query
```

## Политика по умолчанию

Текущая стартовая policy:

```text
frequency:            daily
S3 copy:              enabled
local copies:         2
S3 retention:         30 days
freshness threshold:  36 hours
```

Эти defaults не доказывают, что реальный внешний object существует.

## Настройте schedule под управлением Coolify

Helper обращается только к приватному Coolify API (`127.0.0.1:8000` или проверенному local-forward endpoint). API token передаётся через environment и не является аргументом команды.

Начните с non-mutating plan:

```bash
make database-backup-plan \
  DATABASE_BACKUP_DATABASE_UUID=<database-uuid> \
  DATABASE_BACKUP_S3_STORAGE_UUID=<s3-storage-uuid> \
  DATABASE_BACKUP_DATABASES=<database-name>
```

Если у database уже есть schedule, проверьте/adopt его вместо создания duplicate. Mutating configuration и trigger operations требуют явного confirmation, предусмотренного Makefile.

UUID schedule, которым владеет Solo VPS, хранится во внешнем controller state, а не в Git.

## Запустите и проверьте реальный backup

После настройки:

```bash
make database-backup-trigger \
  DATABASE_BACKUP_DATABASE_UUID=<database-uuid> \
  DATABASE_BACKUP_S3_STORAGE_UUID=<s3-storage-uuid> \
  DATABASE_BACKUP_DATABASES=<database-name>

make database-backup-verify \
  DATABASE_BACKUP_DATABASE_UUID=<database-uuid> \
  DATABASE_BACKUP_S3_STORAGE_UUID=<s3-storage-uuid> \
  DATABASE_BACKUP_DATABASES=<database-name>
```

Verification проверяет совпадение policy, успешный latest execution, положительный размер archive, freshness и reported S3 success.

Она намеренно сообщает:

```text
S3 object independently verified: no
```

потому что success record Coolify не является независимой проверкой object store.

## Формат PostgreSQL archive

Документированный PostgreSQL backup Coolify использует custom-format archive с отключённым восстановлением ownership/ACL. Скачанный archive можно проверить без restore:

```bash
make database-restore-inspect DATABASE_RESTORE_ARCHIVE=/path/to/database.dump
```

Archive inspection доказывает только структуру.

## Disposable restore exercise

Восстанавливайте в database, созданную специально для упражнения. Её имя должно начинаться с:

```text
solo_vps_restore_
```

Target должен быть пустым. Credentials должны поступать через приватный `PGPASSFILE`; helper отклоняет password command-line options и не использует `PGPASSWORD`.

Настоящее доказательство выглядит так:

```text
custom-format archive
→ prove target DB is empty
→ pg_restore
→ run one application-relevant read-only SELECT
→ compare the exact expected result
```

Make target:

```bash
make database-restore-exercise \
  DATABASE_RESTORE_ARCHIVE=/path/to/database.dump \
  DATABASE_RESTORE_DATABASE=solo_vps_restore_example \
  DATABASE_RESTORE_PGPASS_FILE=/path/to/private.pgpass \
  DATABASE_RESTORE_VERIFY_QUERY='SELECT ...' \
  DATABASE_RESTORE_EXPECT='<expected-value>' \
  DATABASE_RESTORE_CONFIRM=I_HAVE_VERIFIED_THE_DISPOSABLE_DATABASE_TARGET
```

Используйте query, которое доказывает наличие значимых application data, а не просто способность PostgreSQL принимать connections.

## Собственная database Coolify — отдельный ресурс

При потере VPS нужен также **backup database самого Coolify**, потому что в ней содержатся dashboard/resource metadata. Это отдельный recovery input от PostgreSQL archives приложений.

## Граница application migration

`Application tests` и rollback container image не доказывают database recovery. Шаблон GitHub Actions содержит отдельный application-owned migration preflight; irreversible schema/data changes всё равно требуют backup/restore или forward-fix plan.

## Никогда не делайте так

- не копируйте raw live PostgreSQL data directories через restic как database strategy;
- не создавайте duplicate host-level database dump scheduler;
- не храните database/S3 passwords в public config;
- не публикуйте Coolify API для backup automation;
- не считайте наличие archive или `pg_restore --list` успешным restore;
- не выполняйте restore proof в непустую production database.
