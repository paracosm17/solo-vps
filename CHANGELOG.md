# Changelog

This file records user-visible Solo VPS changes intended for tagged releases.

The project is **PRE-ALPHA** and has not published a supported release. Changes remain under `Unreleased` until the first release candidate is accepted.

## [Unreleased]

### Added

- Reproducible Ubuntu 24.04 host automation for administrator access, SSH hardening, UFW, security updates, Docker, verification and audit.
- Pinned Coolify installation and lifecycle planning with loopback-only management ports and explicit interrupted-upgrade recovery semantics.
- A two-part EN/RU setup route from a fresh VPS through a GitHub Actions/GHCR application deployment, runtime configuration and live logs.
- Restricted CI deployment transport, immutable-image verification and bounded failed-image rollback.
- SOPS + age infrastructure/recovery secrets, restic off-site backup tooling, PostgreSQL logical backup/restore and lost-VPS recovery source.
- Optional Grafana Alloy retained logs and host metrics, external uptime guidance and operator maintenance runbooks.
- A tagged-checkout Solo VPS source-update contract that preserves persistent state outside the source tree.
- A safety-gated Coolify `4.3.21` disposable evaluation harness with exact release artifacts, Sentinel trust-boundary checks and deterministic interrupted-upgrade recovery; the supported transition remains `4.1.1 → 4.1.2` until runtime proof exists.

### Changed

- Publish documentation through a GitHub Pages artifact/deployment workflow with a strict pull-request build and scoped deployment permissions.
- Clarify the one-VPS alpha prerequisites, Windows/WSL developer path and release-only external evidence gates.
- Make the public user route task-oriented: chapters 1–7 are guided setup tasks, while failures and maintenance is an operational runbook.
- Replace fixed documentation IP/admin values in the guided route with semantic `SERVER_IP` and `ADMIN_USER` inputs defined before use.
- Give the setup routes stronger navigation emphasis, reduce the visual weight of reference trees and soften the documentation accent palette.
- Keep the core Quick Start independent of Grafana, external storage, Tailscale, error tracking, pgAdmin and shell customization.
- Store installation-specific controller state outside the checkout so reviewed releases can use new source directories without overwriting config or credentials.
- Operator-specific validation values stay outside public source; public evidence records capability and validation level rather than installation identifiers.

### Fixed

- Reject operator-state paths in both the release snapshot and reachable Git history, and enforce `v0.1.0` as the first allowed version.
- Correct Coolify proxy publications so raw management ports remain loopback-only and only reviewed public web ports are exposed.
- Preserve independent human and automation SSH identities through the hardening transition.
- Reconcile Coolify filesystem permissions required by non-root application and PostgreSQL backup operations.
- Distinguish a deployment rejected before mutation from a failed deployment that requires rollback.
- Prevent expected Docker API proxy `403` responses after reboot from being misclassified as Grafana provider-auth failures.
- Align the retained-log and metrics walkthroughs with the operator-verified Grafana Cloud UI.

### Security and recovery boundaries

- CRIT-005 is closed at V3: Repository-managed Alloy uses a protected Unix socket and a restricted Docker API proxy; unrelated host users cannot use the collector boundary.
- Image rollback is container-image-only and never claims to reverse database migrations, data changes or external side effects.
- Real Backblaze B2 PostgreSQL restore, restic snapshot/freshness/temporary restore-test and planned reboot recovery are integration-proven.
- Full lost-VPS reconstruction, a reviewed current Coolify lifecycle, whole-host outage notification and exact-candidate clean replay remain release gates.
- No supported release tag exists yet.

[Unreleased]: ./ROADMAP.md
