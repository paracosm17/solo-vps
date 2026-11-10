# Coolify 4.7.3 — bounded production V5 (2026-11-10)

## Source and environment

- Exact Solo VPS candidate run on the existing production VPS: `5e39867f0abe0ca6ed75cd033379687add22d849`; Git worktree verified clean.
- Supported transition: **Coolify 4.6.0 → 4.7.3**, Docker Engine **29.9.3**, Ubuntu 24.04 x86_64. No second validation VPS, by owner preference.
- Upstream Sentinel **1.1.5** had automatically advanced before the Coolify upgrade. Its official Docker multi-platform index digest and API version were independently reconciled in the candidate source, not waived.
- Unchanged Traefik **3.7.16**, local embedded Reverb, 127.0.0.1-only Coolify management ports and protected host firewall.

## Before mutation

- Fresh age-encrypted control-plane backup created on the VPS; an off-VPS WSL copy matched the expected SHA-256. Authenticated `age --decrypt` streamed through `tar -tzf` successfully, with no plaintext archive stored in the published evidence. This archive excludes application databases and volumes.
- The operator explicitly **affirmed that application backups were in place**, without independently supplied app-backup manifests or restore proof.
- Source `make validate` and `make doctor` passed on the corrected commit. `make verify-firewall` passed `ok=20 changed=0 failed=0`; read-only `make coolify-upgrade-preflight` passed `ok=41 changed=0 failed=0`, observing exactly installed 4.6.0 and planned 4.7.3.
- An earlier V1 candidate failed closed on a mismatched Sentinel image config/index identity (`changed=0`). Corrected source and exact-head CI passed, and the same preflight then succeeded before upgrade.

## Production upgrade

- The operator executed the explicit-confirmation `make coolify-upgrade` on the production VPS.
- Result **PASS**: `ok=139 changed=9 unreachable=0 failed=0 skipped=5`.
- Root-private Coolify control-plane checkpoint created before mutation. Exact upstream artifacts staged and validated, with `LATEST_IMAGE=4.7.3` and `AUTOUPDATE=false`; existing identities retained.
- Coolify started with the exact official image and became **healthy**. Two initial readiness retries were transient; the task subsequently passed. HTTP health, embedded realtime and terminal readiness all returned **200**.
- Proxy remained healthy on TCP **80/443**; Coolify TCP **8000/6001/6002** remained bound to **127.0.0.1**, not reachable via external controller probes.
- The managed version marker was updated to `coolify_version=4.7.3`, and the staging directory and pending upgrade transaction marker were removed only after successful verification.

## Post-upgrade results

| Check | Observed result |
| --- | --- |
| `make verify-coolify` | **PASS**, `ok=56 changed=0 failed=0` |
| `make verify` | **PASS**, `ok=163 changed=0 failed=0` |
| `make audit` | **PASS**, `ok=96 changed=0 failed=0` |
| Docker containers | **17/17** running |
| Coolify | Official **4.7.3**, **healthy** |
| PostgreSQL and Redis control-plane containers | **healthy** |
| Sentinel | Official **1.1.5**, healthy; required API/trust checks passed |
| Traefik proxy | **3.7.16**, healthy |
| Failed systemd units | **0** |
| Security audit | No clear violations, `warnings=[]` |
| Upgrade transaction marker | Absent |

## Bounded evidence and release limitations

- This is **V5 for the observed managed Coolify production transition and host/control-plane checks only**. It is not a blanket V5 claim for every application, remote API integration or end-to-end disaster recovery.
- `make verify` explicitly did not contact an off-site restic repository; configured backup repository remains **NOT_CONFIGURED**. The operator's app-backup affirmation is not an independently validated restore.
- No application-specific HTTPS/business transaction, GitHub Actions API deployment, forced interruption/forward resume, UI Sentinel **In Sync** indicator, provider rescue console, full database restore, or externally monitored outage probe was demonstrated by these logs.
- No new disposable V3; no upgrade attempt to be repeated on this host. Preserve prior off-host backup and private checkpoint.
- Raw logs, host-specific URLs/IPs, original checkpoint paths, tokens and credentials are not stored in this public record.

## Publication gate

The production Coolify upgrade is complete. PR #36 (4.6.0) and this stacked PR #38 (4.7.3) remain unmerged. Run exact-head CI and the documented v0.2.7 dry run, review omitted application/recovery checks and receive explicit publication approval before merging and publishing.
