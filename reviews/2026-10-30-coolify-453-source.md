# Coolify 4.5.3 — bounded source review (2026-10-30)

## Scope and disposition

- **Target:** Coolify `4.5.3`, upgrading from the previously qualified `4.5.0` source.
- **Level:** V1 (source review / syntax / manifest fingerprint), **NOT V3**. No controlled VPS upgrade, interrupted resume, isolated restore, production migration or end-to-end backup recovery was executed for this target.
- **Release disposition:** **BLOCKED** until upstream artifact SHA-256 checks, V3 lifecycle, GitHub CI, clean release validation and independent secret scanning pass. No new V5 claim.
- **Existing evidence:** `reviews/2026-10-24-coolify-450-runtime.md` and the related production evidence apply to the prior `4.4.6 → 4.5.0` release, not to this target.

## Upstream release-note review

- [4.5.1](https://github.com/coollabsio/coolify/releases/tag/v4.5.1): **breaking API change** removes `delete_from_coolify_only` from service deletion; Highlight log drain removed; initial root-account registration limited to ten minutes. Review any scripts that use these surfaces. These do not directly describe an Ansible host-configuration contract change.
- [4.5.2](https://github.com/coollabsio/coolify/releases/tag/v4.5.2): bug and security fixes, including proxy, SSH, S3 backup and API permissions. Verify API-token permission flows and backup behavior.
- [4.5.3](https://github.com/coollabsio/coolify/releases/tag/v4.5.3): fixes to Compose builds, preserving Dockerfile HEALTHCHECK, SSH processes and HTTP retry behavior; helper image updated to `1.0.19`.
- [v4.5.3 versions.json](https://raw.githubusercontent.com/coollabsio/coolify/v4.5.3/versions.json): Sentinel `1.1.3`, which is separately pinned in the manifest. Traefik remains deliberately pinned at the previously qualified `3.7.14` until separately tested; upstream versions.json lists `3.7.16`.

## Manifest and artifact review

- The original pinned `docker-compose.yml` and `.env.production` have no visible changes between upstream tags `v4.5.0` and `v4.5.3`.
- `docker-compose.prod.yml` **does change**: the `soketi` legacy service switches from an inactive `busybox` profile to the Coolify image with `deploy.replicas: 0`, enabling cleanup of older realtime containers. This requires lifecycle validation, not just version replacement.
- `upgrade_from` moves from `4.4.6` to `4.5.0`; its Sentinel identity is the former `1.1.2` target. The new Sentinel `1.1.3` digest is identified from the official GitHub package version page; actual Docker daemon identity must be confirmed on the disposable VPS.
- **Checksum limitation:** the initial 4.5.3 Compose SHA-256 in this patch was reconstructed from displayed upstream lines; it is **not verified against downloaded raw bytes**. Run `python3 scripts/check-coolify-453-artifacts.py --sync` on a machine with Internet access to calculate checksums directly from the exact upstream Git tag, then inspect and commit any corrected manifest. The script checks all three artifacts and recomputes the evidence fingerprint. A passing local manifest validator alone does not establish downloaded-byte integrity.

## Required controlled validation before release

1. Confirm the three upstream artifact SHA-256 digests with the included source-fetch checker and review any difference.
2. Use disposable Ubuntu 24.04 with tested prerequisites and fresh verified off-host backup/recovery inputs. Exercise existing `4.5.0 → 4.5.3` preflight, Sentinel HTTPS readiness, exact release downloads and rollback/forward-resume or M16 recovery.
3. Record actual outputs of `verify-coolify`, `verify`, `audit`, health checks and idempotency; test changed realtime/proxy behavior, S3 backup and relevant API paths as applicable.
4. Add fresh, bounded **V3** evidence and update `qualification` with its exact integration fingerprint. Run repo validation and required hosted `fast-source` check.
5. Complete `docs/release-process.md` gates, including explicit owner approval and independent secret scanning. Only then prepare dated changelog, release notes, annotated tag and GitHub Release.
