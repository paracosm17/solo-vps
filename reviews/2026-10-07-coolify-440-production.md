# Coolify 4.4.0 production migration — 2026-10-07

## Scope

Owner-authorized upgrade of the maintained Ubuntu 24.04 production VPS. The owner confirmed production provider console/rescue access. This record contains sanitized results; operator identifiers, credentials, original configuration, full logs and backup artifacts remain private.

Installed Solo VPS source was `29e2c41d3d81043d12e4f71def7d44c74e20cab2`. The clean candidate `23e0925` replaced it in the standard administrator workspace, preserving the old checkout and existing external config/inventory/key paths. Coolify changed from 4.3.21 to 4.4.0. Docker remained 29.8.1; the existing Traefik v3.6 and reviewed Sentinel 1.0.2 stayed healthy.

Evidence: **V5 point-in-time production migration/use** for this bounded operation. It is not a production reliability guarantee, an independent clean-user V4 replay, or qualification of every optional integration.

## Recovery prerequisites

The private backup set contains a Coolify control-plane checkpoint, six PostgreSQL clusters (eight custom database dumps plus cluster globals), three application Redis RDB snapshots, two application PDF volumes, configuration/SSH recovery files and the original source snapshot. PostgreSQL archives passed list and full SQL generation without connecting to a restore database; Redis RDB passed `redis-check-rdb`; tar member streams were fully read. File-volume metadata stayed stable during copying.

The backup was streamed over SSH into age encryption with the owner's existing workstation identity; the identity never went to the VPS. Offhost decryption matched the server bundle SHA-256, every one of the 27 manifest-covered files matched, and encrypted Windows/WSL copies matched. A verification receipt is retained on the VPS. Online database snapshots are independent, not one cross-database transaction. These checks prove readable, intact copies, not a complete production restore rehearsal. The upgrade also created its own fresh private checkpoint before version mutation.

## Results

| Check | Result |
| --- | --- |
| Baseline | Clean source; all existing containers healthy; Docker 29.8.1, Coolify 4.3.21; no active deployment during backup |
| Recovery access | Production console/rescue explicitly confirmed before firewall |
| Exact candidate doctor | Passed, `ok=9 changed=0 failed=0` |
| Firewall prerequisite | Passed, `ok=42 changed=5 failed=0`; fresh workstation SSH/sudo remained usable |
| Origin preflight | Passed, `ok=42 changed=0 failed=0` |
| Supported upgrade | Passed, `ok=139 changed=14 failed=0`; fresh checkpoint retained and transaction marker cleared after verification |
| Full verify | Passed, `ok=163 changed=0 failed=0` |
| Security audit | Passed, `ok=96 changed=0 failed=0` |
| Upgrade rerun | Passed, `ok=87 changed=0 failed=0`; no repeated version mutation |
| Business containers | All 14 retained their image, mounts and start timestamp and remained healthy; applications and their databases were not redeployed/restarted |
| Public application health | Both production bot endpoints returned success, including PostgreSQL and Redis checks, at the original application revisions |
| Platform secret preservation | Six selected credential/identity values matched the pre-upgrade checkpoint privately |
| Management boundary | Supported loopback/private management and native Sentinel checks passed full verification/audit; old standalone realtime retired |
| Reverb | Real local websocket HTTP 101 plus `pusher:connection_established` |
| Terminal | Already enabled; temporary native authenticated session/single-use token reached origin HTTPS websocket and SSH PTY, executed only read-only printf/exit; own smoke session destroyed afterwards |
| Sentinel delivery | Native status `in_sync` with a push age around three seconds |
| Dashboard TLS | Origin HTTPS health returned 200 with valid certificate/SNI |
| Public dashboard health | Cloudflare returned 403 for unauthenticated `/api/health` from workstation/VPS; origin health passed and Cloudflare configuration was not changed |

## Limits and publication

No production reboot, deliberate failed-app rollback, retention/prune or production database restore was executed. The disposable V3 records retain those separate exercises. Optional offsite backup/monitoring target-version coverage, external IPv6 packet proof and an uninterrupted independent browser walkthrough remain separate.

The 0.2.0 release follow-up changes evidence/documentation metadata only. Publish only after the protected-main exact commit passes required CI, Pages, exact-ref secret/history/archive scans and release dry-run. Keep original source, verified encrypted offhost backups and upgrade checkpoint until the owner chooses their retention period.
