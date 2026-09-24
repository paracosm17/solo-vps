# Verify the managed platform

`make verify` is the normal read-only confidence check after installation and after meaningful host/platform changes.

## Run verification

**Where: managed VPS/controller**

```bash
make verify
```

The target runs local capability diagnostics first, then verifies the implemented host/platform state without changing desired configuration.

## What it covers

The composed verification checks the pieces Solo VPS currently owns or can safely inspect, including the managed administrator, SSH-related state, firewall/update baseline, Docker host, and installed platform state.

Use the subsystem checks when you need a narrower answer:

```bash
make verify-ssh
make verify-coolify
```

## Verification is not an availability test

A passing `make verify` does not prove that:

- your public DNS is correct;
- the application serves real traffic;
- an external monitor can see the service;
- off-site backups exist;
- a restore succeeds;
- a destroyed VPS can be recovered.

Those require external/application-specific proof.

## Pair verification with the security audit

After provisioning, upgrades, recovery, or networking changes, run:

```bash
make verify
make audit
```

Both are intended to be read-only. The audit focuses on exposure and security controls rather than duplicating every verification check.

## Related

- [Security audit](security-audit.md)
- [External uptime](operations/external-uptime.md)
- [Backup and recovery](backups-restic.md)
