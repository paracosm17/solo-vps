# Firewall and public ports

Solo VPS uses UFW as the **host-input baseline**. The current core profile supports public SSH plus the HTTP/HTTPS edge needed by Coolify applications.

## Current policy

The managed SSH port is:

```text
22/tcp
```

The configurable public application ports are currently limited to:

```yaml
firewall:
  public_ports:
    - 80
    - 443
```

Arbitrary public host ports are intentionally not a generic configuration feature in the alpha profile.

## Apply and verify

The firewall is applied by the normal host lifecycle:

```bash
make apply
make verify
make audit
```

Keep your existing provider session and provider console/rescue path available during first application.

## Docker is a separate exposure boundary

A UFW rule list is not enough to prove that every Docker-published port is private. Solo VPS audits Docker publication separately.

For the default Coolify profile:

- `80/443` are the public application edge;
- `8000/6001/6002` are expected to be loopback-only;
- application container ports such as `8080` should normally be internal Docker ports, not host publications.

## Provider firewall

Your cloud/provider firewall or security group is outside Solo VPS automation. Keep it aligned with the intended public edge and provider recovery model.

## Recovery

If firewall changes break SSH, use provider console/rescue access. Do not permanently broaden the firewall until you understand which rule or publication caused the failure.

## Related

- [SSH hardening](ssh-hardening.md)
- [Security audit](security-audit.md)
- [Coolify installation](coolify-installation.md)
