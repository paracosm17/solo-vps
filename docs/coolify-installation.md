# Install and access Coolify

Solo VPS installs Coolify without giving the upstream installer ownership of SSH, Docker, or firewall configuration. The host stays Ansible-owned; Coolify owns application/runtime state under `/data/coolify`.

## Current pinned platform

```text
Coolify:           {{ solo_vps_coolify_target }}
image:             docker.io/coollabsio/coolify:{{ solo_vps_coolify_target }}
Docker support:    29.x
management bind:   127.0.0.1
management ports:  8000, 6001, 6002
data root:          /data/coolify
```

The version and first-install artifacts are project dependencies, not per-host configuration knobs.

## Before installation

Complete the host and SSH stages first:

```bash
make apply
make secure
```

Reconnect as `admin.user`, then run:

```bash
make doctor
make verify
make audit
```

The fresh-install path expects `/data/coolify` to be unused by an unrelated Coolify installation.

## Install the platform

**Where: managed VPS/controller as `admin.user`**

```bash
make platform
```

On a fresh host, `make platform` performs readiness checks, installs the pinned release and verifies its bootstrap health and private ports. Complete the first account, HTTPS dashboard and Sentinel setup before `make verify-coolify`. On a previously managed host, `make platform` also runs the full verification.

The separate Coolify Traefik proxy is restricted to public **TCP 80/443**. Solo VPS persists the port policy through Coolify’s native proxy configuration before first-install verification. Host port 8080 and UDP 443 are not published; HTTP/3 is outside this core network profile. Coolify continues to own routing, certificates and the base proxy configuration.

On an older installation, `make platform` also repairs a running proxy with extra published ports. This recreates the proxy and briefly interrupts HTTP/HTTPS traffic. It does not pull a new proxy image, restart application containers or regenerate Coolify credentials. If the saved Compose model would change the image or drop extra application networks, automatic recreation stops for review; restart through Coolify's proxy UI after reviewing its configuration, then rerun verification.

The readiness gate checks the current admin identity, supported Docker/Compose versions, host Docker config, minimum CPU/memory/disk, management-port availability, and existing Coolify state.

## What the installer owns

Solo VPS creates the pinned Coolify filesystem/runtime skeleton, generates first-install secrets without printing them, creates the localhost SSH identity used by Coolify, starts the pinned Compose model, and writes the managed marker only after health and exposure checks pass.

It deliberately keeps the management/realtime publications on loopback:

```text
127.0.0.1:8000 → Coolify web/API
127.0.0.1:6001 → realtime service
127.0.0.1:6002 → realtime service
```

Do not add public firewall rules for those ports.

## Create the first Coolify account

**Where: workstation**

Open an SSH tunnel from PowerShell or a Linux/macOS terminal. Local port 18000 leaves port 8000 available for the documentation site:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 <admin.user>@<server>
```

Then open:

```text
http://127.0.0.1:18000
```

Keep the tunnel terminal open; `-N` does not open a remote shell, so waiting without a prompt is normal. If SSH reports a forwarding error, resolve the local port conflict before opening the page. Create the first account through this private path.

After you configure a normal HTTPS dashboard domain, set **Servers → `server.hostname` → Sentinel → Configuration → Coolify URL** to that URL, leave debug off, enable and sync Sentinel, and wait for **Sentinel In Sync**. Raw management ports and Sentinel port `8888` remain private. See [Coolify dashboard domain and browser terminal](operations/coolify-dashboard-domain.md).

## Verify Coolify

**Where: VPS/controller**

```bash
make verify-coolify
make audit
```

Run this after Sentinel onboarding. Verification checks the managed marker, pinned Coolify and Sentinel identities, health endpoints, HTTPS Sentinel push configuration, localhost SSH integration, bounded filesystem permissions, Docker daemon ownership boundary, and loopback-only publications without printing secret values. Confirm **Sentinel In Sync** in the dashboard as the final delivery check.

## Idempotent second run

Once the installation is marked as Solo VPS-managed, a second:

```bash
make platform
```

reconciles only the supported integration state and verifies it. It does not intentionally regenerate first-install secrets or treat a rerun as an upgrade.


## If proxy/resource paths show permission errors

Do not recursively `chmod` or `chown` `/data/coolify` and do not repair one resource UUID manually.

Reconcile the supported integration:

```bash
make platform
make verify-coolify
```

If the failure is a local backup error containing `/data/coolify/backups/...: Permission denied`, the same `make platform`/`make verify-coolify` path restores the separate private write+traverse boundary required by non-root backup jobs. Do not broaden permissions across all of `/data/coolify`.

If the error remains, preserve the exact Coolify deployment/proxy/backup log and use it as a reproducible bug report.

## Interrupted first install

An interrupted unmarked first install is a recovery case, not a normal rerun. Use the explicit, reviewed recovery path documented in the command reference; never adopt unknown `/data/coolify` state automatically.

## Upgrades

A normal `make platform` does not upgrade Coolify. The supported alpha lifecycle is previous-supported `{{ solo_vps_coolify_origin }}` → current-supported `{{ solo_vps_coolify_target }}`; use the [Upgrade guide](upgrades.md) for the safety-gated procedure.

## Related

- [Deploy your first application](operations/first-app.md)
- [Daily operator UI](operations/operator-ui.md)
- [Architecture](architecture.md)

On repeated `make platform`, first-install readiness is skipped for a completed platform. Its own interrupted install with `.solo-vps-installing` resumes automatically, preserving existing secrets and the SSH key. Older transactions use the bounded recovery path. If the marker is absent or identity differs, inspect the original revision/config; unknown `/data/coolify` is not adopted. Interrupted upgrades require the separate `make coolify-upgrade-resume` path.
