# Solo VPS

[English](README.md) · [Русский](README.ru.md)

**Turn a clean Ubuntu VPS into a ready-to-use server for your applications.** Follow the guide and run a small set of commands. Solo VPS configures Linux, SSH, the firewall, Docker and Coolify, then checks that everything works.

You do not have to design the infrastructure or compare ten tools first. Solo VPS chooses one practical stack, provides the settings and automation, and shows you how to deploy, inspect and recover your applications. After setup, you can return to writing code instead of assembling a server by hand.

> **Status:** PRE-ALPHA — **not production-ready**. Use a test VPS. The basic VPS → Coolify → first application → automatic deployment path has real operator evidence. The exact release candidate still needs a clean-host replay plus recovery/maintenance exercises. Off-site backups and Grafana remain optional profiles.

```text
your computer
        │
        │  setup → apply → secure → platform → verify
        ▼
Ubuntu 24.04 LTS VPS
        ├── hardened host + Docker
        └── Coolify
              └── your applications

GitHub Actions → GHCR → Coolify
SOPS + age → infrastructure/recovery secrets
Optional: restic → managed off-site object storage
```

## What Solo VPS is

Solo VPS is a ready-made server setup for solo developers and small projects. It is both automation and a step-by-step guide: you start with a fresh **Ubuntu 24.04 LTS** VPS and finish with a secured server, a deployment panel and a clear path for CI/CD, logs, backups and recovery.

It is deliberately opinionated. Instead of giving you a box of unrelated options, it answers the important questions up front: which operating system to use, how to secure access, how to run containers, where to deploy applications, where to keep images and how to back up the server.

After the basic setup you can:

- push application code to GitHub and deploy it automatically;
- manage applications, domains, HTTPS, variables, databases and live logs in Coolify;
- verify the server with one project command;
- add retained logs, external monitoring and off-site backups by following the next guided chapters.

## The stack chosen for you

| Technology | What it does here | Why Solo VPS uses it |
| --- | --- | --- |
| **Ubuntu 24.04 LTS** | Base operating system | Stable, widely supported and predictable for one VPS |
| **Ansible** | Configures users, SSH, firewall, updates and Docker | Makes the server setup repeatable instead of a list of one-off shell edits |
| **Docker** | Runs applications and services in containers | Gives applications a consistent package and runtime |
| **Coolify** | Deployments, domains, HTTPS, variables, databases and live logs | Provides a practical UI for everyday application operations without building a platform from scratch |
| **GitHub Actions + GHCR** | Tests code, builds images and delivers them to Coolify | Keeps the build and deployment flow connected to Git pushes |
| **SOPS + age** | Encrypts infrastructure and recovery secrets | Keeps sensitive files encrypted outside the VPS |
| **restic + S3-compatible storage** *(optional)* | Stores recovery copies away from the server | A lost VPS should not destroy its own backups |
| **Grafana Cloud and external uptime monitoring** *(optional)* | Retained logs, host metrics and outage alerts | Lets you investigate failures even when the VPS or an old container is unavailable |

Solo VPS is for one server. It is **not** Kubernetes, a multi-node orchestrator, or a second Coolify implementation. The core profile has **zero dependency on Tailscale, Grafana/Alloy, error tracking, pgAdmin, or shell customization**.

## Current status

Host, SSH, Docker, Coolify, CI and bounded image rollback are implemented in source. A test VPS has operator evidence for fresh Ubuntu 24.04 setup, host apply, admin handoff, SSH hardening, Coolify installation, the first application, automatic post-merge deployment, runtime ENV changes and live application logs. This is not yet the final exact-revision clean replay. Interrupted-install recovery, the real Coolify upgrade path, the three-day retained-log follow-up and full lost-VPS recovery still have separate acceptance work. PostgreSQL restore, off-site backup/restore and Grafana host metrics/alerting are now operator-proven, as is immediate Grafana log delivery across an application redeploy and Alloy restart.

Until those proofs exist, treat local/static validation as development evidence rather than a production guarantee.

This README is the **canonical current user contract**. [`ROADMAP.md`](ROADMAP.md) tracks development state and next work. [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md) is the north-star architecture contract, **not current implementation status**.

## What `make bootstrap` changes

`make bootstrap` is the lower-level host-baseline operation used by the normal `make apply` flow. After preflight, it can:

- configure hostname and timezone;
- create the managed non-root administrator and validated passwordless sudo policy;
- configure the UFW host-input baseline;
- enable unattended Ubuntu security updates with automatic reboot disabled;
- install and configure Docker Engine, Buildx, and Compose.

It intentionally **does not install Coolify**, **does not activate SSH hardening**, does not create production secrets, does not configure off-site storage, and does not deploy applications.

For normal onboarding, use `make apply` rather than assembling lower-level component targets yourself.

## Quick Start

The supported alpha path is **one fresh Ubuntu 24.04 LTS VPS** with at least **2 vCPU, 2 GiB RAM and 30 GiB free disk**. You need root SSH access, provider recovery-console access, inbound TCP 22/80/443, a domain with DNS control, and a Windows PowerShell or Linux workstation with SSH/SCP. The runbook runs Make/Ansible on the VPS; WSL is also suitable when you need Linux tooling on a Windows workstation.

Follow the two-part runbook in order. It includes every required command and UI action, with Windows PowerShell and Linux variants. The [source repository](https://github.com/paracosm17/solo-vps) is public, but there is no validated release or `v0.1.0` tag yet. For pre-alpha testing, clone `main` as shown in the Quick Start. The checkout itself records its exact commit ID; no manual hash entry is required. The moving `main` branch is not a validated release.

1. **[Set up the VPS and Coolify](docs/quick-start.md)** — from `apt-get update` to administrator access, secured SSH, Coolify registration and the dashboard over HTTPS.
2. **[Deploy an application and enable CI/CD](docs/operations/first-app.md)** — GitHub repository, GHCR image, first deployment, dedicated CI key/account, GitHub/Coolify settings, automatic delivery, runtime ENV/secrets and live logs.

The host commands are `make setup → make apply → make secure → make platform → make verify`. Run them at the points shown in part one, including the administrator-login check before SSH hardening.

Basic setup ends after part two. Off-site backups, external alerts and retained logs are subsequent tasks, linked at its end.

**Alpha limits:** the exact release revision still needs a clean-host replay, Coolify lifecycle/interruption proof, whole-host alert test, delayed log-retention check, and lost-VPS recovery exercise. Use a disposable VPS; do not treat the source checks or earlier operator exercises as production approval.

## Safety boundaries

- Use a disposable/test VPS while the project is PRE-ALPHA.
- Keep provider console/rescue access before changing SSH, sudo, or firewall state.
- Never commit private SSH keys, age identities, S3 credentials, restic passwords, API tokens, or application secrets.
- UFW is the host-input baseline; Docker-published ports are reviewed separately.
- Docker-group membership is effectively root-equivalent and is limited to the already privileged managed administrator.
- Source checks are not proof of clean-host installation, hosted CI, real off-site backup, real restore, or disaster recovery.

## Documentation

**Start here:**

- **[Quick Start](docs/quick-start.md)** — fresh VPS to verified Coolify.
- **[Deploy your first application](docs/operations/first-app.md)** — the guided hello-app tutorial.
- **[Daily operations](docs/operations/operator-ui.md)** — where to deploy, inspect logs, edit runtime config, and check CI.
- **[After basic setup](docs/operations/after-basic-setup.md)** — the recommended order for logs, database backups, outage alerts, and recovery.
- **[Retained application logs](docs/operations/observability.md)** — keep searchable history across redeployments.
- **[PostgreSQL backup & restore](docs/operations/postgresql-backups.md)** — create a local Coolify backup and prove it by restoring into a separate database.
- **[External uptime](docs/operations/external-uptime.md)** — chapter 5: receive independent outage and recovery notifications.
- **[Off-site backups](docs/operations/offsite-backups.md)** — chapter 6: move PostgreSQL, Coolify and filesystem recovery copies outside the VPS and prove restore.
- **[VPS metrics](docs/operations/metrics.md)** — chapter 7: send a small CPU/memory/disk metric set to Grafana Cloud and prove one actionable alert.
- **[Failures and maintenance](docs/operations/incidents-and-maintenance.md)** — investigate CI and production failures and follow the planned-maintenance checklist.
- **[Backup and recovery reference](docs/backups-restic.md)** — restic details and recovery boundaries.
- **[Upgrade guide](docs/upgrades.md)** — supported Docker/Coolify lifecycle.
- **[Lost VPS recovery](docs/disaster-recovery.md)** — replacement-server procedure.
- **[Command reference](docs/command-reference.md)** — public and advanced Make targets.

Browse the complete task-oriented map in **[`docs/index.md`](docs/index.md)**.

Preview the same documentation as a Material for MkDocs site:

```bash
make docs
```

For the strict build used by documentation CI:

```bash
make docs-build
```

See [Documentation site](docs/documentation-site.md) for manual setup and GitHub Pages publishing.

For project policy and design: [`SECURITY.md`](SECURITY.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/architecture.md`](docs/architecture.md), [`LICENSE`](LICENSE), and the [`Apache-2.0 decision`](docs/license-choice.md). Release maintainers can use [`docs/release-process.md`](docs/release-process.md) together with [`CHANGELOG.md`](CHANGELOG.md); those release-evidence pages are intentionally excluded from the public documentation navigation.

A repeated `make apply` uses the managed admin inventory. `make platform` verifies a completed installation or resumes its own interrupted install; do not delete `/data/coolify`. `make verify` checks activated SSH/Coolify phases and rejects unfinished transactions.
