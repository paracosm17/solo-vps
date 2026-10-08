# Coolify 4.4.2 / Traefik 3.7.14 controlled runtime — 2026-10-08

V3 controlled integration on the owner-authorized disposable Ubuntu VPS. This is
an existing-host patch transition, not a fresh installation or V4 user replay.
Execution source: `9b95f1e6853f9424e93fd4ef7d0c60b3b62c2459`; no-op correction
verified at `c5c7fd3`. Integration fingerprint:
`sha256:5e6ff2b2460369e1e35eb62f47f6195a586097f9735dc657e63de6501c248e76`.

The reviewed Coolify 4.4.0 → 4.4.2 pair keeps embedded Reverb. The three
checksummed upstream installation artifacts are unchanged. Source review includes
the new backup-notification and traffic-IP-mode database migrations.

Traefik is a separate explicit native lifecycle. The shared manifest pins its exact
target digest and reviewed x86_64 source identities; host port reconciliation still
does not upgrade the proxy.

## Coolify transition

- Exact 4.4.0 → 4.4.2 preflight: `ok=48 changed=0 failed=0`.
- Intentional interruption after checkpoint and transaction marker:
  `ok=57 changed=3 failed=1`, expected evaluation stop.
- Explicit forward resume: `ok=111 changed=5 failed=0`.
- Full verification: `ok=163 changed=0 failed=0`; audit:
  `ok=96 changed=0 failed=0`.
- Checkpoint checksums passed; actual pg_restore into a separately created test
  database passed and its server rows were read. Only that owned test DB was removed.
- Native Coolify SSH backend returned the expected marker; the public dashboard
  origin accepted a certificate-validated Reverb TLS WebSocket handshake (101).
  This is backend/transport evidence, not a new interactive browser-terminal replay.

## Explicit proxy lifecycle

The test initially had a floating 3.7 image containing binary 3.7.14. A private
checkpoint was retained and the exact production-origin 3.6.25 content identity
was installed through native Save/Start before testing the transition.

- 3.6.25 → immutable 3.7.14: intentional interruption after native Save, retained
  transaction, explicit resume and exact image/binary/health/ports/network checks passed.
- Checkpoint rollback restored 3.6.25 through its immutable recorded digest;
  subsequent upgrade passed. Native StartProxy pulls images, so automated rollback
  requires registry access and does not promise offline recovery.
- Native analytics disable/enable and another native proxy restart passed. Sentinel
  reported `in_sync`; its native traffic API returned 19 requests and zero 5xx.
- Origin HTTPS application health returned 200 with certificate validation. The
  application retained container ID, image, mounts and start time through upgrades.
- Following analytics configuration, a native YAML quoting change initially caused
  a redundant image-only restart. The correction preserves identical image scalar
  spelling; ordinary `make proxy-upgrade` rerun passed `ok=24 changed=0 failed=0`.
- Recent proxy/Sentinel logs contained no error/fatal lines or bind-conflict markers.
- A controlled reboot retained the proxy and application image/container/mounts;
  application health returned 200, analytics remained enabled with Sentinel in sync,
  and full post-reboot verification passed `ok=163 changed=0 failed=0`.

Full proxy files (including certificates), original Compose and old image archives
remain root-private on the target. Automatic rollback restores configuration/image;
it does not extract the proxy-files archive or overwrite current certificates.

## Limits

Production and release-publication evidence are separate. Optional integrations,
full application-data restore, exact-revision fresh installation, external IPv6
packet checks and reliability guarantees are not established by this patch replay.
