<p align="center">
  <img src="docs/assets/brand/solo-vps-mark.svg" width="72" height="72" alt="">
</p>
<h1 align="center">Solo VPS</h1>
<p align="center"><strong>Your apps. One VPS. Deploy from Git.</strong></p>
<p align="center">
  <a href="https://github.com/paracosm17/solo-vps/actions/workflows/repository-ci.yml"><img src="https://github.com/paracosm17/solo-vps/actions/workflows/repository-ci.yml/badge.svg?branch=main" alt="Repository CI"></a>
  <a href="https://paracosm17.github.io/solo-vps/"><img src="https://img.shields.io/badge/docs-English%20%2F%20Русский-3273dc" alt="Documentation in English and Russian"></a>
  <a href="https://paracosm17.github.io/solo-vps/quick-start/"><img src="https://img.shields.io/badge/Ubuntu-24.04%20LTS-E95420?logo=ubuntu&amp;logoColor=white" alt="Ubuntu 24.04 LTS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2ea44f" alt="Apache-2.0 license"></a>
</p>
<p align="center">
  <a href="https://paracosm17.github.io/solo-vps/quick-start/"><strong>Get started</strong></a> ·
  <a href="https://paracosm17.github.io/solo-vps/">Documentation</a> ·
  <a href="https://github.com/paracosm17/solo-vps/issues">Report a bug</a> ·
  <a href="README.ru.md">Русский</a>
</p>

Solo VPS sets up a single Ubuntu server for hosting your applications. It configures administrator access, SSH, the firewall and Docker, installs **Coolify**, and provides a step-by-step guide to automatic deployment with **GitHub Actions and GHCR**.

It is built for developers running their own services, side projects or small products on a VPS. Server setup is repeatable; everyday deployments, environment variables and logs are managed through GitHub and the Coolify dashboard.

## Features

- **Repeatable server setup.** Ansible configures a non-root administrator, SSH keys, firewall rules, security updates and Docker.
- **Deploy on push.** The reference workflow tests your code, builds an image in GitHub Actions, publishes it to GHCR and deploys it through Coolify. Builds run outside your VPS.
- **A dashboard for daily work.** Manage domains, HTTPS, application settings, databases, deployments and live logs in Coolify.
- **Verification and maintenance.** Project commands check the host configuration; runbooks cover upgrades, failed deployments and recovery.
- **Backups when you need them.** Add PostgreSQL backups, encrypted off-site copies with restic, and a documented restore procedure.
- **Monitoring when you need it.** Add external outage alerts, retained application logs and VPS metrics using managed services.

## How it works

![Git push → GitHub Actions tests and builds → GHCR stores the image → Coolify deploys to your VPS](docs/assets/brand/delivery-flow.svg)

**Solo VPS configures the host. Coolify runs the applications. GitHub Actions builds the images.** After connecting the delivery workflow, a push to your application's `main` branch starts the checks and deployment. You can follow the result in GitHub and Coolify without opening an SSH session for each release.

The maintained setup is **one application VPS**. The reviewed Coolify release, supported upgrade origin and qualification are defined in [the release manifest](config/coolify-release.yml); see [upgrades](docs/upgrades.md) for the procedure. Backups and monitoring are optional and can be configured after your first application is running. Multi-server clusters, high availability and automated team access management are outside the current scope.

## Quick Start

### Requirements

| What | You need |
| --- | --- |
| Server | A fresh **Ubuntu 24.04 LTS** VPS; minimum **2 vCPU, 2 GiB RAM and 30 GiB free disk** |
| Access | Initial root SSH access, the provider's recovery console, and inbound TCP **22, 80 and 443** |
| Domain | A domain and access to its DNS settings |
| Workstation | **Windows PowerShell or Linux/WSL**, with SSH and SCP |
| Delivery | A GitHub account for the reference GitHub Actions / GHCR workflow |

These resources are the installation minimum. Leave room for the applications and databases you plan to run.

### Install and deploy

Follow the two guides in order. They include the commands, configuration and browser steps for Windows and Linux/WSL:

1. **[Set up the VPS and Coolify](https://paracosm17.github.io/solo-vps/quick-start/)** — configure Ubuntu and administrator access, install Docker and Coolify, and open the dashboard over HTTPS.
2. **[Deploy an application and enable CI/CD](https://paracosm17.github.io/solo-vps/operations/first-app/)** — publish a container image, deploy the sample app, connect automatic updates, and use environment variables and logs.

The host setup follows this sequence:

```text
make setup → make apply → make secure → make platform → make verify
```

Run each command at its place in the first guide: it includes the configuration and administrator-login check needed before SSH hardening. Make and Ansible run on the VPS during setup; workstation commands are provided for PowerShell and Linux/WSL.

Basic setup ends after part two. Continue with your own application or add the operational features it needs.

## Documentation

| Task | Guide |
| --- | --- |
| Manage deployments, variables and live logs | [Daily operations](https://paracosm17.github.io/solo-vps/operations/operator-ui/) |
| Plan the next setup steps | [After basic setup](https://paracosm17.github.io/solo-vps/operations/after-basic-setup/) |
| Back up a database or the server | [PostgreSQL](https://paracosm17.github.io/solo-vps/operations/postgresql-backups/) · [Off-site backups](https://paracosm17.github.io/solo-vps/operations/offsite-backups/) |
| Add alerts, log history or metrics | [Uptime](https://paracosm17.github.io/solo-vps/operations/external-uptime/) · [Logs](https://paracosm17.github.io/solo-vps/operations/observability/) · [Metrics](https://paracosm17.github.io/solo-vps/operations/metrics/) |
| Update or recover an installation | [Upgrades](https://paracosm17.github.io/solo-vps/upgrades/) · [Lost VPS recovery](https://paracosm17.github.io/solo-vps/disaster-recovery/) |
| Look up a command | [Command reference](https://paracosm17.github.io/solo-vps/command-reference/) |

Keep recovery credentials and backups outside the VPS before relying on it for important data. Deployment rollback restores an application image; it does not undo database migrations or data changes.

## Contributing and support

Bug reports, documentation corrections and focused improvements are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Report security issues privately using the process in [`SECURITY.md`](SECURITY.md).

<details>
<summary>Project design and development</summary>

- [Architecture](docs/architecture.md) and [product boundaries](PROJECT_PASSPORT.md).
- [Roadmap and validation evidence](ROADMAP.md).
- [Changelog](CHANGELOG.md) and [release process](docs/release-process.md).
- [Documentation writing guide](.github/DOCUMENTATION.md).

</details>

## License

[Apache License 2.0](LICENSE). See the [license decision](docs/license-choice.md) for the project's contribution terms.
