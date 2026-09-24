# Check prerequisites and connectivity

Use `make doctor` when you want a read-only answer to: **is this controller ready, can it reach the target, and does the target satisfy the current Solo VPS requirements?**

## Supported first-run target

The current alpha path targets:

- Ubuntu 24.04 LTS;
- Python 3.12+ on the controller after `make setup`;
- OpenSSH client/tooling;
- explicit SSH access to the configured target;
- Docker 29.x for the current platform lifecycle;
- enough CPU, memory, and disk for the Coolify readiness gate.

The exact application-platform resource checks are performed later by `make platform` / `make coolify-readiness`.

## First-run controller prerequisite

Before the project can automate anything, install GNU Make and obtain the source:

```bash
apt-get update
apt-get install -y make git
cd solo-vps
make setup
```

`make setup` prepares the remaining controller dependencies and persistent state.

## Run the doctor

**Where: controller**

```bash
make doctor
```

`make doctor` is read-only. It combines local controller diagnostics, platform capability reporting, and a remote preflight against the current inventory target.

## What it checks

The exact checks vary by lifecycle stage, but the doctor is designed to catch problems such as:

- missing local config/inventory;
- unsupported or incomplete controller tooling;
- invalid public-key paths;
- unreachable SSH target;
- inventory/user mismatch;
- unsupported platform characteristics;
- obvious state conflicts before mutation.

## Required local files

Mutable operator state lives outside the source checkout. Use:

```bash
make paths
```

to find the active config, inventory, toolchain, SOPS policy, evidence, and state directories.

See [Persistent state layout](state-layout.md).

## Initial access contract

The first mutation needs a working provider/bootstrap SSH path. If the provider user is not the inventory user, the normal lifecycle can select it explicitly:

```bash
make apply BOOTSTRAP_USER=ubuntu
```

After the host baseline, the inventory transitions to the configured `admin.user`. SSH hardening is not allowed until a fresh workstation login and provider recovery are both proven.

## When `make doctor` fails

Read the first actionable error and fix that boundary before running mutating commands. Do not bypass the check by manually changing firewall, SSH, Docker, or Coolify state unless a documented recovery procedure tells you to.

Useful follow-up pages:

- [Admin access](admin-access.md)
- [SSH hardening](ssh-hardening.md)
- [Docker host](docker-host.md)
- [Coolify installation](coolify-installation.md)
- [Command reference](command-reference.md)
