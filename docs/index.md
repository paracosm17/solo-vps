# Solo VPS

<p class="solo-home-intro" data-solo-home><strong>Set up an Ubuntu server and deploy applications from GitHub.</strong> Solo VPS configures administrator access, SSH, the firewall and Docker, then installs Coolify. The guides cover the server setup and automatic application delivery.</p>

The commands configure and verify the host; the guide covers the GitHub and Coolify steps. After setup, a `git push` can update the application while its status and logs stay visible in Coolify.

## Start here

If this is your first Solo VPS installation, complete the first two chapters in order. Then choose the operational chapters your application needs from the list below. You do not need to read the architecture or internal implementation first.

## Components

Solo VPS uses these components:

| Choice | Purpose |
| --- | --- |
| **Ubuntu 24.04 LTS + Ansible** | A stable server base and repeatable configuration |
| **SSH hardening + UFW + security updates** | A practical host-security baseline |
| **Docker + Coolify** | Containers plus a UI for deployments, domains, HTTPS, variables, databases and live logs |
| **GitHub Actions + GHCR** | Test, build and deploy applications from Git pushes |
| **SOPS + age** | Encrypted infrastructure and recovery secrets |
| **restic, external monitoring and Grafana Cloud** | Optional off-site recovery, outage alerts, retained logs and host metrics |

The setup runs on one VPS. Recovery has its own documented procedure.

## Installation path

The supported first-run path is intentionally small:

<div class="solo-command-path"><code>make setup</code><span>→</span><code>make apply</code><span>→</span><code>make secure</code><span>→</span><code>make platform</code><span>→</span><code>make verify</code></div>

The [Quick Start](quick-start.md) explains where each command runs, what it changes, and what successful output looks like.

## Responsibility boundaries

| Area | Owner |
| --- | --- |
| Ubuntu host baseline, SSH, firewall, Docker | **Solo VPS** |
| Application deployment and runtime configuration | **Coolify** |
| CI builds and image publishing | **GitHub Actions / GHCR** |
| Off-site storage and third-party accounts | **You** |
| Recovery procedure | **Solo VPS docs + your off-site credentials/backups** |

## Common tasks

**Follow the guided chapters:**

1. [Set up the VPS and Coolify](quick-start.md).
2. [Deploy an application and enable CI/CD](operations/first-app.md).
3. [Add retained logs](operations/observability.md) if you need them.
4. [Back up and restore PostgreSQL](operations/postgresql-backups.md) if you use a database.
5. [Set up external uptime monitoring](operations/external-uptime.md).
6. [Move backups off the VPS](operations/offsite-backups.md).
7. [Add VPS metrics](operations/metrics.md) if you want to watch resource use.

Choose chapters 3–7 to fit your application. [After basic setup](operations/after-basic-setup.md) explains their order and dependencies.

**Find a specific task:**

- Something fails before installation: [Preflight & doctor](preflight.md).
- Find deployments, variables or current logs: [Daily operations](operations/operator-ui.md).
- Check host status and bounded logs: [Status & logs](operations/status-and-logs.md).
- Handle an incident or planned maintenance: [Failures and maintenance](operations/incidents-and-maintenance.md).
- Replace a lost VPS: [Lost VPS recovery](disaster-recovery.md).
- Update the host or Coolify: [Upgrade guide](upgrades.md).
- Find an exact command or system boundary: [Command reference](command-reference.md) and [Architecture](architecture.md).
