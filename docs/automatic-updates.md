# Automatic security updates

Solo VPS enables unattended Ubuntu security updates while deliberately leaving automatic reboot disabled.

## Policy

The managed unattended-upgrades policy allows the Ubuntu release/security origins used by the host baseline and excludes broad `-updates`, `-proposed`, `-backports`, PPAs, and unrelated third-party repositories from the automatic security path.

Docker and Coolify use separate, explicit lifecycle policies; they are not silently upgraded by Ubuntu unattended-upgrades.

## Reboot policy

Automatic reboot is disabled. If Ubuntu reports that a reboot is required, schedule it when you can verify the platform afterward.

After a reboot:

```bash
make verify
make audit
```

and confirm your public application health endpoint externally.

## Apply and verify

The update policy is part of the normal host lifecycle:

```bash
make apply
make verify
```

## Why this is conservative

Security patches should arrive without turning host/platform version changes into an unreviewed chain reaction. Docker major versions, Coolify versions, and project dependencies therefore remain explicit upgrade decisions.

## References

- Ubuntu unattended-upgrades documentation: <https://help.ubuntu.com/community/AutomaticSecurityUpdates>
