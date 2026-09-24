# Recover from a lost VPS

This is the supported recovery model when the **old VPS is lost** and you must rebuild on a **fresh Ubuntu 24.04** replacement.

> Current status: the source-side procedure is implemented, but the alpha release still needs the complete destroyed-VPS replacement exercise with real off-site data.

## Recovery sequence

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

## What must survive outside the old VPS

Before you can claim disaster-recovery readiness, keep these independently recoverable:

1. a reviewed Solo VPS release/source revision;
2. an off-VPS recovery kit;
3. the workstation age private identity and its separate backup;
4. the managed off-site restic repository and encrypted backup credentials;
5. a **Coolify instance database backup** outside the VPS;
6. application PostgreSQL logical backups outside the VPS;
7. Git repositories and **immutable** GHCR image artifacts;
8. DNS/provider account access.

If an application stores important data in **arbitrary persistent volumes**, the core alpha does not automatically protect that data. Add an application-specific backup/restore procedure.

## 1. Export and copy the recovery kit before disaster

Create a kit to a protected path:

```bash
make recovery-kit-export \
  RECOVERY_KIT_OUTPUT="$HOME/solo-vps-recovery-kit.tar.gz" \
  RECOVERY_SOURCE_REVISION='<release-or-reviewed-revision>'
```

Copy that archive **off the VPS**, then verify the copied file there:

```bash
make recovery-kit-verify \
  RECOVERY_KIT_OUTPUT=/path/to/copied/solo-vps-recovery-kit.tar.gz
```

The kit may contain config, SOPS public policy/ciphertext, and small controller state. It never contains the age private key, SSH private keys, or plaintext storage credentials.

## 2. Prepare the replacement VPS

Provision a clean Ubuntu 24.04 target and obtain the reviewed Solo VPS source revision.

Extract the verified recovery inputs into the external Solo VPS data root without overwriting existing files:

```bash
make recovery-kit-extract \
  RECOVERY_KIT_OUTPUT=/path/to/copied/solo-vps-recovery-kit.tar.gz
```

Update `server.host` to the replacement address. Keep the intended hostname stable when restoring the same installation identity.

Run the normal host lifecycle through the hardened administrator path:

```bash
make apply
make secure
```

## 3. Install Coolify fresh

Install the **same supported pinned Coolify version** as a new platform:

```bash
make platform
```

Do not overlay the old `/data/coolify` tree on top of a running fresh installation.

## 4. Stage the restic filesystem material

Install the backup runtime/credentials on the replacement and restore the selected snapshot into a **new private staging directory**:

```bash
RECOVERY_STAGING_ROOT=/var/tmp/solo-vps-disaster-recovery/recovery-<id> \
RECOVERY_STAGING_CONFIRM=I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY \
make backup-restore-staging
```

The target must be a new empty private path. The staged tree is input to the recovery procedure, not a direct overlay.

## 5. Inspect the Coolify instance backup and restore plan

```bash
make coolify-instance-restore-inspect \
  COOLIFY_INSTANCE_BACKUP_ARCHIVE=/path/to/coolify-instance.dmp

make coolify-instance-restore-plan \
  COOLIFY_INSTANCE_BACKUP_ARCHIVE=/path/to/coolify-instance.dmp \
  RECOVERY_STAGING_ROOT=/var/tmp/solo-vps-disaster-recovery/recovery-<id>
```

The actual destructive restore is intentionally safety-gated and reserved for the reviewed replacement target.

The supported restore keeps the **fresh** platform secrets where appropriate, restores the old Coolify instance database, restores the previous Coolify application encryption key through `APP_PREVIOUS_KEYS`, and restores the required Coolify SSH identities without authorizing every recovered key for localhost login.

## 6. Restore application PostgreSQL

Each protected application database needs its logical archive restored into the replacement database and verified with an application-relevant read-only query.

Use the procedure in [PostgreSQL backups and restore](database-backups.md).

Restoring the Coolify instance database does **not** restore application PostgreSQL contents.

## 7. Redeploy applications

Redeploy from reviewed Git/GHCR sources using exact **immutable** image identities. Do not depend on a mutable tag as disaster-recovery evidence.

Container-image rollback remains separate from database/schema recovery.

## 8. Repoint DNS and verify

If the public address changed, update DNS/provider routing. Then run:

```bash
make verify-coolify
make verify
make audit
```

Finally verify from outside the VPS:

- the public application health endpoint;
- expected application data after PostgreSQL restore;
- external uptime recovery notification;
- optional retained logs, if configured.

## Recovery is complete only when the application is useful

A replacement host that merely boots is not a successful recovery. The proof must establish that:

- Coolify metadata is usable;
- application PostgreSQL contains the expected data;
- immutable applications redeploy;
- public routing works;
- host verification and audit pass;
- the externally visible service is healthy.

## Important boundary

The restic filesystem snapshot, Coolify instance database, application PostgreSQL backups, recovery kit, Git/GHCR artifacts, and provider access are separate inputs by design. Losing the only VPS must not destroy every authority needed to rebuild it.
