# Solo VPS — ROADMAP

> **Last updated:** 2026-10-07
> **Current phase:** 0.2.0 alpha preparation and authorized production migration
> **Current supported user contract:** [`README.md`](README.md)  
> **Architecture north star:** [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md)  
> **Next action:** complete the authorized production migration, record verification, then publish 0.2.0 from a clean exact commit after required CI/Pages/scans and release dry-run.

This file is intentionally short. It records what is true now, what blocks release, and what happens next. Historical implementation detail belongs in Git history, [`CHANGELOG.md`](CHANGELOG.md), or bounded review/evidence files.

---

## 1. Current snapshot

The maintained VPS has V3 operator evidence for the complete guided route:

```text
Ubuntu 24.04 host
→ administrator access and SSH hardening
→ Docker and Coolify
→ GitHub Actions / GHCR application delivery
→ runtime configuration and live logs
→ retained logs
→ PostgreSQL backup and isolated restore
→ external uptime alert
→ Backblaze B2 + restic off-site backup/restore-test
→ host metrics and alert delivery
→ failed-image rollback and planned reboot recovery
```

A disposable Ubuntu 24.04 VPS has V3 evidence for Coolify `4.1.2` → `4.3.21` interruption/forward-resume, Sentinel, HTTPS demo CI/CD, whole-host DOWN/UP emails and lost-VPS reconstruction from off-site inputs. Recovery restored Coolify identity, PostgreSQL and the immutable demo; HTTPS, platform verification/audit, a new restic snapshot, its restore-test and the daily timer passed. Older retained logs and notification delivery were also confirmed by the owner. No alert-latency or retention SLA is claimed.

The owner independently completed the public core route on a separate clean Ubuntu 24.04 VPS at `0fdba7f`. The supplied logs show host setup/hardening, `verify-coolify`, full `verify`, `audit`, and a second `make platform` with `ok=80 changed=0 unreachable=0 failed=0`. The owner reported a working HTTPS application and automatic deployment. This closed the **0.1.0 core V4 clean-user gate**; optional profiles keep their separate V3 evidence. See [the bounded evidence record](reviews/2026-09-28-clean-user-replay.md).

### Validation levels

```text
V0  not validated
V1  static/lint/syntax
V2  local/unit/source behavior
V3  integration/controlled real environment
V4  complete clean Ubuntu VPS replay
V5  real production-use evidence
```

`DONE` means done only at the stated level.

### Product boundary

- **There is exactly one VPS** in the maintained compute topology.
- The controller and recovery-secret source is the normal **home workstation (Windows or Linux)**.
- GitHub/GHCR, object storage, Grafana Cloud and uptime monitoring are managed external services.
- A disposable/replacement VPS is validation or recovery infrastructure, not a permanent second node.
- Team access-control automation and shell customization remain post-`v0.1.0` work.

---

## 2. Active maintenance work

The owner confirms `v0.1.0` alpha is public and two real applications run on it. Their public health endpoints responded successfully on 2026-10-07; this is a point-in-time check, not a production audit.

Implemented one read/write/deploy token, shell-portable prompts and local documentation values, one reviewed release manifest, version-neutral evaluation commands and read-only update discovery. The 4.3.21 → 4.4.0 transition has V3 controlled test evidence for interruption/resume, checkpoint database restore, no-op rerun, verification/audit, websocket/terminal, one-token app delivery/rollback and reboot. See [the bounded runtime record](reviews/2026-10-07-coolify-440-runtime.md) and [upgrade architecture](docs/adr/0006-reviewed-update-channels.md).

The owner-reset fresh host reached healthy Coolify 4.4.0, HTTPS app deployment/rollback, full verification/audit and an idempotent platform rerun. First-start proxy policy, standalone firewall facts and UTC alias verification were corrected during the replay. Two reboot checks finished; the corrected final source passed full verification/audit, native websocket and real ingress packet checks. Temporary API credentials were revoked and removed; production still needs its own recovery prerequisites. See [the controlled fresh-host record](reviews/2026-10-07-coolify-440-clean-runtime.md). This corrected-source resume is V3, not an uninterrupted V4 user replay.

### Documentation/productization

The public README now leads with product capabilities, requirements and the two-part setup guide. Obsolete installation notes and duplicated planning documents have been removed; writing rules live in `.github/DOCUMENTATION.md`. Historical runtime results are summarized in [the integration evidence record](reviews/2026-09-28-runtime-evidence-summary.md), while the gates below remain the current release checklist.

The public route now treats chapters 1–7 as the guided setup sequence. Failures and maintenance is a separate runbook. Guided commands use semantic `SERVER_IP` / `ADMIN_USER` values, the navigation gives the tutorial more visual weight than reference trees, and the palette is calmer. The upgrade guide defines a new-checkout tagged-source update contract instead of an active-checkout `git pull` workflow.

The owner completed the core public route at `0fdba7f` and reported only first-run wording/input friction. Changes through `dabf740` contain documentation, CSS, release metadata and documentation-validator tests only. Final preparation fills the license notice, prepares the dated changelog and release notes, and simplifies EN/RU public text. The operational route is equivalent, so clean-user evidence carries forward. Review later candidate changes for the same equivalence.

### Observability evidence

Retained logs are V3: entries survived application redeploy and Alloy restart, and the operator later confirmed that older entries were still searchable after several days. Repository-managed Alloy runs non-root and remains the maintained log-delivery path. This is sufficient for the documented capability; Solo VPS does not claim a fixed retention-duration SLA.

### Coolify lifecycle

The published `0.1.0` source supported Coolify `4.3.21`, with `4.1.2` as the previous upgrade origin. The current source qualifies `4.3.21 → 4.4.0` at V3 on a disposable VPS, including native Sentinel `1.0.2`; fresh-install and production evidence remain separate. The reviewed path crosses the [`4.3.19` Sentinel change](https://github.com/coollabsio/coolify/releases/tag/v4.3.19), which made Sentinel mandatory on regular servers. The [official update guide](https://coolify.io/docs/core/instance-management/update) requires an instance backup, release-note review, no active deployments and post-update verification; downgrade does not roll back workloads or their data. The `4.1.2` → `4.3.21` interruption/resume and replacement-host exercises passed, followed by same-host verification of the promoted source.

Sentinel is a Coolify-managed Linux/Docker metrics agent. The old verified "Sentinel absent" result records a `4.1.2` bridge-to-loopback incompatibility; it is not the desired contract for `4.3.19+`. A safety-gated [exercise sheet](docs/coolify-4.3.21-evaluation.md) records exact artifacts, HTTPS push path, the high-trust Docker/host boundary, absence of unintended public ports and interruption/forward-resume behavior. The `database-backup-adopt` API helper fails closed because the `4.3.21` schedule API omits the required S3 storage UUID; Coolify UI backup and isolated B2 restore passed instead. The promoted `4.3.21` source now also has core V4 clean-install and idempotency evidence.

### Publication

The public upstream is `https://github.com/paracosm17/solo-vps`; its initial `main` push started from one clean root commit. Gitleaks found no leaks in the exported tree or earlier published history. The owner confirms the `v0.1.0` alpha is published. GitHub Pages is deployed at `https://paracosm17.github.io/solo-vps/`; the deployed EN/RU home and Quick Start language links resolve under `/solo-vps/`, and both edit links target the right source file. Private Vulnerability Reporting is enabled, and the public repository security page exposes **Report a vulnerability** to an unauthenticated visitor; a synthetic report from another account is not a Solo VPS runtime gate. Hosted `Repository CI / fast-source` is required by the protected `main` branch. Commit `dabf740` from PR [#13](https://github.com/paracosm17/solo-vps/pull/13) passed hosted CI and Pages deployment; the eventual release commit still needs its own hosted checks and exact-ref scans before tagging.

---

## 3. Release gates

### Retained `v0.1.0` release procedure

1. Preserve the completed [core V4 clean-user evidence](reviews/2026-09-28-clean-user-replay.md) at `0fdba7f`, including verification/audit and platform idempotency. Changes through `dabf740` and the final documentation/license preparation preserve operational equivalence. Review later candidate diffs; operational changes require the affected clean-host evidence to be repeated.
2. Require a green hosted `Repository CI / fast-source` check and successful documentation deployment for that exact release commit.
3. Before the release tag, repeat exact-ref history and archive scans for secrets and owner-specific state with the built-in check and an independent scanner.
4. The dated `0.1.0` changelog entry and [release notes](releases/v0.1.0.md) are prepared. Run the clean release dry-run and review the immutable commit. The owner subsequently published the alpha. The owner subsequently authorized production migration and a new release; the 0.2.0 gates below apply.

### Current 0.2.0 alpha gates

- Preserve the controlled 4.4.0 upgrade and owner-reset fresh-host evidence at V3, including corrected-source resume, native proxy lifecycle, real ingress packets, verification/audit and idempotency. Do not carry the original source's independent V4 label onto the changed route.
- Complete the authorized production migration with verified offhost backups, production recovery access and exact-origin preflight; record actual results without a reliability guarantee.
- Require green protected-main source CI, successful Pages deployment, exact-ref history/archive secret scans and `release-dry-run RELEASE_VERSION=v0.2.0` before tagging.
- Publish bounded release notes that preserve separate optional backup/monitoring, external IPv6 packet and uninterrupted browser-walkthrough limits.

### Explicitly deferred

- developer/team onboarding, dev/prod permissions and offboarding workflow;
- optional shell tools, zsh profiles and theme catalog;
- additional observability components;
- Tailscale, error tracking and database administration UI;
- multi-node, HA, Kubernetes/Nomad and self-hosted S3.

---

## 4. Critic-review state

| Finding | State | Current evidence / remaining work |
| --- | --- | --- |
| CRIT-001 backup/restore/DR | RECOVERY PASS / V3 | Clean replacement host rebuilt from off-VPS inputs; Coolify, PostgreSQL, immutable app, HTTPS, new restic snapshot and restore-test passed; optional recovery stays V3 |
| CRIT-002 failed deploy rollback | DONE / V3 | failed immutable candidate restores the known-good image; database rollback excluded |
| CRIT-003 workstation admin key | DONE / V3 | independent human key, sudo, root denial and hardening gate proven |
| CRIT-004 hosted self-CI / clean target | CORE V4 / HOSTED PASS | 0.1.0 independent V4 retained for original source; 4.4.0 controlled replay V3; final release-commit CI pending |
| CRIT-005 observability confidentiality | DONE / V3 | Repository-managed non-root Alloy uses a protected Unix socket boundary |
| CRIT-006 Quick Start complexity | CORE V4 PASS | owner completed both public chapters unaided at `0fdba7f`; first-run copy/paste feedback addressed in docs-only follow-up |
| CRIT-007 operator help surface | DONE / V2 | bounded `help`, `help-ops`, `help-dev`, `help-all` |
| CRIT-008 Passport factual drift | DONE / V2 | Passport is design boundary; README owns current user contract |
| CRIT-009 ROADMAP sprawl | DONE / V2 | current state, gates and next action are concise |
| CRIT-010 contract-test imbalance | CORE V4 PASS | source gates and independent clean-user route passed; avoid additional wording tests without a concrete risk |
| CRIT-011 Docker/Coolify lifecycle | CORE V4 / LIFECYCLE V3 | Supported `4.3.21` clean install/idempotency passed; upgrade/resume and recovery passed at V3; API backup adoption remains fail-closed |
| CRIT-012 CI deployment transport | DEFERRED | restricted SSH tunnel remains the proven default |
| CRIT-013 recovery priority | CLOSED | recovery path implemented before optional observability expansion |
| CRIT-014 private security channel | DONE | GitHub Private Vulnerability Reporting enabled; public **Report a vulnerability** entry verified |
| CRIT-015 external outage detection | DONE / V3 | Provider-level VPS shutdown/restart produced real DOWN/UP emails outside the VPS; operator observed delivery within a few minutes, with no latency SLA claimed |
| CRIT-016 migration safety | DONE / V2 | app-owned preflight and image-only rollback boundary |
| CRIT-017 release/upgrade story | V3 PASS | 0.1.0 alpha published; update discovery and controlled 4.4.0 upgrade/resume/recovery passed; production migration remains separate |
| CRIT-018 documentation duplication | DONE / V2 | user, architecture, plan and evidence roles separated |
| CRIT-019 optional-feature leakage | DONE / V2 | optional capabilities do not gate the core Quick Start |
| CRIT-020 revision metadata | BLOCKED | 0.2.0 immutable identity pending |

The Coolify-native Custom FluentBit experiment is **rejected as the maintained default**. Grafana Cloud credential encryption/delivery integration PASS remains historical evidence. Repository-managed non-root Alloy is the maintained retained-log implementation.

---

## 5. Canonical milestone state

| Milestone | Priority | State | Validation / remaining gate |
| --- | --- | --- | --- |
| M1 — Repository Skeleton & Ansible Foundation | P1 | DONE | V2 |
| M2 — Preflight & Configuration Contract | P1 | DONE | V2 + maintained-host use |
| M3 — Base System Role | P1 | DONE | Core V4 |
| M4 — Admin User & SSH Hardening | P1 | DONE | Core V4 |
| M5 — Firewall & Host Exposure Baseline | P1 | DONE | 4.4.0 guard/policy V3; original source V4 retained separately |
| M6 — Automatic Security Updates | P1 | DONE | Core V4 |
| M7 — Docker Host | P1 | DONE | Docker 29.x, core V4 |
| M8 — Optional Tailscale Administrative Plane | P3 | DEFERRED | post-release optional work |
| M9 — Coolify Installation Backend | P1 | DONE | supported `4.3.21` clean install and idempotency, core V4 |
| M10 — First End-to-End Application | P1 | DONE | Core V4 |
| M11 — GitHub Actions + GHCR Template | P1 | CORE V4 PASS | owner deployed and updated demo using the public guide at `0fdba7f`; original source V4 retained; new single-token workflow V3, not unchanged since |
| M12 — Dependency & Image Hygiene | P2 | DONE | V2 |
| M13 — Infrastructure Secrets with SOPS + age | P1 | DONE | V3 |
| M14 — Off-Site Restic Backup | P1 | DONE | B2 snapshot/freshness/restore-test V3 |
| M15 — Database-Aware Backup Strategy | P1 | DONE | local and off-site isolated restore V3 |
| M16 — Disaster Recovery & Restore Test | P1 | DONE | Replacement-host recovery V3; optional recovery not promoted by the core replay |
| M17 — `make doctor` expansion | P2 | DONE | V2 + maintained-host use |
| M18 — `make verify` | P2 | DONE | V2 + maintained-host use |
| M19 — Security Audit | P2 | DONE | V3 |
| M20 — Automated Integration Testing | P2 | CORE REPLAY PASS | independent core V4; final release-commit source/hosted checks pending |
| M21 — Author Shell / Ops UX | P3 | DEFERRED | post-release optional work |
| M22 — UI-first Operational Visibility | P2 | DONE | V3 |
| M23 — Application Error Tracking UX | P3 | DEFERRED | post-release optional work |
| M24 — Professional Observability UX | P3 | DONE | optional retained logs and metrics V3; expansion frozen |
| M25 — PostgreSQL Application UX / Guidance | P3 | DEFERRED | optional DB administration work |
| M26 — Public README & Quick Start | P1 | CORE V4 PASS | owner completed both public chapters independently at `0fdba7f`; first-run wording/input polish merged in `bf02b74` |
| M27 — Architecture Documentation & ADR | P2 | DONE | V2 |
| M28 — SECURITY / CONTRIBUTING / LICENSE | P2 | DONE | V2; private reporting enabled and public reporter entry verified |
| M29 — Upgrade Guide | P2 | V3 PASS | 4.4.0 test-VPS upgrade/resume/recovery and reboot passed; fresh install and production remain separate gates |
| M30 — Release Process | P2 | SOURCE DONE | hosted dry-run and public release pending |

---

## 6. Batched external-validation window

Use one temporary Ubuntu 24.04 VPS and reimage it between scenarios:

The disposable lifecycle, whole-target outage and lost-VPS reconstruction scenarios have V3 evidence; the independent public core route and platform idempotency have V4 evidence. The changed 4.4.0 route has a separate V3 controlled fresh-host replay with corrected-source resume. An uninterrupted exact-revision browser walkthrough remains unproven; it is not inherited from the old V4 result.

The maintained product topology remains one VPS; another permanent or additional validation server is not required.

---

## 7. Handoff

### Completed in the current productization pass

- chapters 1–7 are the only numbered guided setup tasks;
- failures and maintenance moved to the Maintenance reference group;
- public guided commands use semantic server/admin values instead of a fixed documentation IP and username;
- primary tutorial navigation is visually stronger and the palette is less saturated;
- Solo VPS source updates use a documented new-checkout exact-tag model;
- Passport, ROADMAP and CHANGELOG ownership drift is reconciled.

### Before the next release

- preserve operational equivalence with the tested source while preparing the release;
- release-commit hosted CI/Pages checks and exact-ref secret/state scans;
- clean release dry-run and final review; production migration and 0.2.0 publication are now authorized.

**Current validation:** V3 for the changed 4.4.0 route and controlled fresh-host resume; the original 0.1.0 core retains its own V4 record. Optional integrations and recovery keep separate V3 evidence; production migration is in progress.
