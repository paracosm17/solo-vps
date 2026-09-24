# Stable-alpha release plan

This document is the short execution plan from the current PRE-ALPHA state to the first public Solo VPS alpha. It exists to keep the release path aligned with the product premise: **one operator workstation + one compute VPS**, with optional managed external services for artifacts, backup and monitoring.

## Why a temporary second VPS can appear in testing

A second VPS is **not** a runtime requirement and is not a high-availability node. It is a short-lived release-test fixture used to prove properties that cannot be established safely on the maintained VPS:

- a clean Ubuntu 24.04 install has no hidden state or maintainer-only prerequisite;
- a second full apply converges idempotently;
- a lost-VPS recovery can restore onto a host that did not already contain the old state;
- SSH/Coolify upgrade/recovery behavior can be exercised without risking the maintained server;
- the final user documentation can be followed literally from zero.

Do not rent this target early. Complete source-side recovery and UX work first, then batch the external proofs into one short validation window and reimage/reuse the same temporary compute when a scenario requires a clean host.

## Backup topology

The core product does not require a second operator-managed storage server. The intended backup topology is:

```text
workstation + one Solo VPS
          |
          +--> managed S3-compatible object storage (off-site encrypted restic data)
```

Managed object storage is intentionally different from a second VPS: the operator does not patch, harden, monitor or recover another operating system.

Self-hosted MinIO/S3 on another VPS may be documented later as an advanced option, but it is not the default alpha path. It also makes release testing less efficient because the same machine cannot simultaneously be the independent backup store and the clean lost-VPS restore target.

Provider snapshots are useful as a secondary convenience before risky upgrades, but they do not replace off-site backups: they remain coupled to the provider/account/failure domain.

## Phase A — recovery source completion (no extra VPS)

Primary scope: M14, M15, M16 and CRIT-001. The entire source-side recovery chain is now V2/source-ready: restic operations, Coolify-owned PostgreSQL backup/restore helpers, recovery kit, staged Coolify restore, and lost-VPS orchestration. Real managed storage/replacement-host evidence remains deferred to Phase D.

The source-side recovery target is:

```text
restic repository init/adopt              [M14 source-ready]
→ backup-now / daily schedule              [M14 source-ready]
→ freshness/integrity check                [M14 source-ready]
→ retention/forget/prune safety            [M14 source-ready]
→ temporary control-plane restore test     [M14 source-ready]
→ Coolify/PostgreSQL logical backup integration [M15 source-ready]
→ disposable database restore exercise          [M15 source-ready]
→ control-plane/application restore orchestration [M16 source-ready]
→ lost-VPS recovery runbook/evidence          [M16 source-ready]
```

Local/synthetic object-storage fixtures can validate command behavior, error handling and idempotency, but only a real external repository plus restore target can promote this to V3/V4 evidence.

CRIT-016 is source-closed in this phase: image rollback never claims to reverse database/schema/data mutations; application migrations must be backward-compatible or have an explicit recovery plan.

## Phase B — simplify the product surface (no extra VPS)

Primary scope: CRIT-006, CRIT-007, CRIT-008, CRIT-009, CRIT-018 and CRIT-019.

CRIT-006/CRIT-007 are now source-closed: the normal host-to-Coolify path is `setup -> apply -> secure -> platform -> verify`; `apply` wraps the lower-level bootstrap/admin transition and `secure` keeps the existing two access confirmations. `make help` is bounded to the public lifecycle/obvious operations, while `help-ops`, `help-dev`, and `help-all` preserve advanced discoverability.

CRIT-008/CRIT-009/CRIT-018/CRIT-019 are now source-closed too: README owns the current user contract, Passport is a concise north star, ROADMAP is a short current plan/state file, and the docs index separates user guidance from maintainer/evidence material. The remaining product-surface work before external validation is a polished first-app tutorial plus the final V4 usability proof.

Documentation roles should become explicit:

- README / Quick Start — user truth and the shortest happy path;
- first-production guide — the complete guided setup;
- operations docs — backup/recovery/upgrade/troubleshooting;
- architecture + ADR — design truth;
- ROADMAP — current blockers/next action, not a giant evidence diary;
- maintainer testing/evidence docs — deep proof procedures;
- Passport — concise north star rather than duplicated current state.

## Phase C — remaining pre-validation closure (mostly no extra VPS)

- CRIT-015 source side is complete: provider-neutral external HTTPS health policy, bounded false-positive/latency contract, and sanitized evidence capture are available. Configure a real external monitor/test notification when convenient; the whole-target V3 shutdown proof is safer to finish during the disposable/final validation window.
- CRIT-011 source side is complete: Docker 29.x is a fail-closed alpha window and Coolify supports only the safety-gated previous `4.1.1` → current `4.1.2` transaction with an automatically validated local control-plane checkpoint. Runtime upgrade/recovery proof is deferred to the validation window.
- CRIT-014: when the Solo VPS GitHub repository exists, enable one guaranteed private vulnerability-reporting channel and make SECURITY.md point to it.
- CRIT-017: finalize the first `v0.x` release/update contract and supported version matrix.
- CRIT-020: publish immutable revision/tag metadata with release archives/evidence.
- CRIT-012: review whether the existing restricted SSH tunnel remains the simplest supported CI→Coolify control-plane path. Do not replace a proven secure path merely to reduce line count.

## Phase D — one batched external validation window

Required resources:

```text
1 temporary clean Ubuntu 24.04 VPS
1 managed S3-compatible bucket outside the Solo VPS failure domain
existing workstation/current Solo VPS/GitHub/Grafana accounts
```

Use the temporary VPS sequentially; reimage it between scenarios when clean state matters.

### D1 — CRIT-004 clean-host proof

Run the controlled disposable host-core proof: fresh bootstrap, human access, SSH hardening, root denial, audit and second apply with `changed=0 failed=0`.

### D2 — M14/M15/M16 / CRIT-001 recovery proof

From the maintained VPS, create real encrypted off-site restic/application/database backups. Treat the maintained VPS as unavailable for the restore procedure, bootstrap the temporary clean VPS and recover enough state to redeploy/verify the application and database data.

A restore is the proof; the existence of a restic snapshot is not.

### D3 — CRIT-011 upgrade proof

On the temporary target, establish the previous-supported Coolify `4.1.1` state under the reviewed Docker 29.x window, run `make coolify-upgrade-preflight`, prove the required off-site restic + instance-DB recovery prerequisites, then execute the exact `4.1.1` → `4.1.2` lifecycle. Require `verify-coolify`, `verify`, and `audit` after upgrade. Also exercise one controlled interrupted transaction and prove explicit forward resume or M16 restore semantics; no automatic database-migration downgrade is accepted. Provider snapshot use may be tested here as an optional secondary safety layer.

### D4 — CRIT-015 whole-target outage proof + V4 full user replay

With the public reference app already configured on the temporary target, attach the selected external HTTP monitor, prove its test notification, power off the whole target from the provider control plane, receive the outage alert, power it back on, and receive recovery. Review the provider UI/event artifact plus the sanitized `make uptime-evidence` summary before accepting CRIT-015 V3.

Then reimage/replay the final user journey if the outage exercise was not performed on the exact final-replay state.


Reimage the temporary VPS and act like a first external adopter. Use only the intended user-facing docs and commands:

```text
fresh Ubuntu 24.04
→ Solo VPS setup
→ admin/SSH/firewall/updates/Docker
→ SOPS + age
→ Coolify + HTTPS dashboard/terminal
→ GitHub/GHCR CI/CD
→ reference hello-app
→ successful deploy + failed-deploy rollback understanding
→ Grafana retained logs
→ off-site backup + backup check
→ external uptime alert
→ verify + audit
```

Measure:

- elapsed setup time;
- number of intentional user commands;
- number of config edits/accounts/credentials;
- every point where docs were ambiguous;
- every manual operation that should become automation;
- final `verify`, `audit`, backup freshness and idempotency evidence.

If the experience is not simple enough, fix the product/docs and repeat the relevant part before publication.

## Phase E — reference hello-app tutorial

Keep `hello-app` small enough to understand but rich enough to demonstrate the product. Before alpha, turn it into a guided reference application rather than a generic application framework.

Useful demonstrations:

- health endpoint and visible build/revision information;
- structured request logs that are easy to find in Coolify and Grafana;
- PR tests + no-push Docker build;
- main GHCR immutable publish + Coolify deployment;
- a documented intentionally broken PR exercise;
- a documented failed deployment/automatic rollback exercise;
- a simple safe code change that a new user can make, PR, merge and watch deploy.

A database-backed advanced example can be added only if it materially helps prove M15 restore. Do not make PostgreSQL mandatory for the first hello-app tutorial.

## Phase F — GitHub publication and first alpha

Only when the source and user path are near-frozen:

1. create the Solo VPS upstream repository;
2. run its own `Repository CI / fast-source` on PR, main and manual dispatch;
3. require that exact status check and prove a negative PR is blocked;
4. enable the private security-reporting channel;
5. run release dry-run against clean Git state and immutable revision metadata;
6. freeze README/Quick Start/recovery/upgrade docs to the V4-proven path;
7. publish the reviewed first `v0.x` alpha tag/release.

Consumer `hello-app` CI evidence never substitutes for the Solo VPS repository's own source CI.

## Post-alpha backlog

Keep these outside the first-alpha critical path unless real users expose a need:

- M8 Tailscale automation;
- M21 richer shell/ops UX;
- M23 error tracking;
- M25 pgAdmin;
- broader metrics beyond the proven retained-log slice;
- self-hosted S3/MinIO;
- generic provider integrations;
- generic application starter-template framework;
- HA/multi-node/Kubernetes.
