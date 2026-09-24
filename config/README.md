# Configuration reference

Solo VPS keeps public, non-secret desired state in a persistent YAML file created from `config/config.example.yml`.

Run:

```bash
make paths
```

to find the active file. By default it is:

```text
~/.local/share/solo-vps/config/config.yml
```

Edit the persistent copy, **not** the tracked example.

## `server`

```yaml
server:
  host: 203.0.113.10
  hostname: solo-vps-01
  timezone: UTC
```

### `server.host`

Type: string  
Required: yes

The SSH/Ansible target address. Use an IP address or hostname that the controller can reach.

### `server.hostname`

Type: string  
Required: yes

The Linux hostname Solo VPS applies to the managed VPS.

### `server.timezone`

Type: string  
Required: yes  
Default in the example: `UTC`

Use an IANA timezone such as `UTC` or `Europe/Riga`.

## `admin`

```yaml
admin:
  user: ops
  ssh_public_key_file: ~/.ssh/id_ed25519.pub
  human_ssh_public_key: ""
```

### `admin.user`

Type: string  
Required: yes

Managed non-root administrative account.

### `admin.ssh_public_key_file`

Type: path  
Required: yes

Public key for the controller/automation identity. A private key path is invalid.

### `admin.human_ssh_public_key`

Type: OpenSSH public-key line  
Required for the normal secure onboarding path: yes

Do not paste this value manually when the helper can set it safely:

```bash
make human-admin-key-file HUMAN_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
```

or use `make human-admin-key-stdin` in the same-VPS flow.

## `firewall.public_ports`

```yaml
firewall:
  public_ports:
    - 80
    - 443
```

The current alpha contract allows the HTTP/HTTPS application edge only. SSH port `22` is managed separately.

## `backup.repository`

Optional until off-site backups are configured:

```yaml
backup:
  repository:
    endpoint: https://s3.example.com
    bucket: solo-vps-backups
    prefix: solo-vps
    region: us-east-1
```

These are **non-secret repository coordinates**. Never put S3 access keys or the restic password in this file.

For Cloudflare R2, see [`../docs/backup-storage-cloudflare-r2.md`](../docs/backup-storage-cloudflare-r2.md).

## `ci_deploy`

Optional deployment-control transport:

```yaml
ci_deploy:
  ssh_public_key_file: ~/.ssh/solo-vps-ci-deploy.pub
```

Enable it only when intentionally configuring the dedicated restricted GitHub Actions deployment identity.

## Validate configuration

Use the normal diagnostics:

```bash
make doctor
```

Configuration validation is also included in the lifecycle commands that need it.

## Secret rule

Public config may contain hostnames, usernames, paths, public keys, and S3 repository metadata. It must not contain private SSH keys, age private identities, API tokens, database passwords, S3 secret keys, restic passwords, or application secrets.
