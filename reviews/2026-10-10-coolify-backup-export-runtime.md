# Workstation encrypted Coolify export — V3

The new `make coolify-backup-export` command ran from a Linux/WSL workstation against the owner-authorized disposable Ubuntu 24.04 host using published v0.2.3 / Coolify 4.4.6 / Traefik 3.7.14 / Sentinel 1.0.2. The collector code travelled as a standard-library ZIP application; no server source update, install or container restart was required.

- Existing administrator SSH and noninteractive sudo were used. The age identity stayed on the workstation; the existing pinned age toolchain was checksum-verified before collection.
- Fresh PostgreSQL custom-format dump passed matching-container `pg_restore --list`. Private temporary staging bundled current control-plane configuration/keys, proxy certificates/configuration, operator config/inventory and platform metadata.
- The resulting encrypted archive was written directly to a new Windows path through WSL. Both SSH and age exited successfully; streamed local decryption matched the collector's full SHA256, then a second pass verified every member against the inner manifest. Encrypted SHA256: `6efbf0a82ee14ef5f0057b95a8173706c18205e00fc2a529b62437bae4e16a85`.
- The included dump was decrypted/extracted as a stream directly into a separately created PostgreSQL database. Restore with `--exit-on-error` succeeded and the built-in server row was present. Only that owned temporary database was dropped. No plaintext database dump was written to workstation disk.
- All active container IDs, image IDs, start times and healthy states matched the pre-export snapshot. Temporary remote export staging was empty afterward; prior upgrade checkpoints were retained.

Independent architecture, implementation and runtime-plan reviews found no material blocker. Focused tests cover failed SSH/age/decrypt verification, checksum corruption, unsafe member paths/symlinks, source-tree output, destination collision and final-file publication ordering. Cryptographic correctness is provided by pinned age; pipe unit fixtures do not claim cryptographic proof.

This is a control-plane export and isolated database restore exercise, not application-data backup or full VPS disaster recovery. Database/files are captured separately; pause deployments/settings changes. Historical checkpoints are not bundled. Abrupt process termination may leave private staging or a `.partial` and has no stream-resume guarantee. Production was not used for this feature test.
