# Coolify backups: local archive or workstation export

These commands back up the **Coolify control plane**: its PostgreSQL dump, source configuration, server SSH keys, proxy configuration/certificates, operator config/inventory and platform metadata. Individual files have SHA256 values in an inner manifest.

**Application databases and volumes are separate.** Keep [PostgreSQL backups](postgresql-backups.md) and [off-site data backups](offsite-backups.md). Docker images, access logs, historical checkpoints and workstation identities are excluded. Pause deployments/upgrades/settings changes during capture; database and files are not captured atomically. These archives have no automatic full-VPS restore or database downgrade command.

## Choose where the file should be created

| Command | Runs on | Result |
| --- | --- | --- |
| `make coolify-backup-local` | VPS, as the existing administrator | Local `.tar.gz.age`; no download or private identity required |
| `make coolify-backup-export` | Linux/WSL workstation | Downloaded `.tar.gz.age`, with local decryption verification |

Both use a shared nonblocking capture lock, validate the dump and archive members, check process exit codes and publish a new file atomically. Existing files are never overwritten or pruned. The platform must be healthy and have no pending install/upgrade transaction.

## Local backup on the VPS

### Prepare once

Your private age identity stays on your workstation. Obtain its **public recipient** (`age1...`) from your existing public SOPS recipient file or the output of the workstation age setup. Do not generate a new identity on the VPS or copy `age-key.txt` there.

On the VPS, as the existing administrator, from `~/solo-vps`:

```bash
make coolify-backup-local-prepare SOPS_AGE_RECIPIENT=age1YOUR_PUBLIC_RECIPIENT
```

This reuses the existing public SOPS policy/recipient file and installs/checks pinned age tools. No S3 or restic configuration is required. A different existing recipient is not overwritten: investigate the current key before using the documented rotation procedure. With custom controller paths, use the same `SOLO_VPS_DATA_DIR` as the installed controller.

### Create

```bash
make coolify-backup-local
```

The command prints the path and ciphertext SHA256. By default the file is under the current administrator's external data root, `~/.local/share/solo-vps/backups/`, with a unique timestamp/name and permissions `0600`. Only collection runs with noninteractive sudo; run the Make command without `sudo`.

The server validates the plaintext dump/archive and the stream **before encryption**. It cannot decrypt the result with its public recipient. After copying a backup off-host, verify decryption using your separately held private identity; an isolated dump restore supplies additional recovery evidence. Retain the identity separately: losing it makes the backups unreadable.

For a specific new filename use `COOLIFY_BACKUP_OUTPUT=/protected/path/backup.tar.gz.age`, outside the source checkout.

### Windows without WSL

The Make/crypto helper is Linux-only; it is not a native PowerShell command. From Windows PowerShell with OpenSSH and the existing administrator key/verified host key, you can run the **VPS command remotely**, then copy the ciphertext with native SCP:

```powershell
ssh ops@203.0.113.10 'cd ~/solo-vps && make coolify-backup-local'
scp 'ops@203.0.113.10:/home/ops/.local/share/solo-vps/backups/EXACT_FILE.tar.gz.age' "$env:USERPROFILE\solo-vps-backups\"
```

Use the exact printed filename and an existing local destination directory. The private age identity remains on Windows. This is native SSH/SCP transport to a Linux command, not native Windows execution of Make or the exporter.

### Optional schedule

After the first successful capture and off-host verification, the administrator may add this example to **their own** `crontab -e` (every six hours):

```cron
0 */6 * * * /usr/bin/make -C /home/ops/solo-vps coolify-backup-local >> /home/ops/.local/share/solo-vps/backups/cron.log 2>&1
```

Adjust paths and interval. No schedule is enabled automatically. Local files consume disk and do not survive VPS loss; arrange off-host copies and your own retention. This command never deletes old backups. An overlapping capture fails instead of starting another dump.

## Workstation export in Linux/WSL

Use the existing administrator SSH key, verified `known_hosts`, noninteractive sudo and local identity at `~/.config/solo-vps/age-key.txt` (or `AGE_KEY_FILE`). Install pinned crypto tools once with `make secrets-tools`. The temporary collector is sent over SSH; this feature's source need not be installed on the VPS.

With the existing single-host inventory:

```bash
make coolify-backup-export
```

For a VPS-hosted controller, specify its endpoint instead of maintaining a second inventory:

```bash
make coolify-backup-export BACKUP_VPS_HOST=203.0.113.10 BACKUP_VPS_USER=ops
```

The default remote paths are `/home/<admin>/solo-vps` and `/home/<admin>/.local/share/solo-vps`. For custom paths use `COOLIFY_BACKUP_REMOTE_SOURCE` and `COOLIFY_BACKUP_REMOTE_DATA_DIR`. Inventory fallback accepts one direct host with optional port/private-key path, without inherited/custom connection settings; explicit keys use `BACKUP_SSH_IDENTITY_FILE`.

To save directly to Windows from WSL:

```bash
make coolify-backup-export \
  BACKUP_VPS_HOST=203.0.113.10 BACKUP_VPS_USER=ops \
  AGE_KEY_FILE=/mnt/c/Users/YOUR_USER/.config/solo-vps/age-key.txt \
  COOLIFY_BACKUP_OUTPUT=/mnt/c/Users/YOUR_USER/solo-vps-backups/pre-update.tar.gz.age
```

**The file is already downloaded.** This mode verifies authenticated decryption, whole-stream SHA256 and every manifest entry locally before publishing its final filename. Plaintext archives are never written to workstation disk.

## Failures and recovery limits

Ordinary errors clean only this invocation's private staging and `.partial`; previous backups/checkpoints stay intact. A killed process or broken connection may leave those temporary files: inspect ownership before removing them and retry with a new name. No stream resume is provided. Shared capture locking does not replace pausing deployment/settings changes. See [recovery boundaries](../upgrades.md#rollback-and-recovery); a valid archive alone is not a full restore exercise.
