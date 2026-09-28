# Solo VPS — ROADMAP

> **Last updated:** 2026-09-28
> **Project status:** PRE-ALPHA  
> **Current phase:** first-release productization and runtime evidence
> **Current supported user contract:** [`README.md`](README.md)  
> **Architecture north star:** [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md)  
> **Next action:** prepare the dated `0.1.0` changelog and release notes, then run the final clean release dry-run and exact-ref scans.

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

The owner independently completed the public core route on a separate clean Ubuntu 24.04 VPS at `0fdba7f`. The supplied logs show host setup/hardening, `verify-coolify`, full `verify`, `audit`, and a second `make platform` with `ok=80 changed=0 unreachable=0 failed=0`. The owner reported a working HTTPS application and automatic deployment. This closes the **core V4 clean-user gate**; optional profiles keep their separate V3 evidence. See [the bounded evidence record](reviews/2026-09-28-clean-user-replay.md).

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

## 2. Active first-release work

### Documentation/productization

The public route now treats chapters 1–7 as the guided setup sequence. Failures and maintenance is a separate runbook. Guided commands use semantic `SERVER_IP` / `ADMIN_USER` values, the navigation gives the tutorial more visual weight than reference trees, and the palette is calmer. The upgrade guide defines a new-checkout tagged-source update contract instead of an active-checkout `git pull` workflow.

The owner completed the core public route at `0fdba7f` and reported only first-run wording/input friction. The following merged changes through `659a5a7` contain documentation, CSS, release metadata and one documentation-validator test only. The operational route is equivalent, so clean-user evidence carries forward. Review later candidate changes for the same equivalence.

### Observability evidence

Retained logs are V3: entries survived application redeploy and Alloy restart, and the operator later confirmed that older entries were still searchable after several days. Repository-managed Alloy runs non-root and remains the maintained log-delivery path. This is sufficient for the documented capability; Solo VPS does not claim a fixed retention-duration SLA.

### Coolify lifecycle

The source now supports Coolify `4.3.21`, with `4.1.2` as the previous supported upgrade origin. The reviewed path crosses the [`4.3.19` Sentinel change](https://github.com/coollabsio/coolify/releases/tag/v4.3.19), which made Sentinel mandatory on regular servers. The [official update guide](https://coolify.io/docs/core/instance-management/update) requires an instance backup, release-note review, no active deployments and post-update verification; downgrade does not roll back workloads or their data. The `4.1.2` → `4.3.21` interruption/resume and replacement-host exercises passed, followed by same-host verification of the promoted source.

Sentinel is a Coolify-managed Linux/Docker metrics agent. The old verified "Sentinel absent" result records a `4.1.2` bridge-to-loopback incompatibility; it is not the desired contract for `4.3.19+`. A safety-gated [exercise sheet](docs/coolify-4.3.21-evaluation.md) records exact artifacts, HTTPS push path, the high-trust Docker/host boundary, absence of unintended public ports and interruption/forward-resume behavior. The `database-backup-adopt` API helper fails closed because the `4.3.21` schedule API omits the required S3 storage UUID; Coolify UI backup and isolated B2 restore passed instead. The promoted `4.3.21` source now also has core V4 clean-install and idempotency evidence.

### Publication

The public upstream is `https://github.com/paracosm17/solo-vps`; its initial `main` push started from one clean root commit. Gitleaks found no leaks in the exported tree or earlier published history. No release tag exists. GitHub Pages is deployed at `https://paracosm17.github.io/solo-vps/`; the deployed EN/RU home and Quick Start language links resolve under `/solo-vps/`, and both edit links target the right source file. Private Vulnerability Reporting is enabled, and the public repository security page exposes **Report a vulnerability** to an unauthenticated visitor; a synthetic report from another account is not a Solo VPS runtime gate. Hosted `Repository CI / fast-source` is required by the protected `main` branch. Commit `659a5a7` from PR [#12](https://github.com/paracosm17/solo-vps/pull/12) passed hosted CI and Pages deployment; the eventual release commit still needs its own hosted checks and exact-ref scans before tagging.

---

## 3. Release gates

### Must pass before `v0.1.0`

1. Preserve the completed [core V4 clean-user evidence](reviews/2026-09-28-clean-user-replay.md) at `0fdba7f`, including verification/audit and platform idempotency. Changes through `659a5a7` preserve operational equivalence. Review later candidate diffs; operational changes require the affected clean-host evidence to be repeated.
2. Require a green hosted `Repository CI / fast-source` check and successful documentation deployment for that exact release commit.
3. Before the release tag, repeat exact-ref history and archive scans for secrets and owner-specific state with the built-in check and an independent scanner.
4. Prepare a dated `0.1.0` changelog entry, run the clean release dry-run, review the immutable commit, then create the tag and GitHub Release only with explicit owner approval.

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
| CRIT-004 hosted self-CI / clean target | CORE V4 / HOSTED PASS | independent core replay passed; `fast-source` is required and passed on `659a5a7`; release-commit run pending |
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
| CRIT-017 release/upgrade story | PARTIAL | tagged-source contract documented; Coolify lifecycle V3 passed; first public tag pending |
| CRIT-018 documentation duplication | DONE / V2 | user, architecture, plan and evidence roles separated |
| CRIT-019 optional-feature leakage | DONE / V2 | optional capabilities do not gate the core Quick Start |
| CRIT-020 revision metadata | BLOCKED | immutable public release identity pending |

The Coolify-native Custom FluentBit experiment is **rejected as the maintained default**. Grafana Cloud credential encryption/delivery integration PASS remains historical evidence. Repository-managed non-root Alloy is the maintained retained-log implementation.

---

## 5. Canonical milestone state

| Milestone | Priority | State | Validation / remaining gate |
| --- | --- | --- | --- |
| M1 — Repository Skeleton & Ansible Foundation | P1 | DONE | V2 |
| M2 — Preflight & Configuration Contract | P1 | DONE | V2 + maintained-host use |
| M3 — Base System Role | P1 | DONE | Core V4 |
| M4 — Admin User & SSH Hardening | P1 | DONE | Core V4 |
| M5 — Firewall & Host Exposure Baseline | P1 | DONE | Core V4 |
| M6 — Automatic Security Updates | P1 | DONE | Core V4 |
| M7 — Docker Host | P1 | DONE | Docker 29.x, core V4 |
| M8 — Optional Tailscale Administrative Plane | P3 | DEFERRED | post-release optional work |
| M9 — Coolify Installation Backend | P1 | DONE | supported `4.3.21` clean install and idempotency, core V4 |
| M10 — First End-to-End Application | P1 | DONE | Core V4 |
| M11 — GitHub Actions + GHCR Template | P1 | CORE V4 PASS | owner deployed and updated demo using the public guide at `0fdba7f`; runtime/workflow source unchanged since |
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
| M29 — Upgrade Guide | P2 | SOURCE DONE | tagged-source contract documented; Coolify lifecycle V3 and supported clean install V4 passed; first tagged Solo VPS release pending |
| M30 — Release Process | P2 | SOURCE DONE | hosted dry-run and public release pending |

---

## 6. Batched external-validation window

Use one temporary Ubuntu 24.04 VPS and reimage it between scenarios:

The disposable lifecycle, whole-target outage and lost-VPS reconstruction scenarios have V3 evidence; the independent public core route and platform idempotency have V4 evidence. No new VPS exercise is required for the current operational source. Repeat affected evidence only if a later candidate changes operational behavior.

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

### Remaining blockers

- preserve operational equivalence with the tested source while preparing the release;
- release-commit hosted CI/Pages checks and exact-ref secret/state scans;
- dated changelog, clean release dry-run and immutable `v0.1.0` release identity.

**Current validation:** V4 for the core clean-user route; V3 for separate optional integrations, lifecycle and recovery exercises.
