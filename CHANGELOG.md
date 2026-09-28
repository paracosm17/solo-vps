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
- A safety-gated Coolify `4.1.2 → 4.3.21` lifecycle with exact release artifacts, Sentinel trust-boundary checks and deterministic interrupted-upgrade recovery. The promoted source passed ordinary verification on a recovered disposable VPS and an independent clean-user core replay.

### Changed

- Rewrite the README and documentation home pages around the maintainer's actual VPS setup and deployment workflow, and present the guided chapters before reference tasks.
- Ask for server, administrator and application repository values in copyable EN/RU first-run commands; clarify the Coolify image digest field and the Git author setup step.
- State the supported VPS resources as minimums and remove the small-VPS evaluation exception from the public Quick Start.
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
- Align the first-app and CI authorization flow with Coolify `4.3.21`: use separate `read` + `write` and deploy-only API tokens because the current non-root token UI makes `deploy` exclusive; refresh the affected Coolify UI labels and remove the stale `4.1.2` creation-form workaround.
- Remove brittle new-resource button wording from the public Coolify walkthroughs, refresh the web-terminal reference, and document Coolify's built-in **Sponsorship reminders** switch as an optional UI preference.

### Security and recovery boundaries

- CRIT-005 is closed at V3: Repository-managed Alloy uses a protected Unix socket and a restricted Docker API proxy; unrelated host users cannot use the collector boundary.
- Image rollback is container-image-only and never claims to reverse database migrations, data changes or external side effects.
- Real Backblaze B2 PostgreSQL restore, restic snapshot/freshness/temporary restore-test and planned reboot recovery are integration-proven.
- Disposable lost-VPS reconstruction, the supported Coolify lifecycle and whole-host DOWN/UP notification passed. Retained logs were also observed again after several days. The public core route has V4 clean-user evidence, including verification, audit and platform idempotency; optional profiles retain separate V3 evidence. No alert-latency or log-retention SLA is claimed.
- No supported release tag exists yet.

[Unreleased]: ./ROADMAP.md
