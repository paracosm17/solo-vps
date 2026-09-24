# Audit the security boundary

`make audit` is a read-only check focused on the security controls and network exposure that matter for the current Solo VPS profile.

## Run the audit

**Where: managed VPS/controller**

```bash
make audit
```

Treat a non-zero exit as a reason to stop and inspect the reported boundary before deploying or changing more state.

## What the audit is for

The audit answers questions such as:

- is the managed SSH policy in the expected state?
- are host firewall controls present?
- are Docker/Coolify publications consistent with the intended exposure model?
- are obvious database/cache management ports accidentally public?
- do optional observability components preserve their confidentiality boundary when enabled?

## UFW is not the whole network boundary

Docker-published ports can interact with packet filtering differently from ordinary host listeners. Solo VPS therefore reviews Docker publication separately instead of treating a passing UFW status as proof that every container port is private.

Loopback publications such as Coolify `8000/6001/6002` are expected to remain reachable only on `127.0.0.1` and unreachable through the target's public address.

## What a PASS does not prove

A local audit cannot prove provider-firewall policy, DNS correctness, WAF behavior, real external availability, backup recoverability, or application-level authorization.

Use external checks for those boundaries.

## Related

- [Firewall](firewall.md)
- [Coolify installation](coolify-installation.md)
- [Verification](verification.md)
- [External uptime](operations/external-uptime.md)
