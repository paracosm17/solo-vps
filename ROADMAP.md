# Solo VPS — ROADMAP

> **Last updated:** 2026-09-26
> **Project status:** PRE-ALPHA  
> **Current phase:** first-release productization and runtime evidence
> **Current supported user contract:** [`README.md`](README.md)  
> **Architecture north star:** [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md)  
> **Next action:** prove full lost-host reconstruction from off-site inputs on a clean Ubuntu 24.04 VPS before deciding whether to promote the Coolify `4.3.21` lifecycle pins.

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

A separate disposable Ubuntu 24.04 VPS now has V3 evidence for a clean host setup, Coolify `4.1.2` → `4.3.21` forward-resume upgrade, Sentinel, HTTPS demo CI/CD, B2/restic recovery checks, and isolated PostgreSQL restore from B2. Its external monitor delivered real application and whole-host DOWN/UP emails; the whole-host exercise has a private provider screenshot and observation record, while the formal latency summary remains open. This is not V4: complete lost-host reconstruction, retained logs on this target, and the final owner-only public-doc replay remain open.

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

Remaining proof is the exact-candidate owner replay without ChatGPT. Any hidden value, missing UI action, or undocumented recovery step found there is a release defect.

### Time-dependent evidence

The immediate retained-log path is V3: entries survived application redeploy and Alloy restart. Repository-managed Alloy runs non-root and remains the maintained log-delivery path. The deliberately delayed three-day marker lookup is still pending and can now be performed.

### Coolify lifecycle

The source still supports only Coolify `4.1.1 → 4.1.2`. Official upstream review on 2026-09-17 selected `4.3.21` as the **disposable evaluation candidate**, not yet as a supported Solo VPS target. That reviewed path crosses the [`4.3.19` Sentinel change](https://github.com/coollabsio/coolify/releases/tag/v4.3.19), which made Sentinel mandatory on regular servers. The [official update guide](https://coolify.io/docs/core/instance-management/update) requires an instance backup, release-note review, no active deployments and post-update verification; downgrade does not roll back workloads or their data.

Do not change pins from research alone. Sentinel is a Coolify-managed Linux/Docker metrics agent, not a Solo VPS server mode and not Redis Sentinel. The old verified "Sentinel absent" result records a `4.1.2` bridge-to-loopback incompatibility; it is not the desired contract for `4.3.19+`. A committed, safety-gated [exercise sheet](docs/coolify-4.3.21-evaluation.md) now proves the exact candidate artifacts, an HTTPS push path, the high-trust Docker/host boundary, absence of unintended public ports and deterministic interruption/forward-resume behavior. The disposable Ubuntu 24.04 evaluation reached `4.3.21` with an intentional interruption and explicit forward resume. Sentinel is healthy; candidate verification passed with `changed=0 failed=0`; the HTTPS demo app passed hosted CI and deployed a new image. The `database-backup-adopt` API helper fails closed because the `4.3.21` schedule API omits the required S3 storage UUID; Coolify UI backup and isolated B2 restore passed instead. The supported `4.1.2` pin remains until the remaining runtime/recovery gates and policy review are complete.

### Publication

The public upstream is `https://github.com/paracosm17/solo-vps`; its initial `main` push started from one clean root commit. Gitleaks found no leaks in the exported tree or current published history. No release tag exists. GitHub Pages is deployed at `https://paracosm17.github.io/solo-vps/`; the deployed EN/RU home and Quick Start language links resolve under `/solo-vps/`, and both edit links target the right source file. Private Vulnerability Reporting is enabled; an independent reporter-path test remains. Hosted `Repository CI / fast-source` passed on `3217146` and is required by the protected `main` branch. PR [#9](https://github.com/paracosm17/solo-vps/pull/9) has green hosted checks for the `4.3.21` evidence and backup documentation; merge is pending. Repeat hosted CI on the eventual release commit and exact-ref scanning before tagging.

---

## 3. Release gates

### Must pass before `v0.1.0`

1. Complete the delayed three-day retained-log lookup.
2. Choose and implement the reviewed Coolify release/lifecycle target.
3. On one disposable Ubuntu 24.04 VPS, prove clean install, second-run idempotency, supported Coolify upgrade/interruption recovery, whole-host DOWN/UP notification, and full lost-VPS reconstruction.
4. Replay the exact candidate using only rendered public documentation and no ChatGPT or maintainer notes.
5. Require a green hosted `Repository CI / fast-source` check for the release commit.
6. Test the enabled private vulnerability-reporting path from a reporter account.
7. Before the release tag, repeat exact-ref history and archive scans for secrets and owner-specific state with the built-in check and an independent scanner.
8. Prepare a dated `0.1.0` changelog entry, clean release dry-run, immutable tag and release notes.

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
| CRIT-001 backup/restore/DR | PARTIAL V3 | Disposable-host B2/restic checks, off-VPS recovery kit verification, and isolated PostgreSQL restore pass; clean replacement-host reconstruction pending |
| CRIT-002 failed deploy rollback | DONE / V3 | failed immutable candidate restores the known-good image; database rollback excluded |
| CRIT-003 workstation admin key | DONE / V3 | independent human key, sudo, root denial and hardening gate proven |
| CRIT-004 hosted self-CI / clean target | HOSTED CHECK PASS / V3 | `fast-source` is required on `main` and passed on PR #9; disposable host-core execution passed; release-commit run pending |
| CRIT-005 observability confidentiality | DONE / V3 | Repository-managed non-root Alloy uses a protected Unix socket boundary |
| CRIT-006 Quick Start complexity | SOURCE DONE / V2 | two-part route and semantic values implemented; exact-candidate user replay pending |
| CRIT-007 operator help surface | DONE / V2 | bounded `help`, `help-ops`, `help-dev`, `help-all` |
| CRIT-008 Passport factual drift | DONE / V2 | Passport is design boundary; README owns current user contract |
| CRIT-009 ROADMAP sprawl | DONE / V2 | current state, gates and next action are concise |
| CRIT-010 contract-test imbalance | PARTIAL | source gates exist; runtime V4 evidence remains higher priority than more wording tests |
| CRIT-011 Docker/Coolify lifecycle | PARTIAL V3 | Disposable `4.1.2` → `4.3.21` interruption/resume and candidate verification pass; supported pins and API backup adoption need a reviewed decision |
| CRIT-012 CI deployment transport | DEFERRED | restricted SSH tunnel remains the proven default |
| CRIT-013 recovery priority | CLOSED | recovery path implemented before optional observability expansion |
| CRIT-014 private security channel | PARTIAL | GitHub Private Vulnerability Reporting enabled; independent reporter-path test pending |
| CRIT-015 external outage detection | PARTIAL V3 | Provider-level VPS shutdown/restart produced real DOWN/UP emails and private evidence; formal latency record remains open |
| CRIT-016 migration safety | DONE / V2 | app-owned preflight and image-only rollback boundary |
| CRIT-017 release/upgrade story | PARTIAL | tagged-source contract documented; first tag and lifecycle proof pending |
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
| M3 — Base System Role | P1 | DONE | V3; V4 replay pending |
| M4 — Admin User & SSH Hardening | P1 | DONE | V3; V4 replay pending |
| M5 — Firewall & Host Exposure Baseline | P1 | DONE | V3; V4 replay pending |
| M6 — Automatic Security Updates | P1 | DONE | V3; V4 replay pending |
| M7 — Docker Host | P1 | DONE | Docker 29.x V3; V4 pending |
| M8 — Optional Tailscale Administrative Plane | P3 | DEFERRED | post-release optional work |
| M9 — Coolify Installation Backend | P1 | DONE | `4.3.21` candidate upgrade/resume V3; supported pin decision pending |
| M10 — First End-to-End Application | P1 | DONE | V3 |
| M11 — GitHub Actions + GHCR Template | P1 | DONE | consumer repository V3 |
| M12 — Dependency & Image Hygiene | P2 | DONE | V2 |
| M13 — Infrastructure Secrets with SOPS + age | P1 | DONE | V3 |
| M14 — Off-Site Restic Backup | P1 | DONE | B2 snapshot/freshness/restore-test V3 |
| M15 — Database-Aware Backup Strategy | P1 | DONE | local and off-site isolated restore V3 |
| M16 — Disaster Recovery & Restore Test | P1 | SOURCE DONE | V2; replacement-host V4 pending |
| M17 — `make doctor` expansion | P2 | DONE | V2 + maintained-host use |
| M18 — `make verify` | P2 | DONE | V2 + maintained-host use |
| M19 — Security Audit | P2 | DONE | V3 |
| M20 — Automated Integration Testing | P2 | IN PROGRESS | disposable candidate and hosted demo CI/CD V3; complete V4 replay pending |
| M21 — Author Shell / Ops UX | P3 | DEFERRED | post-release optional work |
| M22 — UI-first Operational Visibility | P2 | DONE | V3 |
| M23 — Application Error Tracking UX | P3 | DEFERRED | post-release optional work |
| M24 — Professional Observability UX | P3 | DONE | optional retained logs and metrics V3; expansion frozen |
| M25 — PostgreSQL Application UX / Guidance | P3 | DEFERRED | optional DB administration work |
| M26 — Public README & Quick Start | P1 | SOURCE DONE | release productization V2; owner-only V4 replay pending |
| M27 — Architecture Documentation & ADR | P2 | DONE | V2 |
| M28 — SECURITY / CONTRIBUTING / LICENSE | P2 | DONE | V2; private reporting setting pending |
| M29 — Upgrade Guide | P2 | SOURCE DONE | tagged-source contract documented; Coolify target/proof pending |
| M30 — Release Process | P2 | SOURCE DONE | hosted dry-run and public release pending |

---

## 6. Batched external-validation window

Use one temporary Ubuntu 24.04 VPS and reimage it between scenarios:

1. clean install and second-run `changed=0`, `failed=0`;
2. supported Coolify install/upgrade and controlled interrupted-transition recovery;
3. whole-target external outage and recovery notification;
4. complete lost-VPS reconstruction from off-site recovery inputs;
5. final exact-candidate first-user replay.

The maintained product topology remains one VPS.

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

- three-day Grafana marker lookup;
- supported Coolify pin decision after lost-host reconstruction and remaining candidate proof;
- replacement-host recovery and formal whole-host alert timing summary;
- exact-candidate owner replay;
- independent private-reporting path test, release-commit hosted CI and immutable release identity.

**Target validation:** V3 for individual real integrations; V4 only after the complete clean-user replay.
