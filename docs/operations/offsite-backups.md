# 6. Move backups off the VPS

The local backup from chapter 4 helps after an application mistake or a bad migration. If the VPS or its disk is lost, the local copy disappears with it.

In this chapter we create external S3-compatible storage and place three different recovery components there:

<div class="solo-delivery-flow" role="list" aria-label="What is stored off the VPS">
  <div role="listitem"><span>1</span><div><strong>PostgreSQL · Coolify</strong><p>A logical application-data backup is uploaded to Backblaze B2.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Coolify · control plane</strong><p>A separate backup keeps projects, resources, settings and deployment history.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Solo VPS · restic</strong><p>An encrypted snapshot keeps the required /data/coolify files outside the server.</p></div></div>
  <div role="listitem"><span>4</span><div><strong>Keys · off the VPS</strong><p>APP_KEY and the age identity are kept separately from the server and bucket.</p></div></div>
</div>

The guided path uses **Backblaze B2**, a managed object store with an S3-compatible API. B2 does not require a credit card to get started and the first 10 GB of storage are free. A second VPS is not required.

If Backblaze is not suitable for your account or region, [Cloudflare R2](../backup-storage-cloudflare-r2.md) remains a supported alternative. The main chapter uses B2 so the default path does not depend on adding an international payment card.

## Before you begin

You need:

- the working Coolify installation from chapter 1;
- the test PostgreSQL database from chapter 4;
- a local `solo-vps` checkout on your workstation;
- the age/SOPS setup from chapter 3;
- a Backblaze B2 account.

If you already deleted the chapter-4 test database, repeat its steps 1–2 first. Restore targets in this chapter must still be separate disposable databases.

One private B2 bucket can be used by both Coolify and restic because they create different object paths. You can split them into separate buckets/keys later if you want stronger isolation.

## 1. Create an account and private Backblaze B2 bucket

Create a free Backblaze account and enable B2 Cloud Storage. A payment card is not required to get started.

Choose the account region during signup. If the VPS is in Europe, choose a European region when available. The account is tied to its region, and the bucket endpoint uses that region.

After sign-in open **B2 Cloud Storage → Buckets → Create a Bucket**.

Use:

| Setting | Value |
| --- | --- |
| Bucket name | a unique name such as `solo-vps-backups-abc123` |
| Files in Bucket are | `Private` |
| Object Lock | leave disabled for the first test |

A public bucket is not needed.

After creation, copy the **Endpoint** shown for the bucket. It looks like:

```text
s3.<REGION>.backblazeb2.com
```

For Coolify and Solo VPS use it with `https://`:

```text
https://s3.<REGION>.backblazeb2.com
```

Also save `<REGION>`, the segment between `s3.` and `.backblazeb2.com`.

## 2. Create an Application Key for only the backup bucket

Open **B2 Cloud Storage → Application Keys → Add a New Application Key**.

Use:

| Field | Value |
| --- | --- |
| Name of Key | `solo-vps-backups` |
| Allow Access to Bucket(s) | only the backup bucket |
| Type of Access | `Read and Write` |
| Allow List All Bucket Names | enabled |
| File Name Prefix | leave empty |
| Duration | leave empty for a persistent key |

`Allow List All Bucket Names` is needed by some S3 clients and connection checks. Object access remains restricted to the selected bucket.

Select **Create New Key** and save these values in a password manager:

- **keyID** — use it as the `Access Key ID`;
- **applicationKey** — use it as the `Secret Access Key`.

The `applicationKey` is shown only once. Do not commit these values or paste them into chat.

## 3. Add Backblaze B2 to Coolify

In Coolify open **S3 Storages → Add**.

Use:

| Field | Value |
| --- | --- |
| Name | `solo-vps-b2` |
| Endpoint | `https://s3.<REGION>.backblazeb2.com` from the bucket |
| Bucket | exact B2 bucket name |
| Region | `<REGION>` from the endpoint, for example `us-west-004` |
| Access Key | Backblaze `keyID` |
| Secret Key | Backblaze `applicationKey` |

Select **Validate Connection & Continue**.

Do not continue until validation succeeds. If you get `403`, first check that the Application Key is **Read and Write**, is restricted to the intended bucket, and has **Allow List All Bucket Names** enabled.

## 4. Upload the PostgreSQL backup to B2

Open the existing schedule under **`solo-vps-db-demo → Backups`**.

Under **S3**:

1. enable **S3**;
2. select `solo-vps-b2`;
3. leave **Disable Local Backup** off;
4. set a reasonable S3 retention such as `7` backups;
5. select **Save**.

In the source database Terminal run:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "DELETE FROM solo_vps_backup_probe WHERE id IN (3,4); INSERT INTO solo_vps_backup_probe VALUES (3, 'before-offsite'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Confirm that `3|before-offsite` is present, then select **Backup Now**.

The useful result is:

```text
Success
Backup Availability: Local Storage, S3 Storage
```

`Success (S3 Warning)` does not complete this chapter because the remote upload failed.

Open **Backblaze → B2 Cloud Storage → Buckets → your bucket → Browse Files** and confirm that a new Coolify backup object exists.

## 5. Restore PostgreSQL directly from S3

First change the source database **after** the external backup was created:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "INSERT INTO solo_vps_backup_probe VALUES (4, 'after-offsite'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

The source now contains `4|after-offsite`, while the B2 object was created earlier.

Create a **fresh, empty** PostgreSQL resource in Coolify with the **same major version**, for example `solo-vps-db-offsite-restore`. Do not connect the application to it. Use a new disposable resource for each restore exercise. Coolify runs `pg_restore` without clearing existing tables first; errors such as `relation already exists` or `duplicate key` mean the restore failed, even if the confirmation warns that existing data will be replaced.

Open **Configuration → Import Backup**.

If the UI offers an S3 restore:

1. choose **S3 storage** and select `solo-vps-b2`;
2. in **Backblaze → Browse Files**, copy the full object key of the backup you just uploaded. It resembles `data/coolify/backups/databases/.../pg-dump-....dmp`. If copying the path from Coolify's **Backups → Executions** instead, remove only its leading `/`;
3. enter that key in **File path**, select **Check File**, and require **File found in S3** with a positive size;
4. select **Restore From S3** and confirm the restore into the empty disposable database with your Coolify account password.

This is the primary path: Coolify reads the external backup directly from B2, so no local `.dmp` on the workstation is required. Check the restore output for `pg_restore` errors before treating it as successful.

If your Coolify version does not offer the S3 option, download the `.dmp` from **Backblaze → Browse Files** and use **Restore from File → Restore Database from File**.

In the restored database Terminal run:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "SELECT id, value FROM solo_vps_backup_probe WHERE id IN (3,4) ORDER BY id;"
```

Expect only:

```text
3|before-offsite
```

`4|after-offsite` must be absent. This proves that the external S3 backup restores the saved point in time.

For an extra independent-access check, you can also download the same `.dmp` directly from Backblaze once. That is useful but not required when the direct S3 restore already passed.

## 6. Back up the Coolify control plane to B2

An application PostgreSQL backup does **not** contain Coolify projects, resources, settings or stored credentials.

Open **Settings → Backup** in Coolify.

If **Configure Backup** is shown, select it. If Coolify first asks you to validate the localhost server, use **Validate Server** and return to Backup.

Under Scheduled Backup:

1. enable **Backup Enabled**;
2. keep a daily schedule;
3. enable **S3 Enabled**;
4. select `solo-vps-b2`;
5. leave **Disable Local Backup** off;
6. save;
7. select **Backup Now**.

The execution must finish as **Success** and show **S3 Storage** under **Backup Availability**.

Confirm that a separate Coolify instance backup object appears in B2.

## 7. Save APP_KEY outside the VPS

Coolify encrypts stored secrets with its `APP_KEY`. The panel `.dmp` is not sufficient to recover those credentials without this key.

**On the VPS as the configured administrator:**

```bash
sudo grep '^APP_KEY=' /data/coolify/source/.env
```

Copy the complete `APP_KEY=...` line into a password manager or other protected storage outside the VPS.

`APP_KEY` is a secret. The command above displays it only so you can move it into the password manager. Do not paste that output into an issue, chat, public log or screenshot; redact the value in evidence.

Do not store it in Git, as a plaintext B2 object, or only on the VPS itself.

## 8. Configure the Solo VPS B2 repository

Coolify backups and restic are separate mechanisms. Now use the same private bucket for the encrypted filesystem snapshot.

**On the VPS as the configured administrator:**

```bash
cd ~/solo-vps
nano ~/.local/share/solo-vps/config/config.yml
```

The file already contains a `backup` section. **Edit the existing `backup.repository`; do not add a second top-level `backup:` key.**

```yaml
backup:
  repository:
    endpoint: https://s3.<REGION>.backblazeb2.com
    bucket: <BUCKET_NAME>
    prefix: solo-vps
    region: <REGION>
```

Use the exact endpoint and region from the Backblaze bucket.

Save the file and run:

```bash
make check-backup-policy
make backup-tooling
make verify-backup-tooling
make backup-readiness
```

`backup-readiness` checks the local scope and policy without writing to B2.

## 9. Prepare restic credentials on the workstation

Do **not** create a new age key. Reuse the key already verified in chapter 3.

**Windows PowerShell, in the local `solo-vps` directory:**

```powershell
.\scripts\windows\init-sops-policy.ps1
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
```

`init-backup-secrets.ps1` asks for:

- Access Key ID — the Backblaze `keyID`;
- Secret Access Key — the Backblaze `applicationKey`;
- whether the provider uses a session token — answer `N` for normal Backblaze B2.

The restic repository password is generated automatically and stored only inside the SOPS-encrypted bundle.

Push the credentials to the VPS:

```powershell
$ServerIp = 'YOUR_SERVER_IP'
$AdminUser = 'YOUR_ADMIN_USER'
.\scripts\windows\push-backup-secrets.ps1 -VpsHost $ServerIp -VpsUser $AdminUser
```

**On the VPS:**

```bash
cd ~/solo-vps
make verify-backup-credentials
```

No secret value should be printed.

## 10. Initialize the restic repository and create a snapshot

**On the VPS as the configured administrator:**

```bash
make backup-runtime
make verify-backup-runtime
```

Choose **exactly one** repository command. Do not run both one after another.

If this restic repository has never existed:

```bash
make backup-repository-init
```

After `PASS restic repository initialized`, go straight to the snapshot; `backup-repository-adopt` is not needed.

If you are replaying the chapter and the repository already exists with the same credentials/password, use this **instead of init**:

```bash
make backup-repository-adopt
```

After initialization **or** adoption succeeds, create and inspect the snapshot:

```bash
make backup-now
make backup-status
```

B2 now contains a restic repository under the `solo-vps/<server-hostname>/` prefix. Its object names are intentionally technical; do not edit them manually.

It is normal for one bucket to contain two independent branches now:

```text
data/coolify/backups/...              Coolify: PostgreSQL and control-plane backups
solo-vps/<hostname>/config            restic repository metadata
solo-vps/<hostname>/{data,index,keys,locks,snapshots}
                                      restic internal objects
```

Do not delete individual `config`, `data`, `index`, `keys`, `locks` or `snapshots` objects from the Backblaze UI. Manage the restic repository only through Solo VPS/restic commands.

## 11. Prove a real restic restore

A snapshot is useful only after restore verification:

```bash
make backup-restore-test
```

Solo VPS restores the latest snapshot into a private temporary directory under `/var/tmp`, verifies the expected `/data/coolify` scope, and removes the test tree.

Expect:

```text
PASS Solo VPS filesystem recovery-material restore test
```

The test never overlays data onto the running Coolify installation.

## 12. Enable the daily restic backup

Only after the restore test succeeds:

```bash
make backup-schedule-enable
```

Check the timer:

```bash
systemctl list-timers solo-vps-backup.timer --no-pager
```

The default schedule runs daily around `03:15` with a small randomized delay.

## 13. Back up the age private key separately

The SOPS-encrypted `backup.enc.yaml` contains the storage credentials and restic password, but it can only be opened with your age private key.

On Windows the key is stored at:

```text
%USERPROFILE%\.config\solo-vps\age-key.txt
```

Keep a **protected copy outside both the VPS and the only workstation**, for example as an encrypted password-manager attachment or on encrypted removable storage.

Do not print the private key just to test this step, and do not upload it to Git or B2 as plaintext.

## What is protected now

| Loss | Recovery input |
| --- | --- |
| application PostgreSQL data | Coolify `.dmp` in B2 |
| Coolify projects/settings/history | Coolify instance `.dmp` in B2 + saved `APP_KEY` |
| required `/data/coolify` files | encrypted restic repository in B2 |
| restic/S3 credentials | SOPS-encrypted `backup.enc.yaml` + separate age private-key copy |
| application source | Git repository / published image |

Restic intentionally does **not** make a raw backup of a live PostgreSQL data directory. Databases use the separately tested Coolify logical backups.

A complete lost-VPS replacement is still a different exercise because it requires another host. We perform that destructive rehearsal later on a disposable VPS, not on the working server.

**Done:** this chapter is complete when a PostgreSQL backup has been downloaded from B2 and restored, a Coolify instance backup is visible in B2, `make backup-restore-test` passes, and the daily restic timer is enabled.

## Alternative S3 providers

The guided path in this chapter uses Backblaze B2. If it is unavailable for your account or region, use another S3-compatible provider with a private bucket, bucket-scoped credentials and an independent failure domain.

A ready alternative guide is available for [Cloudflare R2](../backup-storage-cloudflare-r2.md).
