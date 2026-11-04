# Coolify 4.6.0 — production upgrade (bounded V5)

## Environment and source

- Date: 2026-11-04.
- Source revision used on the production controller: `dcd2a365b2e60f4e6502c1932ca15ec11cf49ee5` from PR #36; working tree clean after source validation.
- Maintained Ubuntu 24.04 x86_64 VPS, Docker Engine 29.9.2; deployment was **not** performed on a disposable validation VPS, by owner instruction.
- Supported exact transition: Coolify **4.5.3 → 4.6.0** with upstream pinned artifacts and no floating upgrade.
- Sentinel 1.1.3 and Traefik 3.7.16 were retained, healthy; no separate proxy image mutation was needed.

## Observed live transition

- Pre-upgrade managed version 4.5.3, running official image `docker.io/coollabsio/coolify:4.5.3`, healthy, no pending transaction and sufficient disk space.
- `make validate` on the production controller passed after two source-only test isolation fixes; `make doctor` passed at `ok=9 changed=0 failed=0`; `make updates-plan` identified the exact 4.5.3 → 4.6.0 transition and a clean source revision.
- `make verify-firewall`: PASS, `ok=20 changed=0 failed=0`.
- `make coolify-upgrade-preflight`: PASS, `ok=41 changed=0 failed=0`; observed 4.5.3, reviewed target 4.6.0, supported Docker 29.9.2, auto-updates disabled, Sentinel healthy, management ports loopback-only.
- `make coolify-upgrade`: PASS, `ok=139 changed=10 failed=0`. A root-private control-plane checkpoint was created and retained. Staged pinned artifacts were verified; the old `COOLIFY_VERSION` line was removed while `LATEST_IMAGE=4.6.0` and `AUTOUPDATE=false` were enforced.
- Initial Coolify readiness retries were transient; the playbook completed successfully. Coolify image `docker.io/coollabsio/coolify:4.6.0` healthy, HTTP health/realtime/terminal readiness all **200**.
- Proxy remained healthy, publishing only TCP 80/443; management TCP 8000/6001/6002 were bound exclusively to `127.0.0.1` and independently unreachable from the controller's external network path.
- After full verification, the upgrade staging directory and pending transaction marker were removed. Managed marker reported `coolify_version=4.6.0`.

## Post-upgrade read-only production verification

| Check | Observed result |
| --- | --- |
| `make verify-coolify` | PASS, `ok=56 changed=0 failed=0` |
| `make verify` | PASS, `ok=163 changed=0 failed=0` |
| `make audit` | PASS, `ok=96 changed=0 failed=0` |
| Docker runtime inventory | 23 of 23 containers running |
| systemd failed units | 0 |
| Security audit warnings | `[]`; no unexpected public PostgreSQL/Redis publications |
| Sentinel | 1.1.3, healthy; push endpoint configured, no public API listener |
| Traefik | 3.7.16, healthy; no image upgrade |
| Coolify control plane | 4.6.0, healthy, health/realtime/terminal endpoints HTTP 200 |
| Pending upgrade marker | Absent |

## Backup and evidence boundaries

- Before the live change, `make coolify-backup-local` created a fresh **age-encrypted control-plane** archive; internal content was validated before encryption.
- The ciphertext was copied from the VPS to a separate WSL workstation. Its SHA-256 matched the source; `age --decrypt` successfully streamed into `tar -tzf` without leaving plaintext on disk.
- The archive excludes application databases and volumes. Their separate backup status was **not independently demonstrated** in the supplied logs; neither was a provider snapshot, an isolated database restore or complete disaster-recovery rehearsal.
- Optional off-site restic repository remained **NOT_CONFIGURED** in the controller's doctor report. The control-plane age archive is not proof of app data backup freshness.
- The supplied checks prove the managed control plane, host baseline, audit and container-level health. They do **not** prove individual application HTTPS/business transactions, application data consistency, a new GitHub Actions deployment, the UI's Sentinel “In Sync” indicator, or Coolify API/MCP token deletion scopes.
- No disposable-VPS V3, interrupted-upgrade resume or forced rollback evaluation was performed for 4.6.0. The observed V5 result is expressly **bounded to this production upgrade and these checks**; a new-install and complete restore claim would be unsupported.
- Private raw logs, configuration values, server-specific URLs/addresses, checkpoint identifiers and credentials stay outside the public repository.

## Release gate

The production-first exception was requested by the owner for this upgrade. It does not automatically approve publication, replace application/restore evidence, waive future safety review or authorize a release. Review v0.2.7 prerequisites and obtain explicit publication approval before merging, tagging or publishing.
