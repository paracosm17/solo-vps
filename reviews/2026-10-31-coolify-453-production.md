# Coolify 4.5.3 — production upgrade (bounded V5)

## Environment and result

- Date: 2026-10-31.
- Reviewed Solo VPS source: 55e4882.
- Transition: Coolify 4.5.0 to 4.5.3.
- Sentinel: 1.1.3 (already installed).
- Traefik: 3.7.16 (retained).
- Preflight: PASS, ok=41, changed=0, failed=0.
- Upgrade: PASS, ok=138, changed=10, failed=0.
- Upgrade checkpoint created and retained.
- Upgrade transaction marker removed after verification.
- Coolify image: docker.io/coollabsio/coolify:4.5.3.
- HTTP health, realtime and terminal readiness: HTTP 200.
- Management ports 8000/6001/6002: loopback-only.
- verify-coolify: PASS, ok=56, changed=0, failed=0.
- verify: PASS, ok=163, changed=0, failed=0.
- audit: PASS, ok=96, changed=0, failed=0.
- Platform inventory: 23 of 23 containers running.
- Audit warnings: none.

## Backup and limitations

- Encrypted Coolify control-plane export was copied off-host.
- Encrypted SHA-256 matched the original.
- Off-host age decryption and tar archive read passed.
- No isolated restore of this new backup was performed.
- Off-site restic repository remains unconfigured.
- Application databases and volumes are excluded from the export.
- No application database restore was verified.
- No claim is made about an unverified provider snapshot.
- Disposable-VPS V3, deliberate interruption, forward-resume
  and controlled recovery were NOT performed.
- No V3 qualification is claimed for Coolify 4.5.3.
- Production V5 is limited to the observed upgrade and checks.
- Private logs and credentials remain outside the repository.

## Release exception

The owner authorized a production-first upgrade and release
without disposable-VPS V3 qualification. This exception applies
only to the v0.2.6 candidate; it does not establish recovery
qualification or change future default release requirements.
