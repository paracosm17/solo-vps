# Plan for the first public release

Updated: 2026-09-17. This is a maintainer/operator work plan, not another public installation guide. Current status remains in ROADMAP.md.

## Goal and working agreement

The owner wants the first public GitHub release to be a tested, usable product with clear documentation, rather than an early pre-alpha publication. Do not publish, purchase services or rent another VPS as part of preparing this plan. A stable label must follow evidence, not replace it.

The owner has completed the two basic chapters on a real VPS: host/platform setup, first application, successful post-merge CI/CD, version 2 over HTTPS, runtime APP_MESSAGE change and live logs. The supplied successful Actions screenshot includes publication, digest verification and deployment. This establishes observed integration success for the basic journey, with fixes applied along the way. It is not yet an uninterrupted clean installation of the eventual release revision.

At each stage, the engineer first checks implementation and prepares a complete EN/RU guide. The operator then follows that guide, reports non-secret results, and the engineer fixes any failure or ambiguous step in the canonical page before moving on. Preserve working stages; do not restart the whole setup after every documentation edit.

## Order of work and acceptance

| Stage | Engineering and documentation work | Operator exercise | Completion evidence |
| --- | --- | --- | --- |
| 0. Daily use | Replace jargon-heavy operator UI page with a visual explanation of code → PR → merge → image → running container, ENV, logs and incidents | Read it against the completed version-2 release | Reader can identify where each operation happens and distinguish successful build, deployment and business behavior |
| 1. Retained logs — immediate path verified | Rewrite Grafana guide from account setup through credentials, agent start, exact search, time range and export; check Docker labels on pinned Coolify | Generate a unique benign request; find it in Grafana; redeploy and find old and new entries; repeat the search after three days | Application-specific search works; old container logs remain searchable; retention and usage limits are understood; collection resumes after restart |
| 2. PostgreSQL and local recovery — verified | Prepare a complete Coolify-native local-backup guide; current database API helper requires S3, so use a verified UI path or extend the helper without another scheduler | Create an isolated test DB and known rows; confirm persistence after restart; run a local backup and scheduled execution; restore into another empty test DB | Restored data matches; original DB untouched; schedule, timezone, local retention and actual file availability verified |
| 3. External outage alerts — verified | Rewrite guide for one chosen external provider, endpoint and notification channel | Receive a test notification; cause a short agreed outage of the demo; recover it | Both outage and recovery messages arrive outside the VPS; detection interval and scope understood |
| 4. Off-site backups and recovery kit — verified | Guide external storage, app DB copy, Coolify control-plane backup, required files and separately protected keys; verify retrieval and retention | Retrieve a real external backup; restore into an isolated target and check application data | Recovery input independently available outside the VPS; include Coolify state and application files, not only DB rows |
| 5. Failed releases and maintenance — maintained-host path verified | Incident/maintenance guide and guarded rollback proof are implemented; pre-mutation authorization failures are distinguished from rollback failures | Maintained VPS proved failed-image rollback, log/metrics restarts and a required planned reboot; disposable target still covers interruption/resume and supported Coolify upgrade | App/data preserved where promised; public app, Coolify, logs, metrics and backup runtime recovered after reboot; upgrade recovery remains a disposable-target gate |
| 6. Useful metrics — verified | Separate non-root Alloy host-metrics service and metrics-only credentials are live; current Grafana alert/editor and email-member restrictions are documented | Operator verified Metrics Drilldown, CPU/RAM queries, a real `Firing` disk alert with email delivery, then restored the production `15%` / `5m` configuration | Metrics, alert delivery and production threshold restoration proven on the maintained VPS |
| 7. Documentation and clean rehearsal | Complete docs cleanup, package candidate, run Linux/Ansible/Docker checks and scan source/archive/history for private data | Install exact candidate on temporary clean Ubuntu using public docs only; restore demo and check its data | No chat-only steps; installation and recovery work; UI labels, EN/RU commands and package match the tested revision |
| 8. GitHub publication | Prepare README, license, versions, release notes, limitations, immutable release identity, security reporting and hosted CI | Review concrete candidate; publish only when authorized | Source CI passes on candidate; final hosted checks run when repository is available; demo CI is not confused with Solo VPS CI |

Retained logs come first because the current demo has no database and the owner needs investigation across deployments. Once a database holds valuable data, backup/restore takes priority over extra dashboards. External monitoring follows early so incidents become visible without opening Grafana.

## Retained-log decision

The implemented path is Alloy → Grafana Cloud through a restricted local Docker API proxy. Self-hosted Grafana/Loki storage is not currently implemented by Solo VPS and would be a separate scoped feature. Use Cloud for the first walkthrough unless the operator chooses otherwise.

Before creating credentials, establish whether an account/stack exists, its retention and usage limits, and whether sending application logs there is acceptable. Reuse existing workstation encryption keys. The free offering checked during planning advertises 14-day retention and 50 GB/month for logs; recheck the live plan before relying on those limits. A month of uptime does not require month-long retention to investigate an error three days old, but an error a month old does.

Do not promise recovery of entries deleted before collection began. Do not declare a three-day history test passed immediately: record a unique marker/time and search after the actual interval. Test container replacement independently now. A collector restart test does not prove lossless buffering across every outage; record delivery gaps.

The live Windows walkthrough on 2026-09-11/12 caught four workstation-specific failures before Grafana credentials were installed: downloaded PowerShell helpers retained the Internet-origin mark, `age-keygen` informational stderr became a terminating `NativeCommandError`, a stale public SOPS policy could survive replacement of the age private key, and a legitimate encrypted bundle from an earlier walkthrough made the recovery-only reset path unusable for a clean documentation rerun. The public guide now uses `Unblock-File`; the age-key helper is idempotent and restricts the private-key ACL; repeated secret initialization reuses a decryptable bundle; and `init-sops-policy.ps1 -StartFresh` archives old public state plus active ciphertext before creating a clean policy for the current key. Keep replaying the real Windows path; static Linux CI is not sufficient evidence for these helpers.

The same walkthrough then completed Grafana credential delivery and the real Alloy runtime on the target. The operator found `solo-vps-log-check-before`, `solo-vps-log-check-after` after a Coolify redeploy, and `solo-vps-log-check-restarted` after restarting Alloy. The post-restart read-only runtime verification also passed. This closes the immediate retained-log path at V3; the deliberately time-dependent three-day retention lookup remains open. Browser feedback also showed that current Grafana Cloud makes **Drilldown → Logs** the clearest beginner path, while the old guide incorrectly required **Explore → Code**. Chapter 3 now uses Drilldown, distinguishes the server-side Line filter from client-side search, and keeps LogQL/Explore optional.

Planning sources: [Grafana pricing](https://grafana.com/pricing/), [Coolify local and S3 backups](https://next.coolify.io/docs/databases/backups), repository Alloy configuration and database API helper. Verify concrete UI commands against pinned Coolify before the operator exercise.

## Documentation shape

Keep **Basic setup** as the two completed chapters. Add **After basic setup** with an overview and daily-use explanation now. As each guide becomes complete, place sequential tasks there: retained logs; PostgreSQL and local copies; outage alerts; external copies and recovery. Do not disguise technical references as completed beginner tutorials by merely renaming them.

User pages explain the task, prerequisites, execution location, input source, action, expected result and recovery where relevant. Use familiar Russian and exact English UI labels. Diagrams explain where code, images, settings, logs and backups move. Show the usefulness of Solo VPS with concrete tasks and honest tradeoffs: one server is simpler to operate but has no high availability; managed services reduce maintenance but require separate accounts.

Remove internal ADR/milestone/critic references, abandoned experiments, repeated verification chains and implementation essays from the first-user route. Preserve useful technical material in maintainer/reference locations. Adjust validators that require obsolete wording instead of hiding strings in HTML comments. Preserve actual security checks, supported behavior and evidence limits.

README and home page should answer: what problem is solved, for whom, what is configured, what still requires operator work, and where to begin. Explain the Dockerfile, tests, ports, runtime config and data requirements when adapting a user's application.

## Owner pre-release review — 2026-09-13

The owner completed a separate review of the rendered documentation and the remaining product/release surface. The detailed backlog is recorded in [`reviews/2026-09-13-first-release-prep.md`](reviews/2026-09-13-first-release-prep.md) so the feedback is not lost in chat.

Before the exact-candidate rehearsal, do one deliberate documentation/productization pass: replace confusing hard-coded sample identity/address values in the guided route with semantic variables, move incident/maintenance material out of the numbered setup chapters, make chapters 1–7 visually dominant over reference trees, remove development-time troubleshooting chronology, and soften the documentation palette. Then run the full owner walkthrough from scratch using only the rendered docs and no ChatGPT.

The first release also needs an explicit lifecycle decision before freezing the candidate. The source currently pins Coolify `4.1.2`, while the maintained instance reports a much newer available release. Do not upgrade the maintained instance merely for freshness; review upstream changes, select the release baseline intentionally, and prove install/upgrade/recovery on the disposable target. In parallel, document a tagged Solo VPS source-update path instead of teaching users to `git pull` an active checkout blindly.

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

This sequence is deliberately linear. Do not combine stages to save a VPS rental day, and do not upgrade the maintained server while the disposable lifecycle gate is open. Each stage ends with a concrete report or committed candidate before the next one starts.

### 1. Review the rendered documentation at the current candidate commit

Review the current candidate before disposable testing.

1. Confirm the documentation baseline is in the current history and the checkout is clean:

   ```bash
   git rev-parse HEAD
   git status --short
   ```

   Expected: record the SHA from `git rev-parse HEAD`; `git status --short` produces no output. Review the rendered documentation for that exact revision.

2. From Linux or WSL, start the documentation preview:

   ```bash
   make docs
   ```

   Open `http://127.0.0.1:8000/`. Keep the command running while reviewing. Use `Ctrl+C` when finished.

3. Review the English route first, then switch to Russian and inspect the same pages:

   - Home and Quick Start;
   - chapters 1–7 under the guided setup route;
   - Daily operations and Failures and maintenance;
   - Upgrade guide and Lost VPS recovery;
   - mobile/narrow browser width for the navigation and code blocks.

4. Check only reader-facing quality at this stage:

   - the first action on each page is obvious;
   - commands say where they run;
   - placeholders such as `<SERVER_IP>` and `<ADMIN_USER>` are unambiguous;
   - chapters 1–7 are visually dominant, while reference material is quieter;
   - chapter 8 is no longer presented as another installation chapter;
   - colors, callouts, tables and code blocks remain readable;
   - Russian and English pages do not contradict each other;
   - no paragraph sounds like internal debugging history or generated filler.

5. Return findings in the form `page -> fragment -> desired change`. Screenshots are useful for layout problems. If there are no findings, report `documentation review PASS`.

Do not follow the VPS commands during this stage. The maintained server already proves chapters 1–7; this pass reviews the release-candidate reading experience.

### 2. Freeze the documentation candidate

The engineer incorporates the review, runs the documentation/release validators and strict MkDocs builds, and commits the result. The owner then checks only changed pages. Completion evidence is a clean committed tree and owner approval of the rendered candidate.

### 3. Qualify Coolify `4.3.21` and Sentinel on a disposable VPS

This happens before any maintained-server upgrade. Sentinel is a Coolify-managed metrics/API agent container, not a server operating mode and not Redis Sentinel. The previously tested `4.1.2` setup disabled the optional agent because its Docker bridge could not reach the loopback-only Coolify endpoint. Since Coolify `4.3.19`, Sentinel is mandatory on regular servers, so the old "container absent" state is historical evidence rather than the future Solo VPS contract.

Before asking the owner to rent or reset a target, the engineer must commit automation and an exact exercise sheet that covers:

- a fresh `4.1.2` baseline from the candidate source;
- a reviewed `4.1.2 -> 4.3.21` upgrade with a fresh backup and no active deployment;
- Sentinel image/version, health, token-authenticated communication, Docker socket mount, host mounts, published ports and Docker-network reachability;
- proof that management endpoints remain outside the public Internet;
- `make verify-coolify`, `make verify`, `make audit`, application health, CI deployment, logs, metrics and backups after the upgrade;
- one interrupted upgrade followed by documented forward resume or recovery;
- deletion of the disposable server after evidence is exported and secrets are revoked.

The committed procedure is [`docs/coolify-4.3.21-evaluation.md`](docs/coolify-4.3.21-evaluation.md). Follow it in order and stop on the first unexpected result; it is not a maintained-server upgrade guide.

The acceptance decision is not "make Sentinel disappear." Accept it only if its required access is explicit, its API is authenticated, no unintended public port appears, and Solo VPS verification/backup/recovery understand the component. Otherwise keep the maintained server on the old supported pin and record `4.3.21` as rejected or blocked.

### 4. Reconstruct a lost VPS on a replacement target

Use a new or wiped target, the exported recovery kit, off-site restic data and Coolify/database backups. Follow only the committed lost-VPS guide. The restored application must contain the known data marker; public HTTPS, Coolify state, deployment, logs/metrics and backup scheduling must be re-verified. Record every undocumented dependency as a release blocker, fix it, commit it, and repeat the failed section.

### 5. Run the exact-candidate clean rehearsal without ChatGPT

Create a fresh Ubuntu 24.04 VPS and use only the public rendered documentation from one clean commit. Do not reuse shell history, local config, an existing Coolify database or chat instructions. Complete setup, application deployment, CI/CD, observability, backup and restore. During this target's lifetime, perform the whole-VPS outage test and confirm both external DOWN and recovery notifications.

### 6. Configure the GitHub release surface

The first public source push is complete at `https://github.com/paracosm17/solo-vps`. The exported tree and new history passed Gitleaks before publication. `main` is the default branch, Pages now deploys from GitHub Actions, and Private Vulnerability Reporting is enabled. Require a green hosted `Repository CI / fast-source` check, verify the deployed EN/RU and edit links after `site_url` is committed, protect `main`, and test vulnerability reporting from a reporter account. Repeat exact-ref history and archive scans before any release tag. A demo application's CI result does not satisfy the repository CI gate.

### 7. Package and publish only after every prior stage passes

Prepare the dated `CHANGELOG.md` entry, run `make release-dry-run RELEASE_VERSION=v0.1.0` from a clean tree, review the resulting commit, then explicitly approve the annotated tag and GitHub Release. Do not move or replace the published tag afterward.

The chapter-3 three-day Grafana marker remains a separate time-dependent check. It may run in parallel with the documentation review, but its result must be recorded before the release candidate is frozen.
