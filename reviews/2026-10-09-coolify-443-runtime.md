# Coolify 4.4.3 controlled patch qualification

Candidate transition: Coolify 4.4.2 → 4.4.3, embedded Reverb and Sentinel 1.0.2. Traefik remains on the reviewed 3.7.14 identity.

All official release notes and the tagged compare were inspected. No database migration, installation artifact or Sentinel version changed in the tag comparison. All three release artifacts have the same independently fetched SHA256 values as the preceding patch. New integration qualification does not inherit previous runtime evidence.

## Controlled existing-host evidence — V3

The disposable Ubuntu 24.04 host started from the published 0.2.1 integration. Operational source `f5fe9cb` passed the exact 4.4.2 → 4.4.3 transition; later source `49da9b3` changes only an architecture test fixture. No application or proxy upgrade was requested.

- Preflight: `ok=48 changed=0 failed=0`.
- Deliberate post-marker interruption: `ok=57 changed=3 failed=1`, retained transaction and checkpoint; explicit forward resume: `ok=112 changed=6 failed=0`.
- Candidate verification: `ok=62 changed=0 failed=0`; full verification: `ok=163 changed=0 failed=0`; audit: `ok=96 changed=0 failed=0`.
- Normal upgrade rerun: `ok=87 changed=0 failed=0`.
- Fresh checkpoint dump restored successfully into a separately created PostgreSQL database; built-in server restored. Only that temporary database was removed.
- Application origin HTTPS `/healthz` returned 200; embedded Reverb TLS WebSocket handshake returned 101; native SSH backend succeeded; Sentinel reported `in_sync`; generated request appeared in native traffic analytics with no 5xx.
- Business application and proxy containers retained IDs, image IDs, mounts and start times; proxy native configuration, built-in server UUID/address/user/key relation and destinations stayed unchanged.
- Actual native initializer changed the default `localhost` display name to configured hostname; rerun was unchanged; a temporary custom UI name was preserved and subsequently restored by the test operator.

Source checks include the full `ci-fast-source` gate and strict EN/RU documentation build. The three artifact checksums were fetched from the exact upstream tag. The source startup chain runs ProductionSeeder before healthy Reverb and first-account onboarding; this was inspected, not independently replayed on a fresh host.

## Limits

This is an existing-host patch qualification, not V4 fresh-user installation or a full application-data restore. The control-plane checkpoint excludes business application data. No prod reboot, host package change, Traefik upgrade or live application deployment is required. Production evidence is recorded separately after execution.
