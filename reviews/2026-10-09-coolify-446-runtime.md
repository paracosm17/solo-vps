# Coolify 4.4.6 controlled patch qualification

Candidate: Coolify 4.4.3 → 4.4.6, embedded Reverb, Sentinel 1.0.2 and unchanged reviewed Traefik 3.7.14. Official 4.4.4/4.4.5/4.4.6 release notes, complete tag comparison and all three new migration classes were reviewed. Exact-tag installation artifact hashes match the manifest; no Sentinel or proxy update is required.

## Existing-host evidence — V3

The disposable Ubuntu 24.04 host started from published v0.2.2. Operational source `ef4139b` passed the direct transition. Before mutation, a fresh checksummed control-plane checkpoint was validated; no active deployments, duplicate variable groups or affected IPv6 records were present.

- Preflight: `ok=48 changed=0 failed=0`.
- Deliberate post-marker interruption: `ok=57 changed=3 failed=1`; explicit forward resume: `ok=112 changed=5 failed=0`.
- Candidate verifier: `ok=62 changed=0 failed=0`; full verification: `ok=163 changed=0 failed=0`; audit: `ok=96 changed=0 failed=0`.
- Normal upgrade rerun: `ok=87 changed=0 failed=0`.
- Fresh checkpoint restored into a separately owned PostgreSQL database. The exact three target migration classes ran there against raw synthetic fixtures: IPv6 normalization and Sentinel URL bracketing, Redis preview-independent grouping, Node-version preview separation, newest timestamp and ID tie-breaking, and preservation of unrelated values all passed. The fixture changes rolled back; only the temporary database was dropped.
- All live environment-variable rows matched baseline hashes; built-in server, native proxy and destinations retained their identities/configuration. Six credential fields and two actual SSH key files stayed unchanged.
- Application/proxy containers retained IDs, image IDs, mounts and start times. Origin HTTPS health returned 200, Reverb TLS WebSocket returned 101, native SSH succeeded, Sentinel reported `in_sync`, and traffic analytics recorded the generated successful request with no 5xx.
- Normalized recent Coolify/proxy/Sentinel logs had zero ERROR/FATAL/CRITICAL and zero bind conflicts.

Focused lifecycle/update checks and the full `ci-fast-source` gate passed. Later qualification/release documentation does not change the tested operational implementation or manifest fingerprint.

## Limits

The three upstream data migrations are forward-only. Reverting source/image cannot undo deleted duplicate records. A checkpoint restore exercise and isolated migration fixtures are not complete application-data disaster recovery. This is an existing-host V3 qualification, not a fresh V4 installation. Production evidence is recorded separately after execution.
