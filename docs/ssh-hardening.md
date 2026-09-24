# Harden SSH safely

SSH hardening is deliberately separate from the initial host bootstrap. The goal is to remove risky bootstrap access **only after** the managed administrator and provider recovery path are proven.

## Before you begin

Do not run this procedure unless both statements are true:

1. you can open a **fresh** workstation SSH session as `admin.user` and `sudo -n id -u` returns `0`;
2. provider console/rescue access is available if SSH becomes unreachable.

Keep the existing working session open during the change.

## Activate hardening

**Where: retained VPS/controller session**

```bash
SSH_HARDENING_CONFIRM=I_HAVE_VERIFIED_PROVIDER_RECOVERY SSH_HARDENING_ADMIN_LOGIN_CONFIRM=I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN make secure
```

The underlying hardening workflow validates the generated OpenSSH configuration before activation, reloads SSH only after checks pass, and runs read-only verification afterward.

## Verify from a new session

**Where: workstation**

```bash
ssh <admin.user>@<server>
```

Then on the managed VPS/controller:

```bash
cd ~/solo-vps
make verify-ssh
make audit
```

Do not close the recovery/retained session until the new admin path is confirmed.

## If the hardening command fails

Stop and preserve the existing working session. Read the failure before changing files manually.

If SSH becomes unavailable, use the provider console/rescue path to inspect the managed SSH drop-in and restore access. Do not weaken the permanent policy merely to make an unexplained failure disappear.

## Why this is staged

An additive admin account is safe to create while the old path still works. Disabling bootstrap/root/password access is access-critical. Separating the two lets Solo VPS require concrete recovery and login proofs before it can make the second change.

## Related

- [Admin access](admin-access.md)
- [Security audit](security-audit.md)
- [Quick Start](quick-start.md)
