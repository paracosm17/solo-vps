# Coolify 4.4.2 / Traefik 3.7.14 production patch — 2026-10-08

Owner-authorized maintained Ubuntu VPS transition, executed at source
`7b56423d12015c25bd30e1a2d016c379e793d06c` after the controlled test qualification.
This records bounded V5 point-in-time use; it is not a reliability guarantee or
a clean-host replay.

## Recovery prerequisites

A fresh root-private backup retained the Coolify database dump, source/environment,
SSH files, proxy configuration/certificates, previous proxy image and old controller
source/configuration. Database dump inspection, archive readability and all three
file hashes passed. The bundle was age-encrypted off-host, decrypted without writing
plaintext to disk, and matched the original SHA256. The age identity remained on
the workstation. Application data was not changed by this patch and is outside
this control/proxy backup; its previous separately verified backup remains distinct.

The two generated Coolify/proxy checkpoints were also hash-verified, encrypted
off-host and decrypted/hash-matched after the transition. These checks are not a
full production restore rehearsal. The disposable checkpoint database restore
exercise is recorded separately in [the V3 runtime record](2026-10-08-coolify-442-runtime.md).

## Execution

No active deployment was present immediately before Coolify mutation. The old
checkout was retained and external controller state reused. An initial read-only
preflight rejected a stale operator input differing from the current Sentinel URL
only by a root trailing slash. Correcting that private input changed no runtime.

- Exact-origin Coolify preflight: `ok=41 changed=0 failed=0`.
- Coolify 4.4.0 → 4.4.2: `ok=137 changed=9 failed=0`; completed transaction removed.
- Proxy preflight: `ok=24 changed=3 failed=0` (private helper installation).
- Explicit Traefik 3.6.25 → immutable 3.7.14: `ok=24 changed=1 failed=0`.
- All 14 business containers retained ID, image, mounts and StartedAt.
- Six origin HTTPS health routes returned 200 with certificate validation.
- Sentinel native status was `in_sync`; analytics returned 282 requests and no 5xx.
- Six control-plane credential fields and two SSH files matched the fresh backup;
  only aggregate comparison results were emitted, never secret values.
- Full verification: `ok=163 changed=0 failed=0`; audit:
  `ok=96 changed=0 failed=0`.
- Coolify upgrade rerun: `ok=87 changed=0 failed=0`; proxy upgrade rerun:
  `ok=24 changed=0 failed=0`.
- Native SSH backend returned its expected marker, Sentinel was `in_sync`, and
  certificate-validated origin Reverb WebSocket handshake returned 101.
- Coolify, proxy and Sentinel were healthy; actual Traefik binary reported 3.7.14.
  Proxy logs had no bind conflicts or error/fatal messages. Sentinel's 20 lines
  containing an `error` field were all WARN `cannot stat mount source` from its
  storage collector; all 20 reported paths existed on the host. No ERROR/FATAL
  severity occurred. Those host-path statistics remain an agent-namespace limitation;
  traffic delivery was measured separately and succeeded.

No OS/Docker package upgrade, production reboot, workload deployment or application
database migration was performed. Coolify migrations are control-plane changes;
source/image reversal alone cannot undo them.

## Evidence limits

The final release metadata is operationally equivalent to the execution source;
the patch changes no host bootstrap/hardening/firewall implementation. Prior
corrected 0.2.0 host-layer controlled evidence remains scoped to those unchanged
operations. A fresh Coolify 4.4.2 installation and uninterrupted new-user V4 replay
remain unproven. Optional integrations retain their own qualification.
