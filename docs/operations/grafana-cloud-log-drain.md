# Rejected Coolify-native Grafana Cloud log-drain experiment

> **Historical / recovery reference.** This Rejected Coolify-native **Custom FluentBit** path is **not the maintained application-log setup**. New installations should use [Grafana Alloy + the restricted Docker API proxy](observability.md).

This page remains because an operator who previously enabled the experiment may need to diagnose or remove it safely.

## What the experiment did

The attempted path was:

```text
Coolify application
  -> local Fluent Bit receiver at 127.0.0.1:24224
  -> Custom FluentBit configuration
  -> Grafana Cloud Loki
```

The configuration used `service_name` and a selected `COOLIFY_APP_NAME` to make application logs searchable in Grafana Cloud.

## Before enabling or diagnosing it

Do not enable this on a fresh Solo VPS merely because this document exists. Use it only for a host that already carries this historical configuration or for a disposable reproduction.

You need the existing observability credential bundle and an ordinary Coolify installation. Keep tokens out of terminal history and clipboard history where possible.

## Windows workstation: copy the configuration without printing the token

The historical helper is:

```powershell
.\scripts\windows\copy-observability-log-drain.ps1
```

Paste only into the intended Coolify field, then **clear the clipboard**.

## Configure the server in Coolify

In Coolify, open:

**Configuration > Log Drains**

Use the **Advanced** / Custom FluentBit configuration that belongs to the experiment. Do not broaden Docker or host exposure to make the drain work.

## Enable log draining for one application first

Choose one disposable or low-risk application and enable **Drain Logs**. Record its `COOLIFY_APP_NAME`; do not opt every workload in before the single-app path is proven.

## Verify the local Coolify path

Run:

```bash
make verify-observability-log-drain
```

Expected result: the expected Coolify-side configuration and selected application opt-in are present without exposing the local collector publicly.

If the experiment has been disabled and you are validating cleanup:

```bash
make verify-observability-log-drain-disabled
```

## Verify Grafana independently

To prove the Grafana Cloud endpoint and credentials independently of Coolify, you can send one synthetic non-secret test record:

```bash
make test-observability-loki
```

This is an **EXTERNAL WRITE**. Use it only when you intend to create that synthetic log entry.

## Diagnose a missing receiver

If Coolify is configured but no local receiver appears at `127.0.0.1:24224`, run:

```bash
make diagnose-observability-log-drain
```

Do not publish the receiver port or change host firewall rules as a workaround. A missing loopback receiver is a runtime/configuration problem, not a reason to create a public listener.

## Roll back the experiment

Disable **Drain Logs** for opted-in applications, remove the Custom FluentBit configuration through Coolify, and then prove the historical collector is stopped:

```bash
make verify-observability-log-drain-disabled
```

Return to the maintained path in [Professional logs and metrics UX](observability.md).
