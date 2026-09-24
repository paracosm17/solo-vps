# Back up Solo VPS with restic

Solo VPS uses restic for encrypted **off-site filesystem recovery material**. If you are setting this up for the first time, follow [Chapter 6: off-site backups](operations/offsite-backups.md); it combines Backblaze B2, database copies, the Coolify control-plane backup and the restic restore test in one sequence.

This page is the technical restic reference.

> Off-site storage does not mean a second VPS. A managed S3-compatible object store is enough; there is still only one application VPS to administer.

## What the core restic backup protects

The default filesystem source is:

```text
/data/coolify
```

with these exclusions:

```text
/data/coolify/ssh/mux
/data/coolify/databases
/data/coolify/backups
```

This is **Coolify filesystem/control-plane recovery material**, not a complete application-data backup.

Application PostgreSQL is protected separately through logical database backups. Arbitrary application persistent volumes need their own application-aware backup procedure.

## What you need

Before enabling backups:

- an S3-compatible bucket outside the VPS failure domain;
- bucket-scoped credentials;
- a workstation age identity and SOPS policy;
- non-secret repository coordinates in Solo VPS config;
- the managed admin path working.

If you do not have external storage yet, continue using the core platform and **skip backups for now**. The trade-off is explicit: disaster recovery is incomplete.

For the default provider example, see [Backblaze B2](backup-storage-backblaze-b2.md). [Cloudflare R2](backup-storage-cloudflare-r2.md) remains an alternative.

## 1. Configure repository metadata

**Where: persistent Solo VPS config**

```yaml
backup:
  repository:
    endpoint: https://s3.example.com
    bucket: solo-vps-backups
    prefix: solo-vps
    region: us-east-1
```

These values are public repository coordinates. Credentials do not belong here.

The effective repository path is derived per host from the endpoint, bucket, prefix, and `server.hostname`.

## 2. Install and verify restic

**Where: managed VPS/controller**

Solo VPS currently pins restic `0.19.1` and installs the checksum-verified binary as `/usr/local/bin/restic`.

```bash
make backup-tooling
make verify-backup-tooling
make backup-readiness
```

`backup-readiness` is read-only and does not contact the repository.

A pre-existing conflicting restic installation is treated as an ownership/migration decision rather than silently replaced.

## 3. Create encrypted backup credentials

The secret bundle contains:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN   optional
RESTIC_PASSWORD
```

The ciphertext stays outside the source checkout as `backup.enc.yaml`. The **age private key remains on the workstation**.

### Windows workstation

If required once for an Internet-downloaded checkout:

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
```

Initialize/recheck the persistent public SOPS policy:

```powershell
.\scripts\windows\init-sops-policy.ps1
```

Create and test the encrypted bundle:

```powershell
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
```

Push decrypted values over SSH stdin without creating a plaintext workstation file:

```powershell
.\scripts\windows\push-backup-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

### Linux workstation

```bash
make secrets-tools
make check-secrets-tools
make backup-secrets-init
make backup-secrets-check
make backup-secrets-push BACKUP_VPS_HOST=<VPS-IP> BACKUP_VPS_USER=<admin-user>
```

### Verify on the VPS

```bash
make verify-backup-credentials
```

The VPS runtime file is:

```text
/etc/solo-vps/backup/credentials.json
```

with root-only permissions. The helper verifies schema/metadata without printing secret values.

## 4. Install the backup runtime

**Where: managed VPS/controller**

```bash
make backup-runtime
make verify-backup-runtime
```

This installs the root-only runtime and systemd units. The schedules are not automatically enabled before repository/snapshot safety gates pass.

## 5. Initialize or adopt the repository

Choose **one** path.

### New empty repository

```bash
make backup-repository-init
```

This is an external write and fails if the repository already opens as an existing restic repository.

### Existing repository

```bash
make backup-repository-adopt
```

This checks that the configured repository is a usable existing restic repository before Solo VPS uses it.

## 6. Create the first real backup

```bash
make backup
```

`make backup` creates one encrypted snapshot and then runs the repository/freshness check.

For separate operations:

```bash
make backup-now
make backup-status
make backup-check
```

**Expected result**

The latest matching snapshot is fresh, the repository opens successfully, and the check completes without exposing credentials.

## 7. Prove a real restore

A snapshot is not recovery evidence until restore works.

```bash
make backup-restore-test
```

The test restores the latest matching snapshot into a temporary private directory under `/var/tmp`, verifies the expected scope, and removes the temporary test tree. It never overlays a running `/data/coolify` installation.

For lost-VPS recovery, the separate staged restore path intentionally retains the private recovered material for the replacement-host procedure. See [Recover from a lost VPS](disaster-recovery.md).

## 8. Enable schedules only after proof

After repository access, a fresh snapshot, and restore verification:

```bash
make backup-schedule-enable
```

The default daily backup timer runs around `03:15` with a randomized delay.

Review retention before enabling destructive maintenance:

```bash
make backup-retention-plan
```

Only after reviewing the dry run:

```bash
BACKUP_RETENTION_CONFIRM=I_HAVE_REVIEWED_THE_BACKUP_RETENTION_PLAN \
make backup-maintenance-schedule-enable
```

The retention/prune path is deliberately separate from normal backup creation.

## Backup security model

- credentials and the restic password never appear in public config;
- the production age private key stays on the workstation;
- the VPS receives only the root-only runtime credential material it needs;
- restic secrets are not passed as command-line arguments;
- `/var/lib/docker` and `/var/lib/postgresql` are not raw backup sources;
- a restic tree is never treated as a safe direct overlay onto fresh Coolify.

## What restic does not replace

You still need:

- a Coolify instance database backup;
- logical application PostgreSQL backups;
- immutable Git/GHCR artifacts for redeployment;
- a recovery kit outside the VPS;
- application-specific procedures for important persistent volumes.

See [Database-aware backups](database-backups.md) and [Lost VPS recovery](disaster-recovery.md).
