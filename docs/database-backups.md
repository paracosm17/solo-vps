# Back up and restore PostgreSQL

Solo VPS delegates scheduled logical backups of **Coolify-managed PostgreSQL** to Coolify, then adds policy/verification and a deliberately separate restore exercise.

The core rule is simple: **a successful backup job is not enough; recovery must restore data into a disposable database and verify an application-relevant fact.**

## Responsibility boundary

The **Coolify API operational layer** manages one explicitly owned backup schedule and verifies its freshness. It **does not run a second database dump scheduler**.

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

## Default policy

The current starter policy is:

```text
frequency:            daily
S3 copy:              enabled
local copies:         2
S3 retention:         30 days
freshness threshold:  36 hours
```

These defaults are not proof that your real external object exists.

## Configure a Coolify-owned schedule

The helper talks only to the private Coolify API (`127.0.0.1:8000`, or the reviewed local-forward endpoint). The API token is supplied through the environment and is not a command argument.

Start with a non-mutating plan:

```bash
make database-backup-plan \
  DATABASE_BACKUP_DATABASE_UUID=<database-uuid> \
  DATABASE_BACKUP_S3_STORAGE_UUID=<s3-storage-uuid> \
  DATABASE_BACKUP_DATABASES=<database-name>
```

If the database already has a schedule, review/adopt it rather than creating a duplicate. Mutating configuration and trigger operations require the explicit confirmation expected by the Makefile.

The schedule UUID Solo VPS owns is stored in external controller state, not in Git.

## Trigger and verify a real backup

After configuration:

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

Verification checks policy match, successful latest execution, positive archive size, freshness, and reported S3 success.

It deliberately reports:

```text
S3 object independently verified: no
```

because Coolify's success record is not an independent object-store check.

## PostgreSQL archive format

Coolify's documented PostgreSQL backup uses a custom-format archive with ownership/ACL restoration disabled. You can inspect a downloaded archive without restoring it:

```bash
make database-restore-inspect DATABASE_RESTORE_ARCHIVE=/path/to/database.dump
```

Archive inspection proves structure only.

## Disposable restore exercise

Restore into a database created specifically for the exercise. Its name must start with:

```text
solo_vps_restore_
```

The target must be empty. Credentials must come through a private `PGPASSFILE`; the helper rejects password command-line options and does not use `PGPASSWORD`.

A real proof has this shape:

```text
custom-format archive
→ prove target DB is empty
→ pg_restore
→ run one application-relevant read-only SELECT
→ compare the exact expected result
```

The Make target is:

```bash
make database-restore-exercise \
  DATABASE_RESTORE_ARCHIVE=/path/to/database.dump \
  DATABASE_RESTORE_DATABASE=solo_vps_restore_example \
  DATABASE_RESTORE_PGPASS_FILE=/path/to/private.pgpass \
  DATABASE_RESTORE_VERIFY_QUERY='SELECT ...' \
  DATABASE_RESTORE_EXPECT='<expected-value>' \
  DATABASE_RESTORE_CONFIRM=I_HAVE_VERIFIED_THE_DISPOSABLE_DATABASE_TARGET
```

Use a query that proves meaningful application data exists, not merely that PostgreSQL accepts connections.

## Coolify's own database is separate

A lost VPS also needs a **Coolify instance database backup** because that database contains dashboard/resource metadata. It is a separate recovery input from application PostgreSQL archives.

## Application migration boundary

`Application tests` and container-image rollback do not prove database recovery. The GitHub Actions template has a separate application-owned migration preflight; irreversible schema/data changes still require a backup/restore or forward-fix plan.

## Never do this

- raw-copy live PostgreSQL data directories as the restic database strategy;
- create a duplicate host-level database dump scheduler;
- put database/S3 passwords in public config;
- expose Coolify API publicly for backup automation;
- treat archive presence or `pg_restore --list` as a successful restore;
- restore proof data into a non-empty production database.
