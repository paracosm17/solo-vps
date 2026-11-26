# Coolify 4.7.8 — source candidate and production gate

## Scope and provenance

- 2026-11-26: official GitHub Releases latest stable is v4.7.8, published 2026-11-25. Review [4.7.4](https://github.com/coollabsio/coolify/releases/tag/v4.7.4), [4.7.5](https://github.com/coollabsio/coolify/releases/tag/v4.7.5), [4.7.6](https://github.com/coollabsio/coolify/releases/tag/v4.7.6), [4.7.7](https://github.com/coollabsio/coolify/releases/tag/v4.7.7), [4.7.8](https://github.com/coollabsio/coolify/releases/tag/v4.7.8) and the [tag comparison](https://github.com/coollabsio/coolify/compare/v4.7.3...v4.7.8).
- Exact origin 4.7.3 from published Solo VPS v0.2.7; target official `docker.io/coollabsio/coolify:4.7.8`. No intermediate installation of 4.7.7. No new Docker major, proxy, application-image, or host-hardening change.
- The existing [4.7.3 production result](2026-11-10-coolify-473-production.md) is historical evidence, not transferable qualification.

## Release artifacts

Fetched all three files directly at both GitHub tags, recomputed SHA-256 and checked the old values against the previous manifest. The Git blob IDs also match for the unchanged files.

| File | 4.7.8 SHA-256 | Difference |
| --- | --- | --- |
| docker-compose.yml | `2532ee9258e10ad4e86cb3c2b46c29fe9329f5a0dace0f7da410744feec279bd` | Unchanged |
| docker-compose.prod.yml | `96c2cdac4146ab8f62a607fb4902a764aa95392eef6079b896530cec955919d9` | Healthchecks changed |
| .env.production | `7895e54f7c9d40063e76afec9b35839048d91e5c3b5107d64ea49ef6987c304a` | Unchanged |

Upstream `upstream.json` is byte-identical: helper 1.0.19, Sentinel 1.1.5, Traefik 3.7.16. Keep both already reviewed Sentinel Docker index/config identities on origin and target, with no alternate version. No proxy image upgrade is needed. The production Compose healthcheck for the main container is now 10s/12 retries instead of 5s/24; the existing 180s controller health wait is retained. PostgreSQL invokes pg_isready with user and database, and Redis checks authenticated ping with nonzero exit on errors. The container names and control-plane volumes, port mapping and embedded realtime topology are unchanged. Solo VPS adds a read-only check for the two dependency statuses before successful verification; it avoids full Redis inspection because the healthcheck embeds its password.

## Compatibility and migration review

- 4.7.4: failed database backup records older than 60 days are removed; non-public preview deployments again inherit production runtime variables with no preview counterpart.
- 4.7.5: API token UI handles unexpected scope formats; SFTP IPv6 connections corrected.
- 4.7.6/4.7.7: PHP 8.4.28, nginx 1.31.9, Node 24.22.3 and other dependency security updates; PHP-FPM is loopback-only in the container, nginx denies requests for sensitive file types. Check dashboard login, API, Reverb and terminal readiness. No reason to expose a new port.
- 4.7.7: public PR preview variable resolution cannot leak production values; invitation-created accounts have stricter first SSO linking; resource secret reads require the relevant access grant as well as API scope. Existing normal CI deployment is not expected to require broader credentials; verify actual deploy/API access.
- The 4.7.7 Compose changes include repository env_file/include handling, explicit host path resolution, validation of service Compose (API 422 for invalid files), preview isolation and shared-network naming. New include support requires Compose 2.25+, not a new control-plane Compose minimum. Existing service templates/images remain unchanged unless manually changed; do not conflate platform upgrade with application/database image upgrades.
- 4.7.8 specifically fixes 4.7.7's regression where a short-syntax variable-based bind mount could attach an empty host directory in place of an existing Docker volume. The previous volume is retained while its Persistent Storage entry exists; do not remove that entry or change mount paths until the data has been checked. Verify persistent storage on the next controlled deployment; do not force-redeploy all applications.
- Reviewed migration files in the target tag include `2026_11_15_140000_remove_duplicate_environment_variables.php` (keep most recently updated non-empty value per resource/key/preview flag, otherwise most recent; delete duplicates), `2026_11_15_150000_rewrite_websocket_schemes_of_domains.php` (rewrite saved ws/wss resource domains to http/https, not reversible), `2026_11_15_120000_cascade_database_backup_executions_on_schedule_delete.php` (delete orphan execution rows and cascade on schedule deletion), `2026_11_16_085347_clear_unchecked_health_check_response_texts.php` (clear old unused expectations), and `2026_11_17_212555_add_variable_fs_path_to_local_file_volumes_table.php` (new saved-path metadata). Recheck healthcheck expectations, ENV references, data/volume identity, and HTTPS/WebSocket routes without exposing secret values. Do not downgrade the application image against the migrated database.
- Upstream now returns HTTP 503 from /api/health until migrations finish. Existing readiness retries continue to gate the managed version marker; interrupted operations keep the transaction and require explicit forward resume.

## Evidence and runtime gate

- V1 source/artifact review; local manifest fingerprint was recomputed using the repository's canonical JSON hashing algorithm and the previous fingerprint reproduced. Hosted PR CI and unit checks must pass on the candidate; no claim of a complete local suite, live container test, or new V3/V5.
- Maintained VPS: use a new checkout of the exact candidate commit with the same external config/inventory paths; run setup, validate, doctor, updates-plan, verify-firewall and coolify-upgrade-preflight. Require installed 4.7.3, target 4.7.8, mutation=false, and no unresolved transaction. Pause deployments/settings changes and confirm provider console, app health and Sentinel In Sync.
- The repository still requires its automatic root-private control-plane checkpoint, not off-site storage as a command prerequisite. The owner elected to omit additional backups for this test; that does not provide application-volume or VPS-loss recovery and does not waive the checkpoint. Production guidance remains to have verified external recovery inputs before migration.
- After the guarded upgrade require `make verify-coolify`, `make verify`, `make audit`, healthy Coolify/PostgreSQL/Redis/Sentinel/proxy, no pending transaction, dashboard and actual application smoke, including a controlled deployment/API test and persistent storage checks where applicable. Do not publish before owner confirmation and release gates. Record only observed results in a separate production evidence file and renew qualification then.
