# 4. Back up and restore PostgreSQL

After this chapter, you will know not merely that a backup job turned green, but that **specific data can actually be restored**.

We start with a local copy on the same VPS. It protects against application mistakes, a bad migration, or accidental data deletion. It does **not** protect against losing the VPS itself; off-server storage comes later.

<div class="solo-delivery-flow" role="list" aria-label="How a PostgreSQL backup is verified">
  <div role="listitem"><span>1</span><div><strong>PostgreSQL · VPS</strong><p>Create a recognizable test record.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Coolify Backups · VPS</strong><p>Coolify creates a logical backup and keeps a local copy.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Separate PostgreSQL · VPS</strong><p>Restore the backup into a disposable database and verify the data.</p></div></div>
</div>

## Before you start

You need the working Coolify instance from chapter 1. For your first restore exercise, **do not use a production database as the restore target**.

If your application does not have PostgreSQL yet, that is fine: create a temporary database specifically for this chapter. You do not need to expose a database port; the entire exercise can stay inside Coolify.

The examples use two resources:

- `solo-vps-db-demo` — the source test database;
- `solo-vps-db-restore` — the separate database that receives the backup.

You can delete the second resource after the exercise.

## 1. Create a test PostgreSQL database

**In Coolify:**

1. Open the project and environment that contain the demo application.
2. Select **New Resource → Databases → PostgreSQL**.
3. Choose the same server and destination.
4. Use standard PostgreSQL without extra extensions and record the selected **major version**; the restore target will use the same one.
5. Name the resource `solo-vps-db-demo`.
6. Do not enable public database access.
7. Select **Start** and wait for Running/Healthy.

Coolify gives the database a separate persistent volume. That volume survives ordinary container replacement, but it is not itself a backup. [Coolify's PostgreSQL guide](https://coolify.io/docs/databases/postgresql) describes this lifecycle.

## 2. Write data that is easy to verify

Open **Terminal** for `solo-vps-db-demo`. If the resource has no Terminal tab, use the global **Terminal** item in the sidebar and select this PostgreSQL container.

Run:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "CREATE TABLE IF NOT EXISTS solo_vps_backup_probe (id integer PRIMARY KEY, value text NOT NULL); TRUNCATE solo_vps_backup_probe; INSERT INTO solo_vps_backup_probe VALUES (1, 'before-backup'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Expect:

```text
1|before-backup
```

This row is the fact we will prove later. After the backup, we will change the source database; the restored copy must still show the `before-backup` state.

## 3. Configure a local backup

Open `solo-vps-db-demo → Backups` and select **Add** next to Scheduled Backups.

For a first useful policy, set:

| Setting | Value |
| --- | --- |
| Frequency | `daily` |
| Enabled | on |
| S3 | off |
| Disable Local Backup | off, if shown |
| Number of backups to keep | `7` |
| Days to keep backups | `0` |
| Maximum storage (GB) | `0` |
| Timeout | keep the default `3600` |

A `0` day or size limit means that rule is unlimited; in this example the count limit keeps the latest seven local copies.

For PostgreSQL, leave the database selection empty when you want the database configured on this resource. Do not enable **Backup All Databases** for this exercise.

Save the schedule. Coolify creates an engine-aware PostgreSQL backup with `pg_dump` and stores the local file under `/data/coolify/backups`. Do not reconstruct the path manually; use the details on the actual execution. [Coolify documents the schedule and retention fields here](https://coolify.io/docs/databases/backups).

## 4. Create a backup now

In the new schedule, select **Backup Now**.

Wait for a new execution and open it. Confirm:

- status is **Success**;
- file size is greater than `0`;
- the intended database is listed;
- **Local Storage** is available;
- S3 is not required and remains disabled in this chapter.

Download the backup to your computer with **Download**. This is not yet a complete off-site backup process, but it gives you a straightforward file for an independent restore exercise.

**Do not continue if the execution failed or the file size is zero.**

## 5. Change the source after the backup

Return to the `solo-vps-db-demo` Terminal and run:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "INSERT INTO solo_vps_backup_probe VALUES (2, 'after-backup'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Expect two rows:

```text
1|before-backup
2|after-backup
```

The source is now ahead of the backup. That lets the restore prove a real point-in-time state rather than merely proving that PostgreSQL accepts connections.

## 6. Create a separate restore database

Create a second **PostgreSQL** resource the same way as step 1:

- name: `solo-vps-db-restore`;
- same server and destination;
- same PostgreSQL **major version**;
- no public port.

Start it and wait for Running/Healthy. Do not create the probe table in this database manually.

## 7. Restore the downloaded backup

Open `solo-vps-db-restore → Configuration → Import Backup`.

1. Choose **Restore from File**.
2. Upload the file downloaded in step 4.
3. For a normal single-database PostgreSQL backup, leave **Backup includes all databases** disabled.
4. Keep the default `pg_restore` import command for a custom-format backup unless you deliberately changed the source backup format.
5. Select **Restore Database from File**.
6. In the destructive-action confirmation, verify that the target is `solo-vps-db-restore`, not the source database.
7. Wait for **Database Restore Output** to finish without an error.

Import Backup changes the target database, so always perform the first proof on a disposable target. [Coolify documents the current Restore from File workflow here](https://coolify.io/docs/databases/restore).

## 8. Verify the restored data

Open Terminal for `solo-vps-db-restore` and run:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

The correct result is:

```text
1|before-backup
```

`2|after-backup` must **not** be present because that row was created after the backup.

For comparison, the source `solo-vps-db-demo` should still return both rows. This proves three things at once: the backup contains data, restore really runs, and it restored the intended point in time.

## If something fails

| What you see | What to check |
| --- | --- |
| Backup Now creates no execution | PostgreSQL must be running; check the schedule and database scope |
| Execution Failed | Open the execution message; check the resource credentials and timeout |
| `Permission denied` under `/data/coolify/backups/...` | On the VPS, from `~/solo-vps`, run `make coolify`, then `make verify-coolify`, and retry **Backup Now**. Do not recursively `chmod`/`chown` `/data/coolify` by hand |
| Backup is Success but Local Storage is unavailable | Make sure **Disable Local Backup** is off |
| Restore rejects the file | Confirm it is a PostgreSQL backup and the target uses a compatible major version |
| `pg_restore` reports existing objects | The restore target must be separate and contain no application tables |
| The restored table is missing | Check which database the schedule backed up and which `$POSTGRES_DB` the Terminal uses |
| The restored database contains `after-backup` | You selected a newer backup or ran Backup Now after the second insert |

Do not delete the source database or restore over it merely to test this guide.

## Done: local restore is proven

Leave the schedule enabled when this database is part of your application. Check **Executions** periodically and repeat the restore exercise after important schema changes.

A local backup still lives on the same VPS. Losing the disk or server can destroy both the database and its backup files. Valuable data therefore needs a copy outside the VPS.

**Next:** continue with [chapter 5 — external uptime alerts](external-uptime.md). After that, move on to off-site copies and lost-server recovery.
