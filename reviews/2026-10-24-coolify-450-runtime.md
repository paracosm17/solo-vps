# Coolify 4.5.0 integration qualification

Reviewed direct transition 4.4.6 to 4.5.0, including security release 4.4.7. Controlled V3 existing-host qualification passed on the disposable Ubuntu 24.04 VPS. Operational upgrade source was `8c270b2`; full host verification used the read-only timezone-alias correction `ab06395`.

Exact upstream tag: `5ca69705d681da46028ea15a8a39d90a4ebcce89`. All three platform installation artifacts are byte-identical to the reviewed origin. Sentinel target is 1.1.2; Traefik stays at 3.7.14 pending a separate proxy qualification.

## Upstream and source review

Reviewed both official release notes, exact tag trees, 31 new migrations and relevant secret/ENV/API changes. 4.4.7 patches upstream dependencies and Sentinel. 4.5.0 adds four explicit breaking changes: deploy permission on side-effect API routes; backup execution message redaction; removal of POST /api/v1/enable; rejection of Compose scale/replicas above one. Solo VPS already uses read/write/deploy and does not call the removed endpoint. Its S3 verification now requires the structured boolean s3_uploaded=true, including when message is null; missing/null/false/nonboolean upload results fail closed.

Migrations preserve legacy ENV escaping and encrypt additional secrets using APP_KEY. The encryption migration catches per-table exceptions: migration completion alone cannot prove success. Both inspected hosts had no nonblank values in the affected columns; a synthetic fixture separately exercises encryption/decryption. Database and APP_KEY must remain paired for recovery. Host patching defaults false and was not enabled; Solo VPS retains host update ownership. Native UI pre-update backup is supplemental and does not replace the reviewed checkpoint/export path.

## Controlled checks

- Fresh encrypted off-host control-plane export passed authenticated decryption and all manifest checks. Application data is excluded.
- Restored a fresh dump into a newly created isolated database. Before running target migrations, verified the actual database with both images and cleared DATABASE_URL. Seeded synthetic legacy ENV and plaintext log-drain values only in that database. All exact upstream migrations passed; legacy ENV/value and encrypted-secret decryption matched; host patching remained disabled. Dropped only the owned fixture database.
- Read-only upgrade preflight: ok=41 changed=0 failed=0. Controlled evaluation stopped after checkpoint/transaction marker, before artifact promotion: ok=57 changed=3 failed=1 (expected). Same-source forward resume: ok=112 changed=5 failed=0. This tests interruption before migration, not arbitrary mid-migration crash recovery.
- Full verify: ok=163 changed=0 failed=0; audit: ok=96 changed=0 failed=0. Normal upgrade rerun: ok=87 changed=0 failed=0.
- Baseline comparisons stayed entirely on the VPS. Original credential hashes and stored logical ENV values matched; proxy/logrotate IDs, images, mounts and start times were unchanged. Exactly 31 migrations were added. Sentinel 1.1.2 was already running and passed the reviewed content identity/HTTPS/no-public-port boundary.
- Origin HTTPS health returned 200. Checked recent platform logs for SQL/migration encryption failures and bind/fatal errors: none. Full verify initially rejected /etc/timezone=Etc/UTC against configured UTC; the read-only correction compares canonical paths for localtime, configured zone and timezone file. Positive full verify passed; a deliberate Europe/Moscow override failed read-only.

This is controlled V3 existing-host evidence, not a fresh 4.5.0 installation/V4, full disaster recovery or a new native S3 integration replay. Production results are recorded separately. App data and post-redeployment rendered ENV semantics require their own qualification; current running workloads were not redeployed.
