# Solo VPS architecture

<!-- Repository-level source documents intentionally remain outside the MkDocs site:
README.md, PROJECT_PASSPORT.md, ROADMAP.md and
.agents/skills/solo-vps-project-engineer/SKILL.md. -->

Solo VPS has one design goal: keep **host ownership**, **application-platform ownership**, and **recovery ownership** explicit enough that one VPS stays understandable.

`PROJECT_PASSPORT.md` is the **north-star product/architecture boundary**. `README.md` is the **current user-facing supported contract**. `ROADMAP.md` tracks development/evidence state rather than defining architecture.

## Source-of-truth hierarchy

When two documents appear to disagree, use this order:

```text
accepted ADR / explicit owner decision
-> PROJECT_PASSPORT.md
-> README.md
-> ROADMAP.md
-> current implementation
-> legacy research
```

This prevents a historical experiment or an unfinished roadmap item from silently becoming a user contract.

## Accepted baseline

| Layer | Owns | Does not own |
| --- | --- | --- |
| **Ansible** | Ubuntu host, admin identity, SSH/sudo, firewall, security updates, Docker host baseline, verification, backup/recovery foundation | Application deployment state, domains/proxy lifecycle, app databases/services |
| **Coolify** | Applications/services, domains/TLS, deployments, live logs, runtime config/secrets, terminals, databases | Base OS hardening, host firewall, the Ansible-owned Docker baseline |
| **GitHub Actions** | CI, tests, image build/publish, optional controlled deployment workflow | Default interactive host administration |
| **GHCR** | Immutable container artifacts | Host configuration or application runtime configuration |
| **SOPS + age** | Infrastructure/recovery secrets in the operator workflow | Online Vault-like brokering or ordinary Coolify app-secret UX |
| **restic + off-site storage** | Filesystem/control-plane recovery material | Coolify instance DB backup or application PostgreSQL ownership |

The core profile keeps Coolify management ports loopback-only. Public applications use the normal web edge; CI reaches the Coolify API only through the restricted deployment transport.

Optional retained historical application logs use non-root **Alloy** through a **restricted Docker API proxy** over a **Unix socket**. The collector does not receive the real Docker socket directly.

## System map

```text
operator workstation
  |-- Git checkout (disposable source)
  |-- ~/.local/share/solo-vps (persistent controller state)
  |-- SOPS + age private identity
  |
  +-- Ansible ------------------------------+
  |                                         |
  +-- git push -> GitHub Actions -> GHCR     |
                                            v
                                  +----------------------+
                                  | Ubuntu 24.04 VPS     |
                                  |                      |
                                  | Ansible-owned host   |
                                  | - users / SSH / sudo |
                                  | - UFW / updates      |
                                  | - Docker host        |
                                  | - verify / audit     |
                                  | - backup foundation  |
                                  |                      |
                                  | Coolify platform     |
                                  | - apps / services    |
                                  | - proxy / TLS        |
                                  | - databases          |
                                  +----------+-----------+
                                             |
                                             +--> managed off-site storage
```

**This diagram is a responsibility map**, not proof that every path has already received end-to-end runtime validation.

## Main flows

### Provision a host

```text
make setup
-> make apply
-> make secure
-> make platform
-> make verify
```

`apply` owns the host baseline and admin handoff. SSH hardening stays separately safety-gated. Coolify is installed only in the platform step.

### Deliver an application

Manual first-app path:

```text
source repository -> Coolify -> Dockerfile build -> domain/TLS -> health check
```

Optional CI/CD path:

```text
git push -> GitHub Actions -> GHCR immutable digest
         -> restricted SSH local forward -> loopback Coolify API -> deploy
```

Application migrations remain application-owned. Automated deployment rollback is container-image rollback only.

### Handle secrets

```text
trusted workstation
  -> age private key stays on workstation
  -> SOPS ciphertext can be stored/transferred safely
  -> required plaintext is delivered over SSH stdin
  -> VPS receives root-only runtime files
```

Application runtime secrets normally stay in Coolify; infrastructure/recovery secrets use SOPS + age.

### Back up and recover

```text
/data/coolify recovery material -> restic -> external S3-compatible storage
Coolify instance database       -> logical Coolify backup
application PostgreSQL          -> Coolify-owned logical backup
```

A lost-VPS recovery combines those inputs on a fresh Ubuntu host. A same-VPS copy is not an off-site backup.

### Operate day to day

```text
GitHub Actions -> CI/build/deploy status
GHCR           -> artifact identity
Coolify        -> deployments, health, live logs, config/secrets, terminal
Grafana Cloud  -> optional retained historical application logs
```

`make ops-*` remains a diagnostic fallback rather than a second application control plane.

## Ownership matrix

| Concern | Authority |
| --- | --- |
| Ubuntu host baseline | Ansible |
| Human admin access / SSH hardening | Ansible + operator safety proof |
| Host firewall / updates | Ansible |
| Docker Engine host configuration | Ansible |
| Coolify installation integration | Solo VPS automation, with Coolify owning the platform runtime |
| Application lifecycle | Coolify |
| CI / build / image publication | GitHub Actions |
| Container artifacts | GHCR |
| Infrastructure/recovery secrets | SOPS + age |
| Host/Coolify filesystem backup | restic + managed off-site storage |
| Coolify-managed PostgreSQL backups | Coolify |
| Optional retained logs | Grafana Alloy -> restricted Docker API proxy -> Grafana Cloud |

The key design rule is to avoid two competing owners for the same state.

## Accepted ADR decisions

The project owner accepted ADRs 0001–0004 below. **Acceptance establishes the architecture boundary**; it does not by itself prove runtime behavior.

| ADR | Status | Decision |
| --- | --- | --- |
| [`ADR-0001`](adr/0001-coolify-installation-boundary.md) | **Accepted** | Keep Ansible ownership of the host/Docker baseline and use a pinned Coolify integration |
| [`ADR-0002`](adr/0002-controller-side-sops-decryption.md) | **Accepted** | Keep the production age private key on the operator workstation; no second controller server is required |
| [`ADR-0003`](adr/0003-coolify-native-database-backups.md) | **Accepted** | Use Coolify-native logical backups for Coolify-managed PostgreSQL rather than a competing dump scheduler |
| [`ADR-0004`](adr/0004-external-operator-state.md) | **Accepted** | Keep per-installation controller state outside the disposable Git checkout |

## Proposed ADR decisions

Proposed entries do not change the supported architecture until their stated evidence is complete.

| ADR | Status | Decision |
| --- | --- | --- |
| [`ADR-0005`](adr/0005-coolify-sentinel-trust-boundary.md) | **Proposed** | Accept mandatory Sentinel only inside the reviewed high-trust Coolify boundary after disposable runtime proof |

Change a long-lived boundary by updating/superseding the ADR first, then the user docs and implementation in the same coherent change.

## Trust and exposure boundaries

**Administrative access.** SSH/sudo/firewall changes are access-critical. Solo VPS preserves a separately proven human workstation login before removing fallback access.

**Docker.** Docker-published ports are a separate exposure surface from UFW. Management interfaces must not become public merely because a container can publish them.

**Coolify.** Ports `8000/6001/6002` remain private/loopback in the core profile. Public traffic belongs on the application edge. Proposed ADR-0005 treats Sentinel as part of this high-trust control plane because its upstream container uses the host PID namespace and read-write Docker socket; its API must not publish a host port.

**Observability.** The retained-log path uses a restricted Docker API proxy through `/run/solo-vps-docker-api/docker-api.sock`. The proxy is still high-trust because it owns the real Docker daemon socket, while Alloy only receives the narrowed Unix-socket interface. A host-local unprivileged identity should not be able to traverse that boundary. The host-metrics profile is deliberately separate: `solo-vps-metrics` reads only selected Linux host metrics through Alloy's Unix exporter, has no Docker access, and exposes its Alloy HTTP endpoint only on loopback.

**Secrets.** Public source, examples, and non-secret config must not contain private SSH keys, age identities, S3/restic credentials, API tokens, or application secrets.

**Backup.** Installing restic is not recovery evidence. Recovery requires off-site storage, fresh snapshots, logical database backups where applicable, and a verified restore procedure.

## Current evidence boundary

Solo VPS is **PRE-ALPHA**. The architecture describes the intended and source-supported responsibility model; it must not be read as a production-readiness claim.

In particular, source validators and local checks are weaker than a clean disposable VPS replay, a real off-site backup/restore, a real PostgreSQL restore, or a destroy-and-rebuild disaster-recovery exercise. Use `ROADMAP.md` for the current evidence state.

## Architecture change rule

Create or update an ADR when a change materially affects ownership, core technology, supported platforms, security/trust boundaries, secrets, storage/database strategy, deployment strategy, or migration burden.

Do not create ADRs for small reversible implementation details.

The maintainer engineering rules live in `.agents/skills/solo-vps-project-engineer/SKILL.md`.
