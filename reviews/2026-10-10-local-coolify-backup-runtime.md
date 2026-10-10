# Local encrypted Coolify backup — controlled V3 evidence

Date: 2026-10-10. Target: disposable Ubuntu 24.04 evaluation VPS. Feature revision: `bb4eb09`, based on published v0.2.3 and the separately reviewed workstation export. Production was not used for this feature qualification.

## Operations and results

- Preserved the previous v0.2.3 source checkout and existing external operator configuration. Installed the candidate in a separate checkout. Read-only preflight confirmed seven healthy containers, no active deployments or incomplete lifecycle markers, and sufficient disk space.
- Derived the existing workstation identity's public recipient locally. One-time `coolify-backup-local-prepare` created public SOPS metadata and checked the pinned age toolchain. No private identity was copied to the VPS; default administrator/root identity paths remained absent.
- Two parameterless `make coolify-backup-local` invocations produced distinct encrypted files. A third invocation under `env -i` with HOME/USER/LOGNAME and PATH=/usr/bin:/bin passed, proving minimal cron-like execution without installing a schedule.
- All three files were owned by the administrator with mode 0600. Collector staging cleaned up after successful collection; only the intentional capture lock remained in its namespace.
- Holding the shared root capture lock rejected both a local invocation and workstation export, without publishing a final backup. A subsequent unlocked workstation export passed authenticated decryption and manifest validation.
- PowerShell invoking WSL SSH/SCP successfully created and transferred encrypted local backups. Both transferred copies matched their server ciphertext SHA256, passed age authenticated decryption and all manifest member checks. No plaintext archive/dump was written on the workstation.
- Streamed one authenticated archive's dump into a newly created, separately owned test database with `pg_restore --exit-on-error --no-owner --no-acl`. The built-in server row was restored. Dropped only that created database in cleanup; the running Coolify database was not restored or modified.
- Compared sanitized container metadata before/after: all seven container IDs, images, start times and health were identical. No restart or platform upgrade occurred.

## Scope and limitations

The local command and remote export are explicit separate operations; no environment autodetection or private-key fallback exists. Native Windows Make is unsupported. Native Windows OpenSSH host verification succeeded with the trusted test host key, but authentication failed with the available Windows identity; the WSL key exposed through UNC was rejected by native SSH permissions checks. No access configuration was changed to make that path pass. Only PowerShell through WSL was exercised successfully.

This is V3 existing-host feature evidence, not clean-user V4, optional production V5, full disaster recovery or proof of an installed cron schedule. Backups exclude application data. The capture lock serializes backup collectors but does not pause unrelated Coolify actions; database and files are not an atomic snapshot. Plaintext staging is private root-owned data during capture; abrupt termination can leave staging/partial files requiring controlled cleanup. Local backups require separate off-host authenticated decryption verification, and local disk copies do not survive loss of the VPS.
