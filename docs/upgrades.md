# Upgrade guide

Solo VPS is **PRE-ALPHA**. Upgrades are deliberate operations with a defined support window, preflight, verification, and recovery path. There is no generic “update everything” command.

## Upgrade safety model

Use this sequence for any runtime-sensitive change:

```text
identify exact current + target versions
-> read the component's recovery boundary
-> prove required backups/recovery inputs
-> run read-only preflight
-> change one subsystem
-> verify that subsystem
-> make verify
-> make audit
```

If a change cannot describe its recovery path, it is not ready for production execution.

A previous project checkout is **not** a generic runtime rollback. Reverting source does not undo packages, database migrations, or external state changes.

## Update Solo VPS source

Solo VPS source is updated by opening a **new checkout of a reviewed release**, not by running `git pull` in the active checkout. Installation-specific config, inventory and encrypted operator state live outside the source tree, so both checkouts use the same persistent state.

No release tag exists while the project is PRE-ALPHA. Until the first release is published, use only the reviewed commit or archive supplied for a test. After a release is published, use its exact tag:

```bash
REPOSITORY_URL='YOUR_SOLO_VPS_REPOSITORY_URL'
RELEASE_VERSION='v0.1.0'
git clone --branch "$RELEASE_VERSION" --depth 1 "$REPOSITORY_URL" "solo-vps-${RELEASE_VERSION}"
cd "solo-vps-${RELEASE_VERSION}"
test "$(git describe --tags --exact-match)" = "$RELEASE_VERSION"
```

Then verify the new source before it changes the VPS:

```bash
make setup
make paths
make validate
make doctor
make verify
make audit
```

Compare the `make paths` output with the old checkout. The config and inventory paths must be identical. Read the target release notes and run only the explicit subsystem migration or lifecycle command required by that release. A source update alone does not require `make secure`, a Docker upgrade, or a Coolify upgrade.

Keep the previous checkout until the new source passes verification and the application remains healthy. Returning to it restores only the previous automation source; it does not undo runtime mutations already performed by a subsystem upgrade.

## Project automation and host configuration

Per-installation **controller state is now external to the checkout**. Before switching source revisions, verify where the active state lives:

```bash
make paths
```

For a reviewed Solo VPS source change:

```bash
make validate
make doctor
# apply only the intended subsystem/lifecycle operation
make verify
make audit
```

Compare your persistent configuration with `config/config.example.yml` when the config schema changes. Preserve a source checkpoint, but do not confuse that checkpoint with host/data rollback.

### Retest an existing VPS after a source fix

Use this sequence for a reviewed automation fix that keeps the installed Docker/Coolify versions supported. Keep a second working SSH session and provider recovery access available.

1. Log in as the existing managed administrator. In the old source directory, run `make paths` and record the config/inventory paths. Preserve the old source and any required data backups.
2. Extract or clone the reviewed source into a new directory. Record its commit ID (`git rev-parse HEAD` for a clone, or the revision supplied with the archive). Run `make paths` there under the same user. The persistent config/inventory paths must match; do not initialize a second installation or copy example config over the active configuration. When running the controller on the VPS itself, preserve the old `~/solo-vps` under a separate backup name, put the new source at `~/solo-vps`, and continue from that standard admin workspace.
3. Run `make setup` to reconcile the controller prerequisites. Existing keys and configuration are retained. For maintainer regression testing, run `make qa-tools`, then `make qa-static`. The QA gate evaluates the Docker version parsers and firewall listener diagnostics with the pinned Ansible engine, without contacting the VPS through SSH.
4. Run `make doctor`, `make verify` and `make audit`, one at a time. These establish the state seen by the new source. Record and investigate any failure before mutation.
5. For the Docker parser fix, run `make docker`, then `make verify-docker`. Supported installed Docker packages should be retained. Run `make apply` to repeat the complete host baseline through the existing admin inventory.
6. Run `make platform` to reconcile and verify the managed Coolify installation. After success, repeat `make apply` and `make platform` once to test reruns, then run `make verify` and `make audit` again. Do not run `make secure` solely because the source changed; an existing hardened host already has that policy.
7. Check the application URL and logs. After all preceding steps pass, reboot deliberately, reconnect as the administrator, and repeat `make verify`, `make audit` and the application check.

Stop at the first failed command and retain its full output with the source revision. `make update` is a plan; a Coolify version transition is a separate operation described below. A maintained-host pass does not replace the later [clean Quick Start](quick-start.md) test.

## Docker Engine and Compose

The current alpha support window is deliberately narrow: **Docker 29.x** on Ubuntu 24.04. An unreviewed **Docker 30** major is rejected — the role should **fail closed** rather than silently cross a major-version boundary.

The Docker role uses package state `present`. Therefore **`make docker` does not upgrade an already-installed Docker Engine** merely because a newer package is available.

Before widening the Docker window:

1. review upstream release/security notes;
2. update the lifecycle policy and role defaults together;
3. run Docker contract/unit/QA checks;
4. prove Coolify, exposure, application delivery, backup/restore, `make verify`, and `make audit` on a disposable target;
5. only then change the supported window.

After a reviewed Docker package change:

```bash
make verify-docker
make verify
make audit
```

A source rollback is not a Docker package downgrade.

## Coolify

Solo VPS manages Coolify through a pinned, reviewed integration. It keeps ownership of the host and Docker configuration instead of handing that responsibility to an unreviewed installer path.

The supported lifecycle pair in this source revision is:

```text
previous supported Coolify: `4.1.1`
current supported Coolify: `4.1.2`
transition:                 4.1.1 -> 4.1.2
AUTOUPDATE=false
```

`make update` and `make platform-lifecycle-plan` are read-only planning surfaces.

### Preflight

Before the supported transition:

```bash
make coolify-upgrade-preflight
```

The preflight checks the managed installation, exact version pair, Docker support window, current runtime health, loopback-only management ports, `AUTOUPDATE=false`, and the absence of an unresolved install/upgrade transaction.

### Upgrade

The mutating path is intentionally confirmation-gated:

```bash
COOLIFY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN \
make coolify-upgrade
```

Before mutation, the upgrade automatically creates a local checkpoint under `/var/lib/solo-vps/checkpoints/coolify-*`: a custom-format Coolify database dump, an archive of `source` (including `.env`), SSH keys and the ownership marker, plus SHA-256 metadata. `pg_restore --list` validates the dump; failure prevents the upgrade. Only root can access it. The checkpoint survives success/failure and its path is recorded in `.solo-vps-upgrading`. S3 and restic are not required.

This copy contains secrets and excludes application data. It cannot survive VPS loss; archive inspection is not a restore test. Pause deployments and UI/ENV changes before upgrading. If forward resume is unsafe, preserve the checkpoint and investigate recovery on a separate test instance at the original version. Automated restore of this local checkpoint is not provided yet. Remove old checkpoints manually only after upgrade verification and your chosen retention period.

### Interrupted upgrade

Solo VPS **does not automatically downgrade Coolify** after an interrupted/failed transition. Coolify **database migrations** may already have run, so blindly restoring only an older container image can create an invalid app/schema pairing.

Inspect the failure first. To explicitly resume the same supported forward transition:

```bash
COOLIFY_UPGRADE_RESUME_CONFIRM=I_HAVE_REVIEWED_THE_INTERRUPTED_COOLIFY_UPGRADE \
make coolify-upgrade-resume
```

Otherwise use the disaster-recovery path with verified recovery inputs. Never delete a transaction marker simply to bypass the safety gate.

## Pinned controller and project dependencies

Treat dependency changes as source-maintenance changes. The authoritative sources are:

| Component | Source of truth |
| --- | --- |
| `community.general` | `ansible/requirements.yml` |
| Ansible QA stack | `tools/qa-requirements.txt` |
| SOPS + age | `tools/secrets-toolchain.json` |
| restic | `ansible/roles/backup/defaults/main.yml` |
| sample Python image | `examples/hello-app/Dockerfile` |
| consumer GitHub Actions | `templates/github-actions/hello-app-ci.yml` |
| Docker/Coolify lifecycle | `docs/contracts/platform-lifecycle-policy.yml` |

Update one dependency class at a time: review upstream notes → change the authoritative pin → run its validators/tests → `make validate` → obtain real integration evidence when runtime behavior changes.

Do not replace exact pins with floating `latest` merely for convenience.

## SOPS, age, and restic

For SOPS/age, update `tools/secrets-toolchain.json` from reviewed releases and re-run the project crypto/toolchain checks before retiring known-good binaries.

For restic, update `ansible/roles/backup/defaults/main.yml` and its hashes. Do not make `restic self-update` the Solo VPS management path.

After a reviewed restic change:

```bash
make validate-backup-tooling
make backup-tooling
make verify-backup-tooling
```

When a real repository exists, also prove repository readability and restore behavior before calling the change operationally verified.

## Optional modules

Optional capabilities are not part of the core upgrade path unless you enabled them. Tailscale, Grafana/Alloy, error tracking, pgAdmin, and shell customization should not force unrelated core upgrades.

Each enabled optional module needs its own version source, verification step, and recovery/data-impact note.

## Rollback and recovery

There is no universal `make rollback`.

| Change | Recovery boundary |
| --- | --- |
| Solo VPS source | return to a reviewed source checkpoint; runtime may still need subsystem recovery |
| SSH/firewall/sudo | provider recovery + proven human-admin access |
| Docker | package/runtime-specific recovery |
| Coolify | explicit forward resume or disaster recovery; no automatic downgrade |
| SOPS/age | retain previous verified tooling until new crypto checks pass |
| restic | retain a known-compatible client until repository + restore compatibility is proven |
| application image | container image rollback only |
| database/schema/data | database backup/restore; image rollback does not roll back data |

If a change cannot describe its recovery path, it is not ready for production execution.

## Upgrade checklist

Before:

```text
[ ] exact current and target versions are known
[ ] target is inside the reviewed support window
[ ] release/security notes were reviewed
[ ] backup/recovery prerequisites are proven
[ ] make validate passes
[ ] make doctor passes
[ ] read-only subsystem preflight passes
[ ] disposable proof is planned for runtime/data-sensitive changes
```

After:

```text
[ ] subsystem verifier passes
[ ] make verify passes
[ ] make audit has no unexplained new finding
[ ] public application behavior is checked
[ ] recovery inputs are retained
[ ] source/version evidence is recorded
```

## Current limitations

At this PRE-ALPHA checkpoint:

- the tagged-checkout source-update contract is documented, but no public release channel or release tag exists yet;
- Docker support is intentionally limited to 29.x rather than generic package auto-upgrades;
- only the Coolify 4.1.1 -> 4.1.2 transition is represented by the current lifecycle source;
- source-level implementation does not substitute for disposable upgrade/recovery evidence;
- off-site backup and isolated restore are integration-proven, but full lost-VPS reconstruction still needs a clean replacement-host exercise;
- optional modules retain separate lifecycle contracts.

See [Disaster recovery](disaster-recovery.md) before any change that can affect data or control-plane recovery.
