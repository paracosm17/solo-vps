# Manage infrastructure secrets with SOPS + age

Solo VPS uses SOPS + age for a **small set of infrastructure and recovery secrets**. It does not require Vault, a second server, or an always-on secrets service.

The model is:

```text
one home workstation (Windows or Linux)
  ├── one age private key
  ├── public SOPS policy/recipient
  └── encrypted Solo VPS secret bundles

one VPS
  └── only the root-only runtime credentials each feature needs
```

Normal application runtime secrets belong in Coolify. CI-only secrets belong in GitHub. The production age private key stays on the workstation.

## What SOPS protects

Current encrypted bundles include:

```text
backup.enc.yaml           restic/S3 runtime credentials
observability.enc.yaml    Grafana Cloud Logs credentials
metrics.enc.yaml          Grafana Cloud Metrics credentials
```

Ciphertext and public recipient/policy metadata may be backed up safely according to your operator policy. Losing every copy of the age private key makes ciphertext unrecoverable.

## Windows workstation

If PowerShell blocks scripts from an Internet-downloaded checkout, unblock only the project helpers:

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
```

This removes the Internet-origin mark from these project scripts; it does not change the PowerShell execution policy. `RemoteSigned` is fine and does not need to be replaced with `Unrestricted`. If the helpers are still blocked after unblocking, run `Get-ExecutionPolicy -List`: a `MachinePolicy` or `UserPolicy` set by an organization can override your local settings and must be handled by that administrator.

Install the checksum-pinned project tools:

```powershell
.\scripts\windows\install-secrets-tools.ps1
```

Prepare the production age identity:

```powershell
.\scripts\windows\new-age-key.ps1
```

The command is idempotent: an existing key is validated and kept without replacement. The helper also restricts the directory and file NTFS ACL to the current user, `SYSTEM`, and local administrators.

The private file lives under:

```text
%USERPROFILE%\.config\solo-vps\age-key.txt
```

Back it up somewhere you control. Do not commit it and do not copy it to the VPS.

Initialize the persistent public SOPS policy:

```powershell
.\scripts\windows\init-sops-policy.ps1
```

The generated public policy/recipient state lives outside the Git checkout under `%LOCALAPPDATA%\solo-vps\state\sops\`. Re-running with the same key is safe. If state from another key remains, the helper prints both recipients and the encrypted-bundle count. Recover the previous private key when you need those old secrets. If you are deliberately repeating setup and only need a clean active state, use `-StartFresh`: the policy and `*.enc.yaml` files are moved to `%LOCALAPPDATA%\solo-vps\archive\workstation-secrets\<timestamp>\`, while the current private key is left untouched.

Prove the production key with non-sensitive temporary data:

```powershell
.\scripts\windows\test-age-key.ps1
```

## Linux workstation

Install/check the pinned tools in the Solo VPS user cache:

```bash
make secrets-tools
make check-secrets-tools
```

Create one production age key on the workstation:

```bash
mkdir -p ~/.config/solo-vps
chmod 700 ~/.config/solo-vps
age-keygen -o ~/.config/solo-vps/age-key.txt
chmod 600 ~/.config/solo-vps/age-key.txt
```

Show the public recipient:

```bash
age-keygen -y ~/.config/solo-vps/age-key.txt
```

Initialize the external public policy:

```bash
make init-sops-policy SOPS_AGE_RECIPIENT='age1...'
```

For manual SOPS operations, point `SOPS_AGE_KEY_FILE` at the workstation private key and use the policy path printed by `make paths`.

## Prove the private key is absent from the VPS

**Where: VPS, as the managed administrator**

```bash
make verify-vps-secrets-boundary
```

This is read-only. It checks the standard Solo VPS/SOPS key locations for the managed admin and root; it does not scan or delete arbitrary files.

Expected result:

```text
production age private identity on VPS: absent
```

## Backup credential bundle

The encrypted backup bundle is `backup.enc.yaml`. Create/check it on the workstation and push only decrypted runtime values to the VPS over SSH stdin.

Linux:

```bash
make backup-secrets-init
make backup-secrets-check
make backup-secrets-push BACKUP_VPS_HOST=<VPS-IP> BACKUP_VPS_USER=<admin-user>
```

Windows:

```powershell
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
.\scripts\windows\push-backup-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

The **age private key remains on the workstation**. See [restic off-site backups](backups-restic.md).

## Grafana Cloud credential bundle

The optional retained-log profile uses `observability.enc.yaml` for Grafana Cloud credentials.

Linux:

```bash
make observability-secrets-init
make observability-secrets-check
make observability-secrets-push OBSERVABILITY_VPS_HOST=<VPS-IP> OBSERVABILITY_VPS_USER=<admin-user>
```

Windows:

```powershell
.\scripts\windows\init-observability-secrets.ps1
.\scripts\windows\test-observability-secrets.ps1
.\scripts\windows\push-observability-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

See [Professional observability](operations/observability.md).

## Repository policy

The public repository contains only templates/placeholders such as `.sops.yaml.example` and public recipient examples. Operator-specific public recipients, encrypted personal infrastructure state, or private keys do not belong in upstream source.

SOPS encrypts files at rest. It does not make a runtime credential invisible to `root` on the VPS after that credential has been intentionally installed for a service.

## Recovery rule

Keep at least one protected backup copy of the workstation age private key. Disaster recovery may restore encrypted bundles from the recovery kit/off-site copy, but those files are useless without the corresponding private identity.
