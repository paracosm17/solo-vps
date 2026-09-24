# Host diagnostic fallback: status and logs

Use these commands when Coolify or your normal observability UI is unavailable and you need a bounded, read-only host view.

## Quick host status

**Where: VPS/controller as the managed administrator**

```bash
make ops-status
```

This reports a concise host/container summary without changing desired state. The normal daily UI remains GitHub Actions for CI and Coolify for deployments, runtime logs, secrets and terminals.

## One container's recent logs

Choose one container explicitly:

```bash
make ops-logs CONTAINER=<container> TAIL=100
```

Use a bounded tail for diagnosis. This path is **read-only** and is a **fallback**, not the normal daily application-operations interface. Always **review before sharing** output because application logs can contain sensitive data.

## If the host view is not enough

Run the broader read-only checks:

```bash
make doctor
make verify
make audit
```

Then return to the owning UI:

- GitHub Actions for CI failure details;
- Coolify for deployment/application runtime state;
- Grafana for historical observability when enabled.

## Related

- [Daily operator UI](operator-ui.md)
- [Professional observability](observability.md)
- [Command reference](../command-reference.md)
