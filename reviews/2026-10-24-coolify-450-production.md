# Coolify 4.5.0 bounded production upgrade — V5

On 2026-10-24 the owner-authorized maintained Ubuntu 24.04 VPS completed Coolify 4.4.6 to 4.5.0 using source `f81f54e`. Read-only follow-up on 2026-10-25 confirmed continued platform health. This followed [controlled V3 upgrade/restore qualification](2026-10-24-coolify-450-runtime.md). Traefik remained 3.7.14; the already-running Sentinel 1.1.2 was retained.

## Recovery and safeguards

A fresh encrypted off-host export passed authenticated decryption and manifest checks before mutation. The normal upgrade created a validated private local checkpoint. Previous source and original credentials were retained. Control-plane backups exclude application data; no application database/volume upgrade or restoration was performed.

Before transition, no active deployments or pending lifecycle markers were present. On-server comparisons confirmed an unchanged baseline immediately before mutation. Secret hashes and plaintext values never left the VPS; only results/counts were returned. The six groups of newly encrypted columns had no nonblank values here; a synthetic isolated fixture exercised conversion separately.

An optional production fixture restore was rejected by automatic approval review and not executed. It is not part of this evidence. Test-VPS isolated restore and production encrypted-export verification remain separate proofs.

## Observed results

- Preflight: ok=41 changed=0 failed=0. Normal upgrade: ok=138 changed=9 failed=0. No deliberate production interruption.
- Full verify: ok=163 changed=0 failed=0. Audit: ok=96 changed=0 failed=0. Normal upgrade rerun: ok=87 changed=0 failed=0.
- Exactly 31 new migrations. Original APP_KEY and checked platform credentials matched their server-side baseline; all 120 stored ENV plaintext values matched and retained legacy escaping. This does not prove byte parity after future app redeployment.
- All 18 application/proxy/logrotate containers retained IDs, images, mounts and start times. Coolify application/database/Redis control-plane containers were recreated by the normal lifecycle; this is not a zero-interruption claim.
- All eight origin HTTPS codes matched baseline: six 200, one pre-existing development-route 404 and one pre-existing development-route 503. Those exceptions were not introduced or repaired by this update.
- Sentinel reported in_sync; Coolify host patching stayed disabled. Correct HTTP/1.1 TLS WebSocket Upgrade returned 101 using the native key internally. An initial HTTP/2 probe was corrected without runtime configuration changes.
- Recent platform logs had no SQL, secret-conversion, fatal or port-bind error patterns. Follow-up after approximately 16 hours found healthy platform containers, identical HTTPS responses and successful Sentinel/WebSocket checks.

This is bounded existing-production V5 evidence, not fresh installation/V4, full disaster recovery, arbitrary mid-migration recovery or a new live S3 replay. Source/image downgrade cannot undo database migrations. Preserve database and APP_KEY together.
