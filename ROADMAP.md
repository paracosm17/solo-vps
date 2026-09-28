# Solo VPS — ROADMAP

> **Last updated:** 2026-09-28
> **Current phase:** post-`v0.1.0` alpha hardening and `v1.0.0` planning
> **Current supported user contract:** [`README.md`](README.md)  
> **Architecture north star:** [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md)  
> **Next action:** begin the security-by-default hardening track with a threat-modelled Fail2Ban/SSH evaluation and a section-by-section review of the external Linux-hardening checklist against Ubuntu 24.04, OpenSSH, Docker and Coolify; do not promote new controls to the default profile until lockout/recovery and runtime compatibility are proven.

This file is intentionally short. It records what is true now, what blocks the next maturity step, and what happens next. Historical implementation detail belongs in Git history, [`CHANGELOG.md`](CHANGELOG.md), releases, or bounded review/evidence files.

---

## 1. Current snapshot

`v0.1.0` is the first public alpha release, tagged from `29e2c41`. The release commit passed the pinned release dry-run, independent reachable-history Gitleaks scan, hosted repository CI, documentation deployment and exact tag/HEAD verification.

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

A disposable Ubuntu 24.04 VPS has V3 evidence for Coolify `4.1.2` → `4.3.21` interruption/forward-resume, Sentinel, HTTPS demo CI/CD, whole-host DOWN/UP notifications and lost-VPS reconstruction from off-site inputs. The owner independently completed the public core route on a separate clean Ubuntu 24.04 VPS at `0fdba7f`; host setup/hardening, `verify-coolify`, full `verify`, `audit`, deployment and repeated `make platform` idempotency passed. This is the **core V4 clean-user gate**. Optional profiles retain separate V3 evidence.

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
- Coolify owns application/project/environment/team operations; Solo VPS owns the host baseline and may document or audit safe access policy without becoming a second RBAC/orchestration layer.
- General-purpose LLM/server-context export and shell customization remain optional post-`v0.1.0` work.

---

## 2. Post-`v0.1.0` product directions

### Security-by-default hardening

The current core already enforces key-only SSH, disables root/password login, limits host ingress with UFW, enables unattended Ubuntu security updates, verifies Docker exposure and provides a read-only security audit. **Fail2Ban is not currently installed or configured.**

Next security work should:

- evaluate a minimal Fail2Ban SSH jail for Ubuntu 24.04 using the actual systemd-journal/UFW path, with safe defaults, explicit verification and an unban/recovery path;
- prove that the control cannot silently lock out the only administrator and does not conflict with provider recovery, Docker networking or Coolify;
- review [`imthenachoman/How-To-Secure-A-Linux-Server`](https://github.com/imthenachoman/How-To-Secure-A-Linux-Server) section by section as a **research checklist**, not as an authority or copy/paste source;
- cross-check every adopted control against current Ubuntu/OpenSSH/Docker/Coolify documentation and, where useful, CIS guidance;
- consider SSH/sudo policy, `/proc` and kernel hardening, intrusion prevention, integrity/audit tooling and additional read-only security checks only when they solve a concrete threat in the one-VPS model.

New hardening belongs in the core default only after source tests plus disposable-VPS evidence show that installation, reconnect, reboot, Coolify and recovery remain safe. Security tools that add substantial services, credentials, false-positive risk or operational burden should stay optional.

### Coolify and Solo VPS lifecycle

The exact `4.3.21` Coolify pin is a safety feature, but the current source contains version-specific evaluation names and a single previous→current transition. That is acceptable for `v0.1.0`, not the desired long-term update experience.

Target direction:

- keep runtime mutations exact-version and fail-closed; never follow floating `latest` or enable unattended Coolify updates merely for freshness;
- add a read-only update discovery/check path that can report a newer upstream Coolify release without changing the VPS;
- move supported version/artifact data into a small lifecycle manifest and make ordinary preflight/upgrade/resume tooling version-generic;
- keep version-specific evidence in review/evaluation records rather than command/file names that must be cloned for every release;
- qualify each promoted Coolify release on a disposable Ubuntu 24.04 VPS for clean install, upgrade/resume, Sentinel, exposure, application deployment and recovery-relevant behavior before a Solo VPS release changes the supported pin;
- make updating Solo VPS itself remain an exact-tag/new-checkout operation with explicit `verify`/`audit` after any platform transition.

The goal is **easy and frequent reviewed upgrades**, not automatic unreviewed upgrades.

### Team access and prod/dev separation

Coolify already owns projects, environments, team membership and application-platform roles. Solo VPS should not build a parallel user/permission system.

Future Solo VPS work may provide a short opinionated team-security guide and audit checklist covering least privilege, 2FA for elevated accounts, Owner/Admin/Member choice, API-token scope/expiry, access review/offboarding and production-vs-development environment separation. Host SSH/sudo access remains a separate infrastructure-admin boundary and should not be granted merely because someone can deploy an application.

### `vps-doctor` / LLM-ready server context

The existing `make doctor` remains Solo VPS-specific preflight/readiness diagnostics. A general-purpose **`vps-doctor`** is a larger product idea and should be researched as a **separate standalone utility/repository**, with an optional Solo VPS integration later rather than a new core dependency.

Desired contract for that utility:

- one-command, read-only collection with no automatic upload/network egress;
- a stable versioned JSON schema as the canonical artifact, with Markdown first and HTML/PDF renderers derived from it;
- topology/deployment-graph inference rather than a flat command dump, for example public endpoint → firewall/proxy → service/container → local port → volume/data path;
- strict secret-value exclusion plus a documented redaction model;
- a stronger `--share` mode with deterministic pseudonyms for public/private IPs, users, domains and project paths while preserving graph relationships;
- explicit provenance, partial/permission-denied states and a list of omitted/truncated data so an LLM does not mistake incomplete context for a clean system;
- token-budget controls and deterministic section prioritization for LLM use;
- tests proving that credentials/private keys/tokens cannot appear in export fixtures.

Before implementation, review adjacent diagnostic/support-bundle tools so this project focuses on the distinctive LLM-safe topology/context problem instead of duplicating generic health checks.

### Optional shell / terminal UX

M21 remains optional. A future one-command shell profile may evaluate Zsh, Zimfw/another lightweight framework, Oh My Posh, `fzf` and a small set of modern Unix utilities/completions.

Rules for this profile:

- never gate the core Quick Start or change root's shell;
- be explicit opt-in and reversible, and back up/avoid overwriting existing dotfiles;
- prefer distro packages or pinned/checksummed artifacts over unattended `curl | sh` installation;
- keep normal SSH/non-interactive automation behavior unchanged;
- provide useful history, completion and navigation without turning Solo VPS into a personal dotfiles distribution.

---

## 3. Path from alpha to `v1.0.0`

`v0.1.x` remains the alpha line for bug fixes, documentation corrections and bounded hardening improvements. A later beta should require V5 real-use evidence plus at least one proven upgrade between published Solo VPS releases and one newly-qualified Coolify lifecycle transition.

`v1.0.0` should mean that the one-VPS contract, source-update procedure, host-security baseline, Coolify lifecycle policy, backup/recovery boundaries and public operator surface are stable enough that ordinary upgrades do not require rediscovering the architecture. Optional ideas such as `vps-doctor`, shell UX, Tailscale, error tracking or database administration UI are **not individually required** for `1.0`; they should ship when their safety and maintenance cost justify them.

---

## 4. Critic-review state

| Finding | State | Current evidence / remaining work |
| --- | --- | --- |
| CRIT-001 backup/restore/DR | RECOVERY PASS / V3 | clean replacement host rebuilt from off-VPS inputs; Coolify, PostgreSQL, immutable app, HTTPS, new restic snapshot and restore-test passed |
| CRIT-002 failed deploy rollback | DONE / V3 | failed immutable candidate restores the known-good image; database rollback excluded |
| CRIT-003 workstation admin key | DONE / V3 | independent human key, sudo, root denial and hardening gate proven |
| CRIT-004 hosted self-CI / clean target | DONE / CORE V4 | independent core replay passed; exact `v0.1.0` release commit also passed hosted repository CI and docs deployment |
| CRIT-005 observability confidentiality | DONE / V3 | repository-managed non-root Alloy uses a protected Unix socket boundary |
| CRIT-006 Quick Start complexity | CORE V4 PASS | owner completed both public chapters independently; first-run friction was corrected before `v0.1.0` |
| CRIT-007 operator help surface | DONE / V2 | bounded `help`, `help-ops`, `help-dev`, `help-all` |
| CRIT-008 Passport factual drift | DONE / V2 | Passport is design boundary; README owns current user contract |
| CRIT-009 ROADMAP sprawl | DONE / V2 | current state, maturity direction and one next action are kept concise |
| CRIT-010 contract-test imbalance | CORE V4 PASS | source gates and independent clean-user route passed; add tests for concrete risks rather than wording volume |
| CRIT-011 Docker/Coolify lifecycle | CORE V4 / LIFECYCLE V3 | `4.3.21` clean install/idempotency passed; `4.1.2 → 4.3.21` upgrade/resume and recovery passed at V3 |
| CRIT-012 CI deployment transport | DEFERRED | restricted SSH tunnel remains the proven default |
| CRIT-013 recovery priority | CLOSED | recovery path implemented before optional observability expansion |
| CRIT-014 private security channel | DONE | GitHub Private Vulnerability Reporting enabled; public reporter entry verified |
| CRIT-015 external outage detection | DONE / V3 | provider-level VPS shutdown/restart produced real DOWN/UP emails; no latency SLA claimed |
| CRIT-016 migration safety | DONE / V2 | app-owned preflight and image-only rollback boundary |
| CRIT-017 release/upgrade story | DONE / V2+ | exact-tag/new-checkout source contract exists and `v0.1.0` was published from an immutable verified commit; future cross-release update evidence is a maturity goal |
| CRIT-018 documentation duplication | DONE / V2 | user, architecture, plan and evidence roles separated |
| CRIT-019 optional-feature leakage | DONE / V2 | optional capabilities do not gate the core Quick Start |
| CRIT-020 revision metadata | DONE | `v0.1.0` tag and GitHub Release identify exact commit `29e2c41` |

---

## 5. Canonical milestone state

| Milestone | Priority | State | Validation / remaining gate |
| --- | --- | --- | --- |
| M1 — Repository Skeleton & Ansible Foundation | P1 | DONE | V2 |
| M2 — Preflight & Configuration Contract | P1 | DONE | V2 + maintained-host use |
| M3 — Base System Role | P1 | DONE | Core V4 |
| M4 — Admin User & SSH Hardening | P1 | DONE | Core V4; future security track may add defense-in-depth without weakening recovery safety |
| M5 — Firewall & Host Exposure Baseline | P1 | DONE | Core V4 |
| M6 — Automatic Security Updates | P1 | DONE | Core V4 |
| M7 — Docker Host | P1 | DONE | Docker 29.x, core V4 |
| M8 — Optional Tailscale Administrative Plane | P3 | DEFERRED | optional post-alpha work |
| M9 — Coolify Installation Backend | P1 | DONE | supported `4.3.21` clean install and idempotency, core V4 |
| M10 — First End-to-End Application | P1 | DONE | Core V4 |
| M11 — GitHub Actions + GHCR Template | P1 | CORE V4 PASS | owner deployed and updated demo using the public guide |
| M12 — Dependency & Image Hygiene | P2 | DONE | V2 |
| M13 — Infrastructure Secrets with SOPS + age | P1 | DONE | V3 |
| M14 — Off-Site Restic Backup | P1 | DONE | B2 snapshot/freshness/restore-test V3 |
| M15 — Database-Aware Backup Strategy | P1 | DONE | local and off-site isolated restore V3 |
| M16 — Disaster Recovery & Restore Test | P1 | DONE | replacement-host recovery V3 |
| M17 — `make doctor` expansion | P2 | DONE | V2 + maintained-host use; general-purpose `vps-doctor` is a separate research track |
| M18 — `make verify` | P2 | DONE | V2 + maintained-host use |
| M19 — Security Audit | P2 | DONE | V3; security-by-default expansion is post-`v0.1.0` work |
| M20 — Automated Integration Testing | P2 | CORE V4 PASS | independent core replay and release source/hosted gates passed |
| M21 — Author Shell / Ops UX | P3 | PLANNED | optional, reversible, pinned/checksummed profile; must not affect core automation |
| M22 — UI-first Operational Visibility | P2 | DONE | V3 |
| M23 — Application Error Tracking UX | P3 | DEFERRED | optional work |
| M24 — Professional Observability UX | P3 | DONE | optional retained logs and metrics V3; expansion frozen |
| M25 — PostgreSQL Application UX / Guidance | P3 | DEFERRED | optional DB administration work |
| M26 — Public README & Quick Start | P1 | CORE V4 PASS | owner completed the public route independently |
| M27 — Architecture Documentation & ADR | P2 | DONE | V2 |
| M28 — SECURITY / CONTRIBUTING / LICENSE | P2 | DONE | V2; private reporting enabled and public reporter entry verified |
| M29 — Upgrade Guide | P2 | DONE / V3 | exact-tag source contract plus one supported Coolify lifecycle; future work makes version promotion less bespoke |
| M30 — Release Process | P2 | DONE | `v0.1.0` published after dry-run, independent secret scan and exact hosted checks |

---

## 6. Batched external-validation window

Use a temporary Ubuntu 24.04 VPS and reimage it between scenarios when a new host/security/lifecycle control needs V3/V4 proof. Do not create a permanent second node merely to validate the product.

The next likely disposable-VPS batch should combine Fail2Ban/security-hardening lockout tests with the next Coolify version qualification when practical. Runtime changes that affect SSH, firewall, Docker or Coolify must repeat the relevant evidence before promotion.

---

## 7. Handoff

The `v0.1.0` release is complete. Keep using the tagged release on a real workload to accumulate V5 evidence while new work lands in `main` through focused PRs.

Near-term planning order:

1. security-by-default review and Fail2Ban candidate;
2. generic/read-only update discovery and less version-specific Coolify lifecycle tooling;
3. team-access/prod-dev guidance without duplicating Coolify RBAC;
4. standalone `vps-doctor` design research;
5. optional shell/terminal UX profile.

**Current validation:** V4 for the core clean-user route; V3 for separate optional integrations, lifecycle and recovery exercises; V5 is the next maturity evidence level.
