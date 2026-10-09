# Changelog

This file records user-visible Solo VPS changes intended for tagged releases.

Solo VPS is an alpha project. Published versions are listed in [GitHub Releases](https://github.com/paracosm17/solo-vps/releases).

## [Unreleased]

## [0.2.2] - 2026-10-09

### Changed

- Qualify Coolify 4.4.2 → 4.4.3 with controlled interruption/resume, checkpoint restore and preserved production workloads; retain Traefik 3.7.14.
- Initialize the built-in Coolify server name from configured hostname while preserving custom names and connection/resource identities.
- Keep the external CI/immutable Docker Image reference and explain Git-source/App/Compose alternatives.

### Fixed

- Render current versions from the shared manifest and remove historical platform notes from public EN/RU guides.
- Exclude ADRs and internal maintainer pages from site publication/search; retain repository decisions.

## [0.2.1] - 2026-10-08

### Added

- Explicit native Traefik upgrade/preflight/resume/rollback with immutable image identities, private checksummed checkpoints and preserved analytics/TLS settings; versions remain in the shared release manifest.
- Controlled Coolify 4.4.0 → 4.4.2 patch qualification and Traefik 3.6.25 → 3.7.14 interruption/resume and rollback evidence.

### Fixed

- Make documentation command-field labels and controls readable in the dark theme.
- Preserve native YAML image spelling on no-op proxy reruns and pin the previous image digest during recovery instead of following a floating tag.

## [0.2.0] - 2026-10-07

### Added

- Local documentation values for copyable commands, read-only update discovery and version-neutral Coolify evaluation commands.
- Reviewed Coolify release manifest shared by Ansible, update discovery, lifecycle planning, restore verification and generated documentation.
- Coolify 4.3.21 to 4.4.0 upgrade with Reverb port policy, preserved credentials and artifact-bound forward resume; controlled test-VPS replay, checkpoint restore, one-token deployment/rollback and reboot passed; the maintained production upgrade passed full verification/audit and preserved business containers.

### Fixed

- Use one Coolify API token with read, write and deploy in the CI template and operator helpers.
- Use shell-portable input prompts and identify VPS-only host-key commands explicitly.
- Retire only the owned legacy realtime container before embedded Reverb starts; verify native Sentinel reconciliation against reviewed origin/target identities.
- Persist the TCP-only proxy policy through native Coolify configuration; protect forbidden ingress before Docker starts workloads and preserve shared firewall rules.
- Collect routed interfaces for standalone firewall commands, verify effective Docker guard execution and accept equivalent UTC zoneinfo aliases.

## [0.1.0] - 2026-09-28

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

- Rebuild the EN/RU README around capabilities, requirements and installation, with CI/docs/license badges and a deployment diagram; remove development-status banners from the public guides.
- Remove obsolete installation notes and duplicated release planning; retain current contributor rules and summarized runtime evidence.

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
- Refresh Coolify token setup and affected UI labels; remove the stale `4.1.2` creation-form workaround.
- Remove brittle new-resource button wording from the public Coolify walkthroughs, refresh the web-terminal reference, and document Coolify's built-in **Sponsorship reminders** switch as an optional UI preference.

### Security and recovery boundaries

- Repository-managed Alloy uses a protected Unix socket and a restricted Docker API proxy; unrelated host users cannot use the collector boundary.
- Image rollback is container-image-only and never claims to reverse database migrations, data changes or external side effects.
- Real Backblaze B2 PostgreSQL restore, restic snapshot/freshness/temporary restore-test and planned reboot recovery are integration-proven.
- Disposable lost-VPS reconstruction, the supported Coolify lifecycle and whole-host DOWN/UP notification passed. Retained logs were also observed again after several days. The public core route has V4 clean-user evidence, including verification, audit and platform idempotency; optional profiles retain separate V3 evidence. No alert-latency or log-retention SLA is claimed.
- This alpha supports one Ubuntu 24.04 VPS with Coolify `4.3.21`. It has no high-availability, alert-latency or fixed log-retention guarantee.

[Unreleased]: ./ROADMAP.md
