# ADR-0001: Preserve host ownership during Coolify installation

Status: Accepted  
Date: 2026-08-11

## Context

Solo VPS already treats Ansible as the authority for the host layer, including administrative access, firewall policy, Docker Engine, and `/etc/docker/daemon.json`. Coolify is the selected application platform and its installation belongs in the Ansible-backed host preparation path, but its runtime/application state must not become a second copy of host automation.

The upstream Coolify quick installer is convenient on a generic host, but it also performs privileged host changes. At the time of this decision it installs/configures Docker, manages Docker daemon settings, creates Coolify SSH material, and prepares `/data/coolify`. That overlaps state which Solo VPS already manages deliberately.

Coolify also documents a manual installation path. Non-root server management exists upstream, but is still documented as experimental. The current Solo VPS M4 administrator already has an SSH key and passwordless sudo, so reopening root SSH solely for Coolify would weaken an existing boundary without first proving it is necessary.

## Decision drivers

- keep one clear owner for host configuration;
- avoid silently undoing the M4/M5/M7 security baseline;
- keep installation reproducible and reviewable;
- pin infrastructure/application-platform dependencies intentionally;
- avoid public first-run management exposure by default;
- keep Coolify's own runtime state and secrets out of plaintext Git;
- make later upgrades an explicit, testable operation.

## Options considered

### 1. Run the upstream quick installer unchanged

Simple and officially recommended for generic installations, but it overlaps Ansible-owned Docker and SSH state. It is not acceptable as an opaque backend for the current host contract.

### 2. Temporarily surrender host ownership to the quick installer, then reconcile

Possible in principle, but creates avoidable intermediate drift and a larger failure/recovery surface. Reconciliation would also have to prove that installer-side Docker changes do not break Coolify after Ansible restores its baseline.

### 3. Use the upstream manual installation flow with pinned release artifacts

Preserves the upstream Coolify deployment model while allowing Solo VPS to keep host ownership explicit. It also allows candidate artifacts, secrets, exposure, and service startup to be staged and validated independently.

## Decision

Use option 3 for the Solo VPS Coolify backend.

The accepted ownership boundary is:

```text
Ansible / Solo VPS
  /etc/ssh/*
  /etc/ufw/* and host firewall policy
  Docker packages/services
  /etc/docker/daemon.json
  installation/readiness/recovery automation

Coolify runtime
  /data/coolify/*
  Coolify containers/networks/volumes
  application/proxy/runtime state
```

For the initial implementation:

- pin the Coolify release in project code, not user config;
- explicitly set the Coolify application image tag to the same exact release instead of accepting Compose's `LATEST_IMAGE:-latest` fallback;
- source installation artifacts from the exact upstream Git tag and verify SHA-256 checksums;
- do not use floating `latest` as the installation identity;
- do not reopen root SSH;
- require the inventory to use the M4 `admin.user` before M9 operations;
- preserve the exact M7 Docker daemon baseline and fail on ownership drift;
- keep `/data/coolify/source/.env` and generated secrets on the target, outside Git;
- do not enable unattended Coolify upgrades until the upgrade artifact/version contract is separately validated;
- target SSH-tunneled first-run management access rather than public management ports.

The loopback exposure mechanism has now been resolved for the pinned release: Solo VPS will add a final project-owned Compose override that uses Docker Compose `!override` to replace the upstream `coolify` and `soketi` port lists with `127.0.0.1` bindings for 8000, 6001, and 6002. This requires Docker Compose 2.24.4 or newer and is enforced by M9 readiness.

The override is statically validated against the pinned v4.1.2 port contract, but has not yet been exercised on a clean target. The project owner accepted this boundary on 2026-08-11; acceptance is an architecture decision, not clean-target integration evidence.

### M10 non-root runtime-access clarification

Real M10 testing exposed one integration detail inside this accepted boundary. The pinned Coolify v4.1.2 proxy-start path executes `cd /data/coolify/proxy` through the localhost server's SSH identity before Docker Compose startup. Because Solo VPS deliberately uses the existing non-root `admin.user` and keeps root SSH closed, every ancestor of that path must be traversable by the SSH identity.

The first source fix assumed only `/data/coolify` and `/data/coolify/proxy` needed a UID-9999/group-traverse adjustment. The real target disproved that model: after `make coolify`, Coolify legitimately changed the proxy directory owner to `admin.user`, and a later `make verify-coolify` still could not enter the directory. Source review explains both observations. Ansible can create a missing intermediate `/data` with the permissions supplied while creating `/data/coolify`, and pinned Coolify v4.1.2 deliberately chowns `/data/coolify...` paths created by its non-root `mkdir -p` command to the configured server user.

Solo VPS therefore owns a **bounded access envelope**, not the runtime contents: `/data` is `root:root` mode `0711`; `/data/coolify` remains UID 9999 with `<admin-group>` mode `0710`; `/data/coolify/{applications,databases,services}` are UID 9999 with `<admin-group>` mode `0710`; `/data/coolify/backups` is UID 9999 with `<admin-group>` mode `0730` so the non-root SSH identity can create known backup paths without listing the namespace; and `/data/coolify/proxy` is intentionally owned by `admin.user` with mode `0700`. Sensitive source/SSH directories and secret files retain their restrictive Coolify/Solo VPS modes. Read-only verification executes real access probes as `admin.user`, so metadata-only checks cannot miss a restrictive ancestor or a non-writable backup root. Coolify still owns application, proxy configuration, databases, backups, and runtime content beneath `/data/coolify`; Ansible reconciles only the minimum filesystem access required by the owner-accepted non-root localhost control model.

## Consequences

### Positive

- host policy remains deterministic and reviewable;
- the quick installer cannot silently overwrite Ansible-owned Docker configuration;
- first installation can be made repeatable from immutable release inputs;
- M4 SSH hardening remains intact;
- Coolify stays responsible for the application platform after installation.

### Negative

- more installation logic must be maintained by Solo VPS than with a one-line installer;
- each intentional Coolify upgrade requires review of release artifacts and upgrade behavior;
- the manual backend can drift from future upstream installer assumptions and must be retested;
- non-root compatibility remains an upstream experimental boundary and requires pinned-version integration tests; M10 already exposed one proxy-start path-access assumption that Solo VPS must reconcile.

## Migration / rollback impact

This ADR itself introduces no host mutation.

The future installation backend must not adopt an existing `/data/coolify` automatically. If the directory or a Coolify container already exists, it must stop and use a separate reconciliation/upgrade path.

Before changing an installed Coolify instance, recovery must account for `/data/coolify`, generated secrets, persistent application data, and the M7 Docker host baseline. Backup/restore design is not complete yet and remains a later project milestone.

## Validation

ADR acceptance and M9 completion are different gates. Accepting this ADR approves the ownership/install-backend direction; it does **not** claim the backend has been integration-tested. This avoids a circular dependency where installation would require an accepted boundary while acceptance itself required installation.

Evidence supporting the accepted architecture decision:

1. **V1 complete:** validate the exact pinned release artifacts/checksums;
2. **V1 complete:** define and statically validate the loopback-only `!override` strategy for the pinned Compose port contract.

Evidence required before M9 can be `DONE`:

3. prove the merged Compose model and real management-port reachability on a clean target;
4. install on a clean supported Ubuntu 24.04 target using `admin.user` + sudo;
5. prove `/etc/docker/daemon.json` remains the M7 value before and after installation;
6. prove root SSH remains disabled after M4 hardening;
7. prove management ports are not publicly exposed by default;
8. verify Coolify health and first-run registration flow;
9. exercise a second installation/verification run without destructive reinitialization;
10. document and exercise recovery for a failed install before treating the backend as mature.
