# Plan for the first public release

Updated: 2026-09-27. This is a maintainer/operator work plan, not another public installation guide. Current status remains in ROADMAP.md.

## Goal and working agreement

The owner wants the first public GitHub release to be a tested, usable product with clear documentation, rather than an early pre-alpha publication. Do not publish, purchase services or rent another VPS as part of preparing this plan. A stable label must follow evidence, not replace it.

The owner has completed the two basic chapters on a real VPS: host/platform setup, first application, successful post-merge CI/CD, version 2 over HTTPS, runtime APP_MESSAGE change and live logs. The supplied successful Actions screenshot includes publication, digest verification and deployment. This establishes observed integration success for the basic journey, with fixes applied along the way. It is not yet an uninterrupted clean installation of the eventual release revision.

At each stage, the engineer first checks implementation and prepares a complete EN/RU guide. The operator then follows that guide, reports non-secret results, and the engineer fixes any failure or ambiguous step in the canonical page before moving on. Preserve working stages; do not restart the whole setup after every documentation edit.

## Order of work and acceptance

| Stage | Engineering and documentation work | Operator exercise | Completion evidence |
| --- | --- | --- | --- |
| 0. Daily use | Replace jargon-heavy operator UI page with a visual explanation of code → PR → merge → image → running container, ENV, logs and incidents | Read it against the completed version-2 release | Reader can identify where each operation happens and distinguish successful build, deployment and business behavior |
| 1. Retained logs — verified | Rewrite Grafana guide from account setup through credentials, agent start, exact search, time range and export; check Docker labels on pinned Coolify | Generate a unique benign request; find it in Grafana; redeploy/restart the collector and find earlier entries; later confirm older entries are still searchable | Application-specific search works; old container logs remain searchable in the operator's later check; collection resumes after restart; no fixed retention-duration SLA is claimed |
| 2. PostgreSQL and local recovery — verified | Prepare a complete Coolify-native local-backup guide; current database API helper requires S3, so use a verified UI path or extend the helper without another scheduler | Create an isolated test DB and known rows; confirm persistence after restart; run a local backup and scheduled execution; restore into another empty test DB | Restored data matches; original DB untouched; schedule, timezone, local retention and actual file availability verified |
| 3. External outage alerts — verified | Rewrite guide for one chosen external provider, endpoint and notification channel | Receive a test notification; cause a short agreed outage of the demo; recover it | Both outage and recovery messages arrive outside the VPS; provider scope is understood; no precise notification-time SLA is required or claimed |
| 4. Off-site backups and recovery kit — verified | Guide external storage, app DB copy, Coolify control-plane backup, required files and separately protected keys; verify retrieval and retention | Retrieve a real external backup; restore into an isolated target and check application data | Recovery input independently available outside the VPS; include Coolify state and application files, not only DB rows |
| 5. Failed releases and maintenance — maintained-host path verified | Incident/maintenance guide and guarded rollback proof are implemented; pre-mutation authorization failures are distinguished from rollback failures | Maintained VPS proved failed-image rollback, log/metrics restarts and a required planned reboot; disposable target still covers interruption/resume and supported Coolify upgrade | App/data preserved where promised; public app, Coolify, logs, metrics and backup runtime recovered after reboot; upgrade recovery remains a disposable-target gate |
| 6. Useful metrics — verified | Separate non-root Alloy host-metrics service and metrics-only credentials are live; current Grafana alert/editor and email-member restrictions are documented | Operator verified Metrics Drilldown, CPU/RAM queries, a real `Firing` disk alert with email delivery, then restored the production `15%` / `5m` configuration | Metrics, alert delivery and production threshold restoration proven on the maintained VPS |
| 7. Documentation and clean rehearsal | Complete docs cleanup, package candidate, run Linux/Ansible/Docker checks and scan source/archive/history for private data | Install exact candidate on temporary clean Ubuntu using public docs only, including the two scoped Coolify API tokens and automatic deployment; run verification, audit and idempotency checks | No chat-only steps; installation and deployment work; UI labels, EN/RU commands and package match the tested revision |
| 8. GitHub publication | Prepare README, license, versions, release notes, limitations, immutable release identity, security reporting and hosted CI | Review concrete candidate; publish only when authorized | Source CI passes on candidate; final hosted checks run when repository is available; demo CI is not confused with Solo VPS CI |

Retained logs come first because the current demo has no database and the owner needs investigation across deployments. Once a database holds valuable data, backup/restore takes priority over extra dashboards. External monitoring follows early so incidents become visible without opening Grafana.

## Retained-log decision

The implemented path is Alloy → Grafana Cloud through a restricted local Docker API proxy. Self-hosted Grafana/Loki storage is not currently implemented by Solo VPS and would be a separate scoped feature. Use Cloud for the first walkthrough unless the operator chooses otherwise.

Before creating credentials, establish whether an account/stack exists, its retention and usage limits, and whether sending application logs there is acceptable. Reuse existing workstation encryption keys. The free offering checked during planning advertises 14-day retention and 50 GB/month for logs; recheck the live plan before relying on those limits. A month of uptime does not require month-long retention to investigate an error three days old, but an error a month old does.

Do not promise recovery of entries deleted before collection began or a fixed provider retention duration. Test container replacement and collector restart independently; a collector restart test does not prove lossless buffering across every outage, so record any observed delivery gaps.

The live Windows walkthrough on 2026-09-11/12 caught four workstation-specific failures before Grafana credentials were installed: downloaded PowerShell helpers retained the Internet-origin mark, `age-keygen` informational stderr became a terminating `NativeCommandError`, a stale public SOPS policy could survive replacement of the age private key, and a legitimate encrypted bundle from an earlier walkthrough made the recovery-only reset path unusable for a clean documentation rerun. The public guide now uses `Unblock-File`; the age-key helper is idempotent and restricts the private-key ACL; repeated secret initialization reuses a decryptable bundle; and `init-sops-policy.ps1 -StartFresh` archives old public state plus active ciphertext before creating a clean policy for the current key. Keep replaying the real Windows path; static Linux CI is not sufficient evidence for these helpers.

The same walkthrough then completed Grafana credential delivery and the real Alloy runtime on the target. The operator found `solo-vps-log-check-before`, `solo-vps-log-check-after` after a Coolify redeploy, and `solo-vps-log-check-restarted` after restarting Alloy. The post-restart read-only runtime verification also passed. This closes the retained-log path at V3. The owner later confirmed that older entries remained searchable after several days; that observation is recorded as evidence, not as a retention SLA. Browser feedback also showed that current Grafana Cloud makes **Drilldown → Logs** the clearest beginner path, while the old guide incorrectly required **Explore → Code**. Chapter 3 now uses Drilldown, distinguishes the server-side Line filter from client-side search, and keeps LogQL/Explore optional.

Planning sources: [Grafana pricing](https://grafana.com/pricing/), [Coolify local and S3 backups](https://next.coolify.io/docs/databases/backups), repository Alloy configuration and database API helper. Verify concrete UI commands against pinned Coolify before the operator exercise.

## Documentation shape

Keep **Basic setup** as the two completed chapters. Add **After basic setup** with an overview and daily-use explanation now. As each guide becomes complete, place sequential tasks there: retained logs; PostgreSQL and local copies; outage alerts; external copies and recovery. Do not disguise technical references as completed beginner tutorials by merely renaming them.

User pages explain the task, prerequisites, execution location, input source, action, expected result and recovery where relevant. Use familiar Russian and exact English UI labels. Diagrams explain where code, images, settings, logs and backups move. Show the usefulness of Solo VPS with concrete tasks and honest tradeoffs: one server is simpler to operate but has no high availability; managed services reduce maintenance but require separate accounts.

Remove internal ADR/milestone/critic references, abandoned experiments, repeated verification chains and implementation essays from the first-user route. Preserve useful technical material in maintainer/reference locations. Adjust validators that require obsolete wording instead of hiding strings in HTML comments. Preserve actual security checks, supported behavior and evidence limits.

README and home page should answer: what problem is solved, for whom, what is configured, what still requires operator work, and where to begin. Explain the Dockerfile, tests, ports, runtime config and data requirements when adapting a user's application.

## Owner pre-release review — 2026-09-13

The owner completed a separate review of the rendered documentation and the remaining product/release surface. The detailed backlog is recorded in [`reviews/2026-09-13-first-release-prep.md`](reviews/2026-09-13-first-release-prep.md) so the feedback is not lost in chat.

Before the exact-candidate rehearsal, do one deliberate documentation/productization pass: replace confusing hard-coded sample identity/address values in the guided route with semantic variables, move incident/maintenance material out of the numbered setup chapters, make chapters 1–7 visually dominant over reference trees, remove development-time troubleshooting chronology, and soften the documentation palette. Then run the full owner walkthrough from scratch using only the rendered docs and no ChatGPT.

The Coolify lifecycle decision is complete for this release: current-supported is `4.3.21`, previous-supported is `4.1.2`, and the disposable upgrade/interruption/recovery exercise passed before promotion. The tagged Solo VPS source-update path is documented so users do not `git pull` over an active installation checkout.

## Resource and release boundaries

Use the current demo for reversible application checks. Plan destructive recovery, SSH-interruption and upgrade exercises on one temporary target in a batched window, once source and instructions are ready. Do not reboot or interrupt the current VPS merely to advance this checklist without scheduling it with the operator.

Local DB backups are useful, not disaster recovery. Off-site recovery can remain an optional installation profile, but a published claim that it works requires a real restore before release. Error trackers and pgAdmin are outside the immediate route unless a concrete task requires them.

2026-09-12 live chapter-4 test: the first Coolify `Backup Now` exposed a real Solo VPS integration bug: the pinned non-root server identity could not write `/data/coolify/backups/.../pg-dump-*.dmp`. The managed Coolify filesystem contract was corrected to a private UID-9999/admin-group `0730` backup root and reconciled successfully on the live server. The operator then repeated `Backup Now`, downloaded the backup, inserted a second `after-backup` row into the source database, restored the saved file into a separate PostgreSQL resource, and verified that the restored database contained only `1|before-backup`. This closes the chapter-4 local backup/restore path: the restored state matches the backup point and the source database remained independently modified.

2026-09-12 live chapter-5 test: the operator configured UptimeRobot against the public application health endpoint, stopped the demo application, and received the external outage email as expected. The monitor remained independent of the VPS. This closes the normal chapter-5 outage-alert path; a whole-VPS shutdown remains reserved for the later disposable-target release exercise.

The chapter-5 public path is now concrete rather than provider-neutral: UptimeRobot Free, one HTTPS `/healthz` monitor, an attached email contact, Test Notification, a short reversible stop/start of the demo application, and observed DOWN/UP delivery. The free plan's 5-minute interval and provider confirmation retries replace the old fictitious "two consecutive failures" setting, which is not a configurable Free-plan control. Whole-VPS shutdown remains a separate release proof for a disposable target and is not part of the beginner exercise.

2026-09-13 live chapter-6 test: Backblaze B2 account/bucket creation succeeded without the Cloudflare payment-card blocker. Coolify uploaded the application PostgreSQL backup to B2; the operator restored that backup directly through Coolify's S3 restore path into a separate PostgreSQL resource and verified only `3|before-offsite`, while the source had already advanced to `4|after-offsite`. Coolify's own instance database backup also appeared in B2. Solo VPS then initialized the real encrypted restic repository, created snapshot `4308d59c49ca`, passed freshness verification, restored that snapshot into temporary staging with `production_paths_modified: false` and `temporary_restore_removed: true`, and enabled the daily `solo-vps-backup.timer`. The B2 bucket now correctly contains separate `data/coolify/backups/...` objects from Coolify and `solo-vps/<hostname>/{config,data,index,keys,locks,snapshots}` restic repository objects. This closes the normal chapter-6 off-site backup/restore path at V3; full lost-VPS reconstruction remains a later disposable replacement-host exercise.

2026-09-13 live chapter-7 test: metrics credentials/runtime succeeded; the dedicated Alloy service is running/enabled with its HTTP listener bound to `127.0.0.1:12346`, root-owned `0600` credentials and `failed=0`. Grafana Metrics Drilldown shows `node_uname_info` with `job=integrations/node_exporter`; Explore returns live CPU and memory percentages for `prod-001`. The operator created the current simplified disk rule, proved the test `IS BELOW 101` condition reaches `Firing`, and received the Grafana email notification; the rule was then restored to the production `IS BELOW 15` threshold with a `5m` pending period, where the condition evaluates normal. The walkthrough also exposed documentation mismatches now fixed: newly arrived metrics may require the visible circular-arrow refresh, contact-point email recipients must be organization members in this Grafana Cloud flow, the default rule editor does not require manual Reduce/Threshold expressions while **Advanced options** is off, and Grafana email may land in Spam/Junk. This closes the normal chapter-7 metrics/alert path at V3.

The same walkthrough exposed two UX issues now fixed in source/docs: repository `init` and `adopt` were easy to read as sequential commands even though they are mutually exclusive paths, and an older root-driven admin handoff could leave `~/.local/share` root-owned, causing ordinary `nano` state/history creation to warn with `Permission denied`. The handoff now reconciles only the standard admin XDG data parents, and chapter 6 explicitly enters `~/solo-vps`, treats `prefix: solo-vps` as required, makes direct S3 restore the primary path, explains the restic object layout, and warns that printed `APP_KEY` output is secret evidence that must be redacted.

2026-09-13 chapter-8 rollback proof: the first maintainer proof attempt correctly made no mutation but refused the real demo application because the proof target still inherited the older isolated-resource `no public domain` guard. After that guard was fixed, an insufficient API token produced HTTP 403 on the candidate desired-state PATCH. That request was rejected before mutation; the deploy helper now classifies this as `DEPLOY_NOT_STARTED` and does not attempt or report a fake rollback. The proof was then rerun with a separate reviewed short-lived maintainer root token and passed end to end: the deliberately missing immutable candidate failed, the exact previous immutable image was restored, the application returned `running:healthy`, and its public-domain configuration was preserved. `make verify-coolify`, `make audit`, `/` and `/healthz` all passed afterward. The temporary elevated token must be revoked after the exercise and must not replace the least-privilege CI token.

The same post-proof audit reported `reboot_required: true` from Ubuntu security-update evidence. A planned reboot is therefore operationally justified on this maintained VPS rather than being performed only for documentation. Before reboot, finish the non-destructive chapter-8 checks, verify the latest backup, ensure no deployment is active, and use the documented before/after checklist. The previous-supported → current-supported Coolify upgrade and complete lost-VPS recovery remain reserved for a disposable target.
2026-09-13 planned reboot evidence: pre-reboot log/metrics runtime verification and off-site backup freshness all passed; the daily backup timer was active. The host rebooted cleanly, SSH returned, aggregate `make verify`, `make audit`, `make verify-coolify`, metrics verification, backup freshness and the public application endpoints all passed afterward. Ubuntu then reported `reboot_required: false`. The first post-reboot retained-log verification exposed a verifier false positive: Alloy itself was active with readiness/health `200`, but a bare expected Docker-proxy `403` was classified as a Grafana provider-auth failure. The classifier was narrowed to require Grafana/Loki/remote-write context for `401/403`; the operator then reran `make verify-observability-runtime` without changing credentials or permissions and it passed with `failed=0`, `recent_provider_auth_errors: false`, healthy loopback readiness, and the intended Docker API boundary intact. This closes the maintained-host chapter-8 reboot/maintenance path at V3.


## Immediate owner sequence for `v0.1.0`

The earlier Coolify qualification, whole-host outage, lost-VPS reconstruction, retained-log checks, backup/restore exercises and GitHub security-channel setup are already evidence. Do not rerun them merely to satisfy ceremony. The remaining sequence is intentionally short.

### 1. Freeze the source/documentation candidate

Review the rendered EN/RU Home, Quick Start, first-application guide, daily operations, upgrade and recovery pages. Fix stale UI labels, contradictory version statements, duplicated text and development-history wording. Run the documentation/release validators and strict MkDocs build.

### 2. Reconcile the independent clean-host rehearsal with the candidate

The owner followed the public first two chapters on a clean Ubuntu 24.04 VPS at Solo VPS commit `0fdba7f` and reported a working application with automatic deployment. The supplied logs show clean bootstrap, administrator/SSH hardening, Coolify `4.3.21`, `verify-coolify`, full `verify` and `audit` without failed Ansible tasks. Changes through `bf02b74` touch only documentation, CSS and release metadata. Carry this rehearsal forward while later candidate changes remain operationally equivalent and the rendered guide still matches the route. The missing proof is an idempotent second `make platform` run on this host with `changed=0`.

If later candidate changes alter operational behavior or required clean-install proof is missing, repeat the full public route on a clean Ubuntu 24.04 VPS. A docs-only edit does not itself require reimaging if the executed route is equivalent. On a repeat, do not reuse old controller state, Coolify data, shell history or chat-only instructions. Optional Grafana/B2 chapters already have separate V3 evidence and are not repeated unless the clean replay exposes a dependency on them. Any missing value, renamed Coolify control or undocumented recovery step is a release defect: fix the source/docs and repeat the affected section.

### 3. Validate the exact release commit on GitHub

Push/merge the candidate only with explicit owner authorization. Require the hosted `Repository CI / fast-source` check and documentation deployment to pass for the exact release commit. Confirm Pages renders the same EN/RU instructions. Repeat the built-in exact-ref/archive inspection and an independent Gitleaks scan against the refs that will be released.

Private Vulnerability Reporting is already enabled and the public GitHub security page exposes **Report a vulnerability**. A synthetic report from a second account is optional maintainer testing, not a Solo VPS release gate.

### 4. Prepare and publish `v0.1.0`

Move the release contents from `Unreleased` into a dated `0.1.0` changelog section, leave a fresh `Unreleased` section above it, and run:

```bash
make release-dry-run RELEASE_VERSION=v0.1.0
```

Review the exact clean commit and release notes. Only after explicit owner approval create the immutable annotated tag and GitHub Release. Do not move or replace the published tag.

The project makes no precise UptimeRobot notification-latency SLA and no fixed Grafana Cloud retention SLA; those provider-dependent measurements are not release gates.
