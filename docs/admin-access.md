# Configure administrative access

Solo VPS creates one managed non-root administrator and keeps two SSH identities separate:

- **automation identity** — used by the controller;
- **human workstation identity** — used by you for normal SSH access.

The human private key must remain on your workstation.

## Before `make apply`

Run `make setup` and edit the persistent config first. Then configure your human public key through the supported helper.

### Same-VPS/root-first flow

**Where: workstation**

Linux/macOS shell:

```bash
cat ~/.ssh/id_ed25519.pub | ssh <provider-user>@<server> 'cd ~/solo-vps && make human-admin-key-stdin'
```

PowerShell:

```powershell
Get-Content -Raw "$HOME\.ssh\id_ed25519.pub" | ssh <provider-user>@<server> "cd ~/solo-vps && make human-admin-key-stdin"
```

### Separate controller checkout

**Where: controller/workstation**

```bash
make human-admin-key-file HUMAN_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
```

The helper accepts exactly one OpenSSH public-key line, updates the persistent config atomically, and rejects private-key material.

## What `make apply` creates

The configured `admin.user` receives:

- a normal home directory and `/bin/bash` login shell;
- membership in Ubuntu's `sudo` group;
- `~/.ssh` mode `0700`;
- both configured public keys in `authorized_keys` mode `0600`;
- a managed `/etc/sudoers.d/90-solo-vps-<user>` fragment granting passwordless sudo after `visudo` validation.

This stage is intentionally additive. It does not harden the SSH daemon, disable root login, disable passwords, or delete pre-existing admin keys.

## Prove the human login before hardening

After `make apply`, open a **new** workstation session:

```bash
ssh <admin.user>@<server>
sudo -n id -u
```

Expected output:

```text
0
```

Also verify that provider console/rescue access is available. Keep the current working session open.

Only then continue to [SSH hardening](ssh-hardening.md).

## If the workstation login fails

Do not repair `authorized_keys` ad hoc. Re-run the public-key helper through a working provider/recovery path, then re-apply the additive identity state:

```bash
make bootstrap
make verify
```

If you are already using the five-command lifecycle, `make apply` is the preferred normal entry point.

## Security boundary

The automation and human keys must be distinct on same-VPS installs. A controller private key may exist on the VPS for local automation; the human private key must not.

Solo VPS preserves existing access during the additive stage because deleting an unknown working key before a new path is proven could create a lockout. SSH restrictions are applied only in the separate, safety-gated hardening step.
