# Export an encrypted Coolify backup

Run **on your workstation in Bash/WSL**, from the Solo VPS source directory. One command creates a fresh Coolify control-plane backup, downloads it over SSH and saves a verified `.tar.gz.age` file locally. It does not require S3 or the optional restic profile.

## Contents and limits

The archive contains the Coolify database (custom-format PostgreSQL dump), source configuration, server SSH keys, proxy configuration/certificates, operator config/inventory and platform container metadata. An inner manifest records the source revision, capture time and individual file SHA256 values.

**Application databases and volumes are excluded.** Keep [PostgreSQL backups](postgresql-backups.md) and [off-site data backups](offsite-backups.md) separately. This export also excludes Docker images, access logs, historical checkpoints and workstation SSH/age identities. A fresh export replaces the need to bundle previous upgrade checkpoints; it never removes them.

Capture is not atomic across the database and configuration files. Let deployments finish and pause upgrades/settings changes while exporting. A successful dump listing and decrypted-file verification prove archive integrity, not a complete restore. There is no automatic restore/downgrade command for this bundle; see [recovery boundaries](../upgrades.md#rollback-and-recovery).

## Prepare once

Use the existing administrator SSH key and a verified host key in your workstation's `known_hosts`. Password prompts are disabled. The administrator must have noninteractive sudo, as configured by Solo VPS. The default remote paths are `/home/<admin>/solo-vps` and `/home/<admin>/.local/share/solo-vps`; the latter must contain `config/config.yml` and `config/hosts.yml`.

The platform must be healthy. The collector is sent as temporary Python code over SSH; installing this feature's source on the VPS is unnecessary.

Keep your age identity on the workstation at `~/.config/solo-vps/age-key.txt`, or provide `AGE_KEY_FILE`. Install the project's checksummed crypto tools:

```bash
make secrets-tools
```

## Export

With the existing single-host inventory on your workstation:

```bash
make coolify-backup-export
```

For a server that runs its own Solo VPS controller, specify its endpoint instead of maintaining a second workstation inventory:

```bash
make coolify-backup-export BACKUP_VPS_HOST=203.0.113.10 BACKUP_VPS_USER=ops
```

The command prints the final local path, by default under the workstation's `make paths` data root in `backups/`. **The file is already downloaded.** No SCP step is needed. Private age key material never travels to the VPS; plaintext archives are never written to workstation disk. Temporary collection files on the VPS are private and removed after this invocation, including failure; previous checkpoints/backups are retained.

To save directly to a Windows directory in WSL:

```bash
make coolify-backup-export \
  BACKUP_VPS_HOST=203.0.113.10 BACKUP_VPS_USER=ops \
  AGE_KEY_FILE=/mnt/c/Users/YOUR_USER/.config/solo-vps/age-key.txt \
  COOLIFY_BACKUP_OUTPUT=/mnt/c/Users/YOUR_USER/solo-vps-backups/pre-update.tar.gz.age
```

The output must be a new `.age` path outside the source checkout; existing files are never overwritten. For custom layouts use `COOLIFY_BACKUP_REMOTE_DATA_DIR`, `COOLIFY_BACKUP_REMOTE_SOURCE` and, when necessary, `BACKUP_SSH_IDENTITY_FILE`. Inventory fallback supports exactly one direct host with host/user, optional port/private-key path, and no inherited or custom Ansible connection settings.

Normal errors clean up this invocation's temporary files. A killed process or lost connection can leave private staging or a local `.partial`; retry with a new output name and inspect ownership before removing leftovers. The transfer is not resumable.

Before publishing the final filename, the exporter checks collection/encryption exit codes, decrypts locally to compare the full received SHA256, then streams a second verification of every archived member against the manifest. A failed invocation leaves no successful-looking final backup. Keep your age identity separately backed up; losing it makes this archive unreadable.
