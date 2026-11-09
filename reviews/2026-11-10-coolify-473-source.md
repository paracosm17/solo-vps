# Coolify 4.7.3 — 4.6.0 origin, source review and production gate

## Scope and provenance

- Date: 2026-11-10. Stable upstream release sequence: [4.7.0](https://github.com/coollabsio/coolify/releases/tag/v4.7.0), [4.7.1](https://github.com/coollabsio/coolify/releases/tag/v4.7.1), [4.7.2](https://github.com/coollabsio/coolify/releases/tag/v4.7.2) and [4.7.3](https://github.com/coollabsio/coolify/releases/tag/v4.7.3), all published 2026-11-09.
- The **latest stable at review time is 4.7.3**; no prerelease or floating image tag is used.
- Exactly reviewed runtime transition: production-observed Coolify **4.6.0 → 4.7.3**, official `docker.io/coollabsio/coolify:4.7.3`.
- Preserve the previous standalone [4.6.0 production V5 record](2026-11-04-coolify-460-production.md) in PR #36. This branch starts from the **unmerged PR #36 head** as a stacked change; do not discard or rewrite its history to manufacture a direct 4.5.3 → 4.7.3 path.
- Keep Docker Engine 29.x, host-owned UFW ingress guard, non-root resource directory boundary, 127.0.0.1-only ports 8000/6001/6002, auto-upgrades disabled, the transaction marker, checkpoint and explicit forward-resume procedure.

## Artifact and image identities

Directly fetched the official raw files at `v4.6.0` and `v4.7.3` over GitHub and compared their exact contents:

| File | Verified v4.7.3 SHA-256 (already independently computed at v4.6.0) | Byte difference |
| --- | --- | --- |
| `docker-compose.yml` | `2532ee9258e10ad4e86cb3c2b46c29fe9329f5a0dace0f7da410744feec279bd` | none |
| `docker-compose.prod.yml` | `f8b104aadfca48d0033fdee6cb87fea13c68bc5c67c63ba18b1934e9f901ff5d` | none |
| `.env.production` | `7895e54f7c9d40063e76afec9b35839048d91e5c3b5107d64ea49ef6987c304a` | none |

Unchanged upstream Compose is **not** proof that migrations/API permissions or application behavior are unchanged.

- `v4.7.3/upstream.json` sets Sentinel **1.1.5**, versus 1.1.3 at v4.6.0, and retains Traefik **3.7.16**.
- The official Sentinel 1.1.5 release publishes **two distinct, independently evidenced Docker identities**: `linux/amd64` image **config digest** `sha256:e677a5637ab4276589839b7f16b7c0eecd16f36c7e5aff915f45da62f2f7b211` from the successful `build-push` amd64 job **127923179672** (`exporting config sha256:e677a...`), and multi-platform **index digest** `sha256:b3ee40d4d00b508c1018e67dc6a9e5693d0027b117f560c9fb003f464879243e` from successful `merge-manifest` job **127925921800** (`pushing sha256:b3ee40... to docker.io/coollabsio/sentinel:1.1.5`). Both were independently verified in the official [Sentinel v1.1.5 release workflow](https://github.com/coollabsio/sentinel/actions/runs/42227082341). A Docker 29 containerd-backed host can report the index digest in `docker container inspect .Image`, while a classic store reports the platform config ID. The candidate accepts **only these two pinned identities**, conditional on the exact Sentinel 1.1.5 tag/API version and unchanged trust boundary.
- Do **not** confuse that with `v4.7.3/upstream.json`'s `sentinel-host.digest=sha256:05530359731cc5e9aaa05cd85749945e2e6d414c0e36b95f8a17c4adb6ab13b4`: this refers to the separately published **GHCR sentinel-host artifact**, not the Docker container ID accepted by Solo VPS verification.
- Since Coolify can update its managed Sentinel independently, the origin preflight permits the reviewed 1.1.3 or already-updated 1.1.5 **with exact reviewed image identities and API version** (`accept_target: true`). After upgrade, the managed runtime verifier requires **1.1.5 only**, with the same Docker socket, host PID, HTTPS token and no-public-listener boundaries.
- Both Sentinel `v1.1.3` and `v1.1.5` source send the `X-Sentinel-Version` header. Coolify's upstream `v4.7.3` `SentinelController::updateSentinelIfOutdated` receives it during heartbeat and dispatches `CheckAndStartSentinelJob` when the version is behind; `StartSentinel` retains the token in the container environment via a temporary `--env-file`, not CLI arguments. This is a **native asynchronous update path**, not a promise that it will complete during any particular verification window. Preserve the pending transaction if target Sentinel verification fails; investigate and use guarded forward resume rather than force-resetting state.

## Preflight discrepancy and source correction (2026-11-10)

- On the maintained production host, before any upgrade, `make verify-firewall` passed `ok=20 changed=0 failed=0`. `make coolify-upgrade-preflight` rejected Sentinel 1.1.5 after 18 read-only retries with `Sentinel image content does not match the evaluation candidate`; final recap `ok=37 changed=0 failed=1`. Coolify 4.6.0 and Sentinel 1.1.5 were healthy. No Coolify mutation or pending upgrade marker occurred.
- Secret-safe operator metadata showed Sentinel `docker.io/coollabsio/sentinel:1.1.5` / API 1.1.5, runtime `docker inspect .Image=sha256:b3ee40d4d00b508c1018e67dc6a9e5693d0027b117f560c9fb003f464879243e`, platform `linux/amd64`. This index digest matches the **official Docker Hub v1.1.5 manifest publication**, while the initial Solo VPS candidate only pinned the config digest `e677a...`.
- This is a **Solo VPS source identity-model defect**, not evidence of an untrusted or unhealthy live Sentinel. The fix adds the official multi-platform index and config identities to the release manifest, validates both exact SHA-256 values, passes them to the read-only Sentinel verifier, and rejects all unreviewed identities. This correction is source-only, pending exact-head source CI and a fresh production preflight; **Coolify has not been upgraded**.

## Breaking changes and migration review

### 4.7.0 (breaking/security)

1. **Queued webhook deployments:** newer pushes cancel earlier queued webhook deployments per app/PR/server by default. New migration `2026_11_03_072701_add_auto_cancel_superseded_deployments.php` creates `is_auto_cancel_queued_deployments_enabled` with **default true** and `is_auto_cancel_building_deployments_enabled` **false**. Manually triggered, API, restart and rollback deploys are not auto-cancelled; `POST /api/v1/deploy`'s `cancel_previous` defaults to `none`. Applications that must process every webhook build should opt out **after the upgrade, before webhook pushes resume** (the setting and database column are new in 4.7.0).
2. **API authorization:** cloud provider tokens are limited to team owners/admins. More resource-scoped checks now restrict team SSH keys, GitHub/Gitea Apps, S3 storage, server access, preview changes, image-tag changes and repository selection. A deploy token alone cannot create/change a preview or modify an image without write permission. Existing Solo VPS CI deploy-on-image path uses `read`, `write`, `deploy`; verify real resource grants and API `403` before considering token changes. Do not grant root, delete or team-wide write indiscriminately.
3. **Resend sender:** API fields change to `resend_from_address`/`resend_from_name`; a migration copies old values. Audit custom email integrations.
4. **SSH host-key trust:** Coolify pins host keys on first connection; changed server/Git-host keys require verification. Never disable host-key checking to hide a mismatch.
5. **Sentinel:** bumped to 1.1.5 and token removed from process arguments. Native heartbeat-triggered update can lag after the Coolify upgrade, requiring guarded recovery if target verification is not satisfied.
6. **Scheduled tasks:** disabled after 10 consecutive failures where the first failure is older than 24h; database backups and cleanup are not automatically disabled. Scheduled tasks need review after the upgrade.
7. **New-resource defaults:** Redis new default Valkey 9; PostgreSQL 18 and other new database defaults, while existing database images remain unchanged. Optional image vulnerability scanning adds Syft/Grype resource overhead and is **opt-in**, not enabled by this Solo VPS source upgrade.
8. Other hardening: API failed-request rate limit, team access checks, terminal/SMTP controls, image tag validation, private-key browser restrictions. These can reveal previously permissive API clients; they are not grounds to relax permissions.

### 4.7.1–4.7.3 fixes

- 4.7.1 fixes missing scanner templates on self-hosted instances, maintenance mode with custom labels/wildcards and vulnerability UI.
- 4.7.2 hardens destination Stop/Redeploy authorization, fixes the fresh root-account registration window and large-image scanner memory behavior.
- 4.7.3 fixes instance/service database backup notification links, restores root-team backup management access, and addresses large scan timeouts with configurable limits. These fixes do not justify auto-enabling the scanner.

## Qualification, production and release boundaries

- **Source V2:** initial candidate `86fe3e7dc6ed939ccd81730d109d2e49f0fe2090` passed hosted [Repository CI / fast-source](https://github.com/paracosm17/solo-vps/actions/runs/42703500766) and [documentation build](https://github.com/paracosm17/solo-vps/actions/runs/42703500772). The fast source job checked the Coolify 4.7.3 manifest, unit tests (including reviewed Sentinel origin/target identities), YAML parsing, Ansible syntax and ansible-lint (`0 failures, 0 warnings` in 183 linted files). The final metadata-only evidence commit must also pass its exact-head CI before production.
- No disposable validation VPS is used under the owner's production-first workflow. **No 4.7.3 runtime, migrations, app API or restore validation has occurred.** 4.6.0 production V5 cannot be relabelled as 4.7.3 evidence.
- On the one maintained production host: verify clean candidate checkout, `coolify_version=4.6.0` and `docker.io/coollabsio/coolify:4.6.0` healthy, Sentinel current/target identity, Traefik 3.7.16 healthy, no transaction marker, admin/provider rescue access and sufficient disk.
- Prepare a **fresh age-encrypted Coolify control-plane backup**, copy outside VPS, match SHA-256 and verify authenticated decryption/reading; separately verify application databases/volumes and preferably a provider snapshot. Existing control-plane backup alone does not cover those data.
- Pause deployments, configuration/ENV changes and enable no unnecessary new scanner features. Check current HTTPS apps, API tokens and Sentinel In Sync. Run `make validate`, `make doctor`, `make updates-plan`, `make verify-firewall`, `make coolify-upgrade-preflight`; preflight must report exactly `observed_version=4.6.0`, `current_supported=4.7.3`, `upgrade_required=true`, `mutation=false`, `failed=0`.
- Upgrade only through the guarded `COOLIFY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN make coolify-upgrade`. Do not use UI Update, floating image pull or manual removal of transaction markers; never revert the image against a migrated database.
- After upgrade: require exact image/marker 4.7.3, Sentinel 1.1.5 healthy/In Sync, all Coolify realtime and health endpoints 200, proxy/loopback boundary, `make verify-coolify`, `make verify`, `make audit`, app HTTPS/CI/API deploy checks and backup/restore evidence. Record honest **bounded V5** in a new dated production report only after observed logs.
- **Publication:** PR #36 for 4.6.0 is unmerged. Keep the stages reviewable in order: preserve/merge the predecessor after approval, then retarget/merge the 4.7.3 PR, run exact-release dry run and public/history/security checks, and publish Solo VPS **v0.2.7 only after explicit owner authorization**. The new version badge is a candidate claim, not a published release.
