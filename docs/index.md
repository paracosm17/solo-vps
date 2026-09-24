# Solo VPS

<p class="solo-home-intro" data-solo-home><strong>Start with a clean Ubuntu VPS. Finish with a ready-to-use server for your applications.</strong> Solo VPS chooses the stack, supplies the settings and automation, and walks you through the few commands and UI steps that cannot be avoided.</p>

You do not need to be a DevOps engineer. Follow the guide and Solo VPS will configure secure access, the firewall, Docker and Coolify. You then deploy and manage applications through GitHub and Coolify instead of maintaining the infrastructure by hand.

<div class="solo-status">
  <svg class="solo-status__icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2.75 22 20H2L12 2.75Zm0 5.1a1 1 0 0 0-1 1v5.25a1 1 0 1 0 2 0V8.85a1 1 0 0 0-1-1Zm0 9.05a1.15 1.15 0 1 0 0 2.3 1.15 1.15 0 0 0 0-2.3Z"/></svg>
  <div class="solo-status__body"><strong>PRE-ALPHA</strong>Use a test VPS for now. The complete installation and recovery paths are still being validated.</div>
</div>

## Start here

If this is your first Solo VPS installation, complete parts 1 and 2 in order. Together they cover basic setup through CI/CD, runtime variables and live logs. You do not need to read the architecture or internal implementation first. Then open [After basic setup](operations/after-basic-setup.md) and add the operational pieces your application needs.

<div class="solo-start-grid">
  <a class="solo-start-card" href="quick-start/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M13 6l6 6-6 6"/></svg></span>
    <span><span class="solo-start-card__title">1. VPS and Coolify</span><span class="solo-start-card__copy">From a fresh Ubuntu server to administrator access and Coolify over HTTPS.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/first-app/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9"/></svg></span>
    <span><span class="solo-start-card__title">2. Application and CI/CD</span><span class="solo-start-card__copy">Create the demo, enable GitHub deployment, set ENV and inspect logs — all on one page.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/operator-ui/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 5h16v14H4zM8 9h8M8 13h5"/></svg></span>
    <span><span class="solo-start-card__title">Daily operations</span><span class="solo-start-card__copy">Know where deployments, variables, logs, health checks and diagnostics live.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/offsite-backups/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6M4 4v4.6h4.6"/></svg></span>
    <span><span class="solo-start-card__title">Backups and recovery</span><span class="solo-start-card__copy">Move PostgreSQL, Coolify and filesystem backups off the VPS and prove a real restore.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
</div>

## What is already decided for you

Solo VPS provides one recommended path instead of asking you to assemble your own platform:

| Choice | Purpose |
| --- | --- |
| **Ubuntu 24.04 LTS + Ansible** | A stable server base and repeatable configuration |
| **SSH hardening + UFW + security updates** | A practical host-security baseline |
| **Docker + Coolify** | Containers plus a UI for deployments, domains, HTTPS, variables, databases and live logs |
| **GitHub Actions + GHCR** | Test, build and deploy applications from Git pushes |
| **SOPS + age** | Encrypted infrastructure and recovery secrets |
| **restic, external monitoring and Grafana Cloud** | Optional off-site recovery, outage alerts, retained logs and host metrics |

The result is not a multi-server cloud platform. It is one understandable server with concrete defaults and documented recovery steps.

## Installation path

The supported first-run path is intentionally small:

<div class="solo-command-path"><code>make setup</code><span>→</span><code>make apply</code><span>→</span><code>make secure</code><span>→</span><code>make platform</code><span>→</span><code>make verify</code></div>

The [Quick Start](quick-start.md) explains where each command runs, what it changes, and what successful output looks like.

## Responsibility boundaries

| Area | Owner |
| --- | --- |
| Ubuntu host baseline, SSH, firewall, Docker | **Solo VPS** |
| Application deployment and runtime configuration | **Coolify** |
| CI and image publishing, when enabled | **GitHub Actions / GHCR** |
| Off-site storage and third-party accounts | **You** |
| Recovery procedure | **Solo VPS docs + your off-site credentials/backups** |

## Common tasks

- **New server:** [Quick Start](quick-start.md)
- **Something fails before installation:** [Preflight & doctor](preflight.md)
- **Deploy an application:** [Deploy your first app](operations/first-app.md)
- **Find deployments, variables or current logs:** [Daily operations](operations/operator-ui.md)
- **Decide what to configure after the basic setup:** [After basic setup](operations/after-basic-setup.md)
- **Find application logs from days ago:** [Retained logs](operations/observability.md)
- **Check host status and bounded logs:** [Status & logs](operations/status-and-logs.md)
- **Move backups off the VPS:** [Chapter 6: off-site backups](operations/offsite-backups.md)
- **Back up or restore PostgreSQL:** [Chapter 4: PostgreSQL backup & restore](operations/postgresql-backups.md)
- **Get notified about downtime:** [Chapter 5: external uptime monitor](operations/external-uptime.md)
- **Watch CPU, memory and disk:** [Chapter 7: VPS metrics](operations/metrics.md)
- **Handle an incident or planned maintenance:** [Failures and maintenance](operations/incidents-and-maintenance.md)
- **Replace a lost VPS:** [Recover from a lost VPS](disaster-recovery.md)
- **Update the host/platform:** [Upgrade Solo VPS & Coolify](upgrades.md)
- **Find an exact command:** [Command reference](command-reference.md)
- **Understand ownership and system boundaries:** [Architecture](architecture.md)
