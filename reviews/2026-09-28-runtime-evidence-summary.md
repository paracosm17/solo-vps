# Runtime evidence carried into the first release candidate

This record preserves the completed integration results from the retired release-readiness plan. It is a summary of the existing operator exercises, not a new execution report. Current gates and supported scope belong in `ROADMAP.md`; publication steps belong in `docs/release-process.md`.

| Exercise | Observed result | Evidence level |
| --- | --- | --- |
| Basic installation and application delivery | The owner followed the two public chapters on a separate clean Ubuntu 24.04 VPS at `0fdba7f`; verification, audit and a repeated platform run passed. The application and automatic deployment worked. | Core V4; [separate record](2026-09-28-clean-user-replay.md) |
| Retained application logs | Entries remained searchable after application redeploy and Alloy restart. The owner subsequently confirmed older entries after several days. | V3; no fixed retention SLA |
| PostgreSQL local backup and restore | A backup restored into a separate database matched the backup point while later changes remained only in the source database. | V3 |
| PostgreSQL off-site restore | Coolify uploaded a logical backup to Backblaze B2 and restored it into a separate database; restored contents matched the saved state. | V3 |
| Restic off-site recovery inputs | Repository initialization, snapshot creation, freshness checks, temporary restore-test and daily backup timer passed. The restore-test did not modify production paths. | V3 |
| External outage alerts | Test, DOWN and UP emails arrived for the application exercise and the later whole-host power-off/on exercise. | V3; no notification-latency SLA |
| Host metrics | CPU, memory and host identity metrics appeared in Grafana Cloud. A deliberate disk-alert condition fired and delivered email, then the normal threshold was restored. | V3 |
| Failed-image rollback | A missing immutable candidate image failed deployment; the previous image returned to healthy operation with its public domain preserved. Database rollback was not claimed. | V3 |
| Planned reboot | SSH, Coolify, application endpoints, host verification/audit, logs, metrics and backup checks recovered. | V3 |
| Coolify lifecycle and lost-VPS reconstruction | The `4.1.2` → `4.3.21` interruption/resume and later replacement-host exercises passed. Recovery reconstructed Coolify identity, application database state and the immutable demo from off-site inputs. | V3; see [evaluation record](../docs/coolify-4.3.21-evaluation.md) |

The earlier chapter exercises were performed during September 2026 and recorded in the [release-readiness plan at the previous candidate](https://github.com/paracosm17/solo-vps/blob/4a95dba85b730427a5234457d5427d65c01a8bbb/RELEASE_READINESS_PLAN.md). The Coolify evaluation record and core replay record retain their own scope and limitations.

Removing obsolete plans and development banners does not change these evidence levels. Optional integrations remain separately exercised capabilities, not prerequisites for the core installation or a production reliability guarantee.
