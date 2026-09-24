# Command reference

Solo VPS deliberately exposes a small normal lifecycle. Start there; use subsystem targets only for diagnostics, recovery, or a reviewed advanced operation.

> Run `make help` for the supported operator surface, `make help-ops` for operational commands, and `make help-all` only when you need the complete implementation catalog.

## Normal lifecycle

| Command | Mutates state? | Purpose |
| --- | --- | --- |
| `make setup` | workstation/controller | Prepare prerequisites, persistent state, SSH identity, and pinned QA tooling |
| `make apply` | **yes — VPS** | Apply/resume the host baseline, verify it, and switch inventory to the managed admin |
| `make secure` | **yes — access-critical** | Activate SSH hardening after provider-recovery and fresh workstation-login proofs |
| `make platform` | **yes — VPS** | Install/verify the pinned Coolify platform |
| `make verify` | no | Run read-only local/remote verification and summarize platform state |

The intended order is:

```text
setup -> apply -> secure -> platform -> verify
```

For a first installation, use [Quick Start](quick-start.md) rather than this reference page.

## Setup and access helpers

### `make paths`

Shows the source checkout and persistent Solo VPS state paths. Useful before switching checkouts or debugging which config/inventory is active.

### `make controller-check`

Read-only check of first-run controller prerequisites.

### `make ssh-key`

Creates or reuses the default **controller** SSH key. It never substitutes for the human workstation recovery identity.

### `make init`

Initializes persistent config/inventory outside the Git checkout without overwriting existing operator state.

### `make human-admin-key-file`

Stores the human admin **public** key from an explicit `.pub` file.

### `make human-admin-key-stdin`

Stores the human admin **public** key from stdin. This is convenient when the project/controller runs on the VPS but the recovery identity belongs to your workstation.

```bash
SERVER_IP='YOUR_SERVER_IP'
BOOTSTRAP_USER='YOUR_BOOTSTRAP_USER'
cat ~/.ssh/id_ed25519.pub | ssh "${BOOTSTRAP_USER}@${SERVER_IP}" \
  'cd ~/solo-vps && make human-admin-key-stdin'
```

Do not send the private key.

### `make use-bootstrap` / `make use-admin`

Synchronize inventory to the bootstrap SSH identity or the managed admin identity. These are recovery/diagnostic helpers; the normal `make apply` path handles the handoff automatically.

## Diagnostics and verification

### `make doctor`

Runs platform-aware diagnostics and remote preflight. Use it when a lifecycle command refuses to proceed or before a risky subsystem change.

### `make preflight`

Read-only target compatibility and configuration checks.

### `make verify`

Read-only aggregate verification of the implemented baseline.

### `make audit`

Read-only security audit of implemented host controls and exposure.

### `make ops-status`

Bounded host/container status fallback.

### `make ops-logs`

Read-only recent logs for one explicitly selected container:

```bash
make ops-logs CONTAINER=<container-name> TAIL=100
```

Use Coolify or your observability UI for normal log work; this is a diagnostic fallback.

## Host subsystems

The normal install uses `make apply`, `make secure`, and `make platform`. These narrower targets are useful when you intentionally work on one subsystem:

| Apply target | Read-only verifier |
| --- | --- |
| `make firewall` | `make verify-firewall` |
| `make updates` | `make verify-updates` |
| `make docker` | `make verify-docker` |
| `make ssh-harden` | `make verify-ssh` |
| `make coolify` | `make verify-coolify` |

`make bootstrap` applies the current host bootstrap baseline but **does not activate SSH hardening** and **does not install Coolify**. It exists as a lower-level recovery/engineering surface; first-time users should prefer `make apply`.

## Backup commands

Before using these, configure off-site storage and credentials as described in [restic off-site backups](backups-restic.md).

| Command | Behavior |
| --- | --- |
| `make backup-readiness` | local/source-policy readiness; no storage contact |
| `make backup-tooling` | install pinned restic binary only |
| `make verify-backup-tooling` | verify restic tooling |
| `make backup-runtime` | install root-only runtime + timer units; does not automatically enable the timer |
| `make verify-backup-runtime` | verify runtime files/timer state |
| `make backup-repository-init` | **external write** — initialize a new empty encrypted repository |
| `make backup-repository-adopt` | read/check an existing repository before adoption |
| `make backup-status` | read-only repository/freshness summary |
| `make backup-check` | read-only integrity + freshness check |
| `make backup-now` | **external write** — create one off-site snapshot |
| `make backup` | run a configured backup and verify repository/freshness |
| `make backup-restore-test` | restore latest matching snapshot into a temporary test tree |
| `make backup-retention-plan` | read-only retention dry run |
| `make backup-retention-apply` | **destructive external write** — apply reviewed forget/prune policy |

Scheduling is opt-in:

```bash
make backup-schedule-enable
```

Weekly retention/prune also requires a separate reviewed path; do not enable destructive maintenance just because snapshots work.

## Database backup and restore

Coolify owns the PostgreSQL logical backup schedule for Coolify-managed databases. Solo VPS does not add a second dump scheduler.

Useful targets:

```bash
make database-backup-plan
make database-backup-configure
make database-backup-trigger
make database-backup-verify
```

A restore exercise is deliberately separate and destructive to the **disposable target database**:

```bash
make database-restore-inspect
make database-restore-exercise
```

Follow [PostgreSQL backups and restore exercise](database-backups.md) rather than invoking restore targets from memory.

## Recovery

### `make recover`

Prints the safety-gated lost-VPS recovery entry point. It does not mutate a host by itself.

Full-host recovery needs more than a restic snapshot: follow [Disaster recovery](disaster-recovery.md), including Coolify instance database and application database recovery inputs.

## Platform lifecycle and upgrades

### `make update`

Read-only review entry point for both the Solo VPS source contract and the Docker/Coolify lifecycle. It does **not** run `git pull` or blindly upgrade a host.

### `make source-update-plan`

Prints the reviewed-tag/new-checkout source update contract. The executable example and rollback boundary are in [Upgrade Solo VPS & Coolify](upgrades.md).

### `make platform-lifecycle-plan`

Displays the reviewed Docker/Coolify support window.

### `make coolify-upgrade-preflight`

Read-only preflight for the one supported previous → current Coolify transition.

### `make coolify-upgrade`

**Mutating, confirmation-gated** supported Coolify upgrade. Requires backup checks and exact acknowledgements.

### `make coolify-upgrade-resume`

Explicitly resumes a known interrupted supported upgrade. It never means “downgrade automatically.”

Read [Upgrade guide](upgrades.md) before either mutating upgrade target.

## External uptime

Render the provider-neutral monitor policy without creating anything:

```bash
make uptime-plan UPTIME_HEALTH_URL=https://app.example.com/healthz
```

After an actual external outage/recovery exercise, `make uptime-evidence` records a sanitized operator-attested summary outside tracked source. See [External uptime](operations/external-uptime.md).

## Optional retained logs

If you intentionally enable Grafana Cloud retained logs:

```bash
make observability-secrets-init
make observability-secrets-check
make observability-secrets-push
make verify-observability-credentials
make observability-runtime
make verify-observability-runtime
```

See [Chapter 3: retained logs](operations/observability.md) first. The core Quick Start does not require this module.

## Optional host metrics

If you intentionally enable the chapter-7 Grafana Cloud host metrics profile:

```bash
make metrics-secrets-init
make metrics-secrets-check
make metrics-secrets-push
make verify-metrics-credentials
make metrics-runtime
make verify-metrics-runtime
```

See [Chapter 7: VPS metrics](operations/metrics.md) for the complete credential, Grafana UI and alert test workflow.

## CI/CD transport

For the application GitHub Actions → Coolify path:

```bash
make plan-ci-deploy-transport
make ci-deploy-transport
make verify-ci-deploy-transport
```

These install a dedicated forwarding-only deployment identity; they are not part of `make bootstrap`. See [GitHub Actions + GHCR delivery](ci-ghcr.md).

## Documentation

### `make docs`

Creates/updates the isolated documentation environment and starts the local Material for MkDocs preview server.

### `make docs-build`

Builds the documentation with `mkdocs build --strict`. Use this before a documentation commit.

See [Documentation site](documentation-site.md) for manual setup and GitHub Pages publishing.

## Project validation

For normal local source validation:

```bash
make validate
```

When the pinned QA environment is installed:

```bash
make qa-check
make qa-static
```

Maintainers can discover the full validator/test catalog with:

```bash
make help-dev
make help-all
```

The complete internal target list is intentionally not duplicated here; `make help-all` is the executable source of truth and avoids documentation drift.
