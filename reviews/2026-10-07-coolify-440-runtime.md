# Coolify 4.4.0 controlled upgrade evidence — 2026-10-07

## Scope

Owner-authorized disposable Ubuntu 24.04 x86_64 VPS with no important data. Production was excluded. Full operator logs, credentials, checkpoint archives and failed-state databases remain private; this record contains sanitized results only. No release or tag was created.

Final runtime replay used source `3800d76a3de8b7a3194b190d35f838a55c9f9007`. Coolify changed from `4.3.21` to `4.4.0`; Docker stayed `29.8.1`. The target Sentinel is `1.0.2`, with content identity recorded in `config/coolify-release.yml`.

Evidence level: **V3 — controlled real-environment integration**. This is not a fresh-install V4 replay or production V5 evidence.

## Results

| Check | Result |
| --- | --- |
| Separate candidate checkout and isolated evaluation state | Passed; published checkout and normal controller state retained |
| Doctor and exact origin preflight | Passed, no changes |
| Private local checkpoint | Custom PostgreSQL dump and source/SSH archive created; hashes and readability checked |
| Intentional interruption after checkpoint/marker | Expected failure before target promotion |
| Ordinary upgrade with pending marker | Refused without changes; marker retained |
| Fresh forward resume using corrected manifest | Passed: `ok=110 changed=9 failed=0` |
| Upgrade rerun at target | Passed: `ok=93 changed=0 failed=0` |
| Full managed-host verification | Passed before and after reboot: `ok=154 changed=0 failed=0` |
| Security audit | Passed before and after reboot: `ok=87 changed=0 failed=0`; no warnings or clear violations |
| Management exposure | 8000/6001/6002 on IPv4 loopback; Sentinel has no published host port; controller probes reject public management access |
| Reverb and terminal readiness | `/up` and `/ready` return 200 |
| Reverb websocket | Actual local and public HTTPS websocket handshakes return 101, including after reboot |
| Terminal | Native authenticated HTTPS websocket and single-use token execute a bounded read-only command through SSH PTY, including after reboot |
| Sentinel delivery | Healthy exact target image, recent database push timestamps and reviewed private-API/HTTPS boundary |
| Credentials and platform SSH identity | Compared privately against original checkpoint; unchanged |
| Old standalone realtime | Removed through ownership-checked helper; no volumes removed |
| One scoped API token | Read, write and deploy succeed with `read`, `write`, `deploy`, without root ability |
| Immutable app deployment | Public CI-built GHCR digest deploys and application stays healthy |
| Failed-image rollback | Nonexistent digest produces expected `DEPLOY_FAILED_ROLLBACK_OK`; known-good image/public health restored |
| Update discovery | Reports newer upstream separately from reviewed target and does not install it |
| Standard workspace | Tested source activated in normal workspace; old checkout saved separately, original config/inventory retained |
| Reboot | Administrator SSH, platform, app, websocket and terminal recover; existing pending OS kernel update activates, Docker unchanged |
| Cleanup | Task-created API token revoked; private credential files removed and original terminal-access setting restored |

## Failures found and corrected

The first resume exposed two integration issues. The legacy standalone realtime container retained port 6001 despite Compose `--remove-orphans`; it was not a removable orphan of the new Compose model. Upgrade and resume now retire only the inspected, Coolify-owned, official versioned realtime container after target Compose validation. Unknown ownership fails closed.

Coolify's native scheduler independently upgraded Sentinel to 1.0.2. The old candidate expected 1.0.1 and correctly retained the transaction marker. Official Sentinel release/component metadata and the installed Coolify scheduler/start action were reviewed. The manifest now records origin and target identities. Origin preflight explicitly permits the reviewed newer agent because it can update before Coolify; target verification requires the exact new tuple. Unknown content or versions fail. A bounded wait accommodates native reconciliation.

The changed Sentinel contract invalidated the first transaction identity. It was not bypassed or rebound. The failed marker, current database, source and Redis snapshot were retained privately. The original checkpoint database was restored into a separate PostgreSQL database, then activated with its matching original source and marker after stopping control-plane writers. Only dedicated Coolify queues/cache were reset; application data was untouched. The migrated database was preserved separately. Secrets and SSH identities matched. The failed marker was archived unchanged and retired only after coherent original runtime restoration. A fresh complete interruption/resume replay then passed with corrected source.

The pre-existing demo desired image named an unavailable repository and used a local image SHA instead of the current public registry artifact. Its running container stayed healthy while registry pulls failed. Only the disposable app was corrected to an already-published public CI digest; known-good recovery, ordinary deployment and negative rollback then passed with the combined token. This was fixture repair, not a production app change.

## Limits

The checkpoint restore proves same-host control-plane recovery on a disposable target. It excludes application data and is not offsite recovery or a generally supported automated downgrade. Audit does not contact offsite storage or replace an external monitor. Optional B2/restic, database-backup API adoption and backup UI workflows need separate target-version checks. An uninterrupted exact-revision new-user browser walkthrough remains a separate gate; subsequent controlled fresh-host results are recorded below. Production needs its own owner-authorized operation and recovery prerequisites.

## Subsequent fresh-host replay

The owner later reset the disposable VPS. Fresh bootstrap exposed additional first-start proxy/firewall behavior; see [the bounded clean-host replay](2026-10-07-coolify-440-clean-runtime.md) for exact revisions, corrected-source resume and post-reboot verification. The earlier upgrade/reboot results above do not substitute for that new check.
