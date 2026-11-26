# Solo VPS — product ideas and future work

> Owner direction captured: 2026-11-26.
> Status: planning / not implemented. Priorities below are a proposed sequence, not a release commitment.
> Current supported behavior: [README](README.md). Current state and evidence: [ROADMAP](ROADMAP.md). Architecture baseline: [Project Passport](PROJECT_PASSPORT.md) and accepted ADRs.

## 1. Product direction

Solo VPS should become a small, polished infrastructure product that a developer **or an authorized AI agent** can discover, install, configure, verify, maintain and troubleshoot with minimal instructions.

Owner goals:

- A normal user copies literally a couple of commands from README to get a working platform, rather than learning Make, Ansible, Git checkouts and internal confirmation variables.
- A normal platform update is one memorable command, for example `solo-vps update` (short alias `solo` is an option, not decided). Automatic updates are available only after the operator explicitly enables them.
- Output is concise and attractive for humans. Detailed operational reports are compact Markdown files designed to be read by agents, not multi-thousand-line terminal transcripts.
- Agents should immediately understand whether the project fits the user's goal, what is supported, what access is required, what to run, in which order, and how to tell whether it worked.
- Reconsider the full documentation, delivery and observability stack, maintenance burden of pinned dependencies, and the older optional terminal-environment idea.

These goals supersede the *long-term UX ambition* of the five-command Make interface, not its current documented behavior. They do not authorize removing safety gates, expanding the supported topology, installing optional services, or changing any production system. Keep current README commands accurate until a replacement is implemented and validated.

## 2. Why this matters: observed v0.2.8 update

The [production transition](reviews/2026-11-26-coolify-478-production.md) from Coolify 4.7.3 to 4.7.8 succeeded, and the [publication/installed-tag record](reviews/2026-11-26-release-028-publication.md) confirms clean verification from v0.2.8. The user experience nevertheless exposed a product problem:

- Manual Git fetch, detached checkout, setup, validation, doctor, update plan, firewall check, preflight, explicit environment variables, upgrade, separate verification and audit, then another exact-tag checkout.
- The user skipped the mutating upgrade once and ran verification too early; the safety guard correctly refused the origin marker. The command sequence was too easy to get wrong.
- A stale single-branch Git fetch configuration pointed to a removed candidate branch; the operator had to repair origin's fetch branch to main before obtaining the published tag.
- Old checkout copies accumulated; two contained root-owned Python cache files that required separately scoped cleanup.
- Maintainer-only release QA, secret scanning and publishing spilled onto the production host. Release dry-run initially failed because developer QA tools were missing; local tag creation also failed due to absent Git author identity.
- Huge Ansible/task/test logs buried the actual outcome among repeated banners, duplicated data, expected negative tests and retry messages. Success/expected failure/real failure were not obvious to the reader.

Distinguish **operator friction** from maintainer release work. Normal installed users must not publish project releases, install developer-only lint tooling, run secret scans of the source history, create candidate branches, or manually resolve routine lifecycle ordering. Keep evidence and build/release QA in the maintainer workflow. The user/agent experience, not just a new command name, is the modernization target.

## 3. Backlog (proposed order)

| ID | Idea | State | Suggested priority |
| --- | --- | --- | --- |
| UX-01 | Stable product CLI and minimal installation/configuration from README | PLANNED / V0 | First |
| UX-02 | One-command reviewed source + platform update, automatic recovery workflow | PLANNED / V0 | First |
| UX-03 | Human-friendly console and compact AI-oriented Markdown reports | PLANNED / V0 | First |
| AI-01 | Agent-first product discovery, documentation and deterministic operations | PLANNED / V0 | First |
| AI-02 | Agent-assisted bug reports to GitHub issues | PLANNED / V0 | First |
| DOC-01 | Full documentation information architecture and visual redesign | PLANNED / V0 | First |
| UPD-01 | Opt-in scheduled automatic Solo VPS/platform updates | DESIGN REVIEW / V0 | After manual updater |
| DEP-01 | Automated upstream compatibility review and dependency-pin maintenance | DESIGN REVIEW / V0 | Parallel design |
| CI-01 | Reconsider end-to-end CI/CD and registry delivery options | DESIGN REVIEW / V0 | Next |
| CI-02 | Managed GitHub Actions / GitLab CI self-hosted runner profile | IDEA / V0 | Next |
| OBS-01 | Optional self-hosted Grafana and appropriate log/metric storage | IDEA / V0 | Next |
| OPS-01 | Reevaluate S3/recovery, external uptime and observability defaults | DESIGN REVIEW / V0 | Next |
| SHELL-01 | Optional one-command terminal setup (existing M21) | DEFERRED / V0 | Later |
| OLD-01 | Other retained optional capabilities and deferred work | DEFERRED | Later |

### UX-01 — Product CLI, install and configuration

Provide a stable public executable (proposed name `solo-vps`) with a small, coherent lifecycle; do not simply rename every existing Make target into a new public command. Keep Make/Ansible internal if that is the simplest reliable implementation. Example future interface, **not current commands**:

```text
solo-vps install
solo-vps configure     # only if separate setup is genuinely needed
solo-vps update
solo-vps status
solo-vps logs          # locate the latest compact report
```

Design the real installation/bootstrap method and required inputs first. Aim for a trusted bootstrap plus one guided setup command, with a complete minimal README path. Discover already configured state; ask only for missing essential choices. Support guided interactive setup and an explicit non-interactive config path for agents/CI. Give clear preconditions, where to run, exit codes, safe defaults and next action. Do not pretend mandatory DNS, provider console, SSH identity proof or first-account setup can be skipped unless safely automated. Avoid remote shell pipelines without a reviewed integrity/bootstrap design.

Keep configuration, inventory, credentials, logs, checkpoints and update state outside the source checkout. Protect existing installations on repeated runs; a failed step should resume through the documented command rather than require reinstallation. Keep optional modules optional.

### UX-02 — One-command update

The normal user contract is one command:

```bash
solo-vps update
```

Proposed internal orchestration:

1. Acquire an operation lock; detect installed source/runtime version, configuration, and any interrupted transaction.
2. Discover an eligible **published, reviewed** Solo VPS release; confirm supported origin/target and artifact identity. Follow intermediate supported transitions when necessary; do not jump to arbitrary upstream versions.
3. Stage source safely, preserve external state and recoverable previous source; avoid depending on stale branch-specific fetch configuration or user-maintained candidate directories.
4. Run access/network/recovery preflight, required local checkpoint, compatibility and configuration checks. Resolve non-secret configuration such as the saved Sentinel URL without repeated ENV exports; require meaningful operator approval for exceptional or unsafe operations.
5. Execute the existing guarded platform/component lifecycle; wait for health and dependent services, use bounded retries for transient failures, verify exact image/version/identity and port policy. Preserve application data and avoid unrelated redeploys.
6. Commit installed identity only after successful verification/audit. Release the lock and summarize success, no-op, blocked or failed state. Bound stale staged copies and cleanup without deleting user files, active state or recovery inputs.
7. On interruption, inspect persisted transaction state, resume the reviewed forward path or stop safely with a precise recovery instruction. Source rollback must not be confused with reverting migrated databases.

The target is no avoidable manual intervention on the supported happy path, not a promise that networks, disks, external APIs or unsupported environments never fail. No silent adoption of drift, unconditional force, blind retry or automatic image downgrade after irreversible migration.

### UX-03 — Console and agent-oriented logs

Replace raw Ansible/Make output as the default interface. A human should see compact stage progress, final versions/outcome, important warnings and a report path; no long banners, verbose task dumps, duplicated JSON or expected test-fixture errors. Color/icons are optional; support plain/no-color, non-TTY output and deterministic output for automation. Errors must preserve an actionable cause, not hide it.

Write one durable, bounded Markdown report per operation to an operator-state directory such as `${XDG_DATA_HOME:-$HOME/.local/share}/solo-vps/logs/` (proposed), plus an atomic latest pointer. Example format (illustrative, not a runtime claim):

```markdown
# Solo VPS update
- schema: 1
- result: SUCCESS
- source: v0.2.7 -> v0.2.8
- Coolify: 4.7.3 -> 4.7.8
- mutation: completed
- recovery: local checkpoint retained
- stages: preflight PASS; upgrade PASS; verify PASS; audit PASS
- containers: 17/17 running
- pending: OS reboot required
- next: none for platform update
```

For failure include stage ID, stable error code, exit status, expected/observed value, bounded sanitized evidence, whether mutation occurred, transaction/checkpoint state and exact safe next action. Distinguish `SUCCESS`, `NO_OP`, `BLOCKED`, `FAILED` and `RESUME_REQUIRED`; distinguish expected negative checks and retries from final failures. State evidence scope and NOT RUN checks. Include timestamps/durations/revisions when useful, not repeated unchanged metadata. Consider an optional structured JSON result with the same schema for deterministic agents; Markdown remains the primary shareable report.

Keep raw diagnostics only behind an explicit debug option, locally private, bounded by rotation/retention; do not copy raw secrets into either report type. Use existing secret suppression, redact identifiers/paths/credentials before sharing, and test against leakage. Never assume a successful stage means all applications or restore paths were tested. Optimize actual report size/token use on real success and failure examples, not just terminal aesthetics.

### AI-01 — Agents as a first-class user audience

The maintainer-facing [AGENTS.md](AGENTS.md) already exists; distinguish **agents operating an installed Solo VPS for a user** from agents modifying this repository. Make a discoverable, concise public operating entry point linked from README; choose file conventions after review (for example an explicit agent quickstart, optionally llms.txt). No need to adopt a convention merely because it is fashionable.

Give the agent:

- product fit / non-fit, supported OS and topology, minimum resources, access and trust boundaries, ownership of host vs Coolify vs delivery;
- short command sequences for install/configure/update/status/recovery, with versioned interface, required inputs, execution location, exit codes, outputs and report paths;
- safe read-only discovery, documented non-interactive behavior and explicit approval boundaries before privileged or destructive changes;
- a compact task-to-document map, source-of-truth order, machine-readable examples and failure/recovery decision paths; link exact current-version documentation instead of requiring agents to infer commands from old reviews;
- reports that can be shared without pasting thousands of console lines or leaking private data.

Acceptance: an independent authorized agent starting from README can decide if Solo VPS is appropriate and complete a supported fresh setup and a subsequent update without undocumented maintainer help. A human following the same route can do it too. Record real clean/disposable evidence separately.

### AI-02 — Agent-assisted bug feedback

Add a visible invitation in the future agent entry point/contribution guide: if an agent using Solo VPS encounters a reproducible bug, it may propose an issue for the upstream project and submit it with the user's authorization and an authenticated account. Do not silently post issues, credentials or telemetry. Search for duplicates first; only report a concrete Solo VPS defect, not ordinary user errors or an upstream-only defect.

Provide a small issue template: affected published version/commit, supported environment (generic), command/stage/error code, expected versus observed behavior, reproduction on safe infrastructure, sanitized report excerpt, impact and suggested workaround if known. Label agent-assisted reports if useful. Remove tokens, private keys, actual IP/domain/resource identifiers, production inventory and raw logs. Security-sensitive problems go through [SECURITY.md](SECURITY.md) private reporting, not public issues. No automatic destructive reproductions. This idea does not yet change the reporting policy or submit issues.

### DOC-01 — Rebuild documentation and visual design

Owner is dissatisfied with the current information architecture and site design. Review existing EN/RU material from first principles; reuse the tested facts and essential safety steps, not necessarily the page structure or presentation.

Proposed separation:

- **Product**: what Solo VPS does/doesn't do, compatibility, minimal README/Quick Start, supported commands, configuration and optional profiles.
- **Operations**: install/update/status/diagnose/recover, short task-based pages and explicit failure paths; agent quickstart/reference.
- **Infrastructure guides**: broader GitHub/GitLab, registry, DNS, S3, monitoring and other third-party/general instructions that are not functionality of Solo VPS. Move to a clearly separate recipes/knowledge area or external links rather than interleave with required setup.
- **Maintainers**: architecture, ADRs, backlog, release gates and evidence outside the primary user journey.

Redesign navigation, typography, layout, code blocks, light/dark mode and language switching with concrete alternatives and owner review. Preserve equivalent EN/RU information, working links/redirects, accessibility, and version correctness. Do not publish proposed commands as working ones or move genuinely mandatory actions into disconnected pages. Replace obsolete wording/command-contract tests deliberately when the new implementation proves the changed UX.

### UPD-01 — Opt-in scheduled updates

Offer a user-enabled update schedule (cron is the owner's example; compare cron vs systemd timer), using the same trusted lifecycle as manual `solo-vps update`. Proposed policy: disabled by default; discovery/check-only and apply modes separately configurable; operator chooses interval/window, notices, allowed transitions and pause/disable. Persist configuration; no concurrent install/update/deploy conflict. Bound retry, jitter and network behavior; keep service health, lock, report and error recovery identical to manual mode.

Separate automatically safe source/component changes from potentially irreversible platform migrations, major versions and changes requiring manual evidence/approval. If no eligible reviewed path, required checkpoint or recovery input is missing, a deployment is active, or a prior transaction is unresolved, stop/defer with a compact report rather than guessing. Don't enable Coolify's native unattended updater as a shortcut. Design how an unattended operation can obtain all necessary approved inputs without copying human private keys or weakening access policy. Test no-op, transient network failure, incompatible release, concurrent runs, interruption and safe resume.

### DEP-01 — Pinned versions versus maintenance automation

Owner wants to avoid personally tracking every Coolify, Grafana or other dependency release while retaining protection against breaking changes. Current [ADR-0006](docs/adr/0006-reviewed-update-channels.md) explicitly distinguishes upstream availability, reviewed release manifests and runtime mutation; [dependency hygiene](docs/dependency-hygiene.md) already uses limited Dependabot updates and exact pins for several other classes.

Review trade-offs before changing the contract:

| Policy option | Upside | Downside |
| --- | --- | --- |
| Exact version + verified digest/checksums | Reproducible, auditable, known compatibility | Manual work and security-update lag unless automated |
| Floating tags / broad automatic upstream updates | Less manual version tracking | Drift, breaking changes, unreviewed migrations, unreliable rollback |
| Automated candidate PRs retaining reviewed pins | Reduces maintainer work while preserving release identity | CI/runtime test cost and incomplete automated breaking-change detection |
| Version-class or compatibility channels | Different treatment of safe dependency patches and platform migrations | Policy complexity, trust metadata and testing burden |

Proposed research direction (not selected implementation): automate upstream release discovery, compare manifests/artifacts, classify security fixes/migrations/breaking changes, produce candidate PRs with verified digests and release-note summaries, run static/controlled upgrade/health/security tests, and require the correct qualification before publishing an immutable Solo VPS release. Evaluate Renovate/Dependabot/custom bot coverage of GitHub/GitLab templates, Ansible Galaxy, Compose/image digests and other ecosystem pins. Automate ordinary low-risk changes only if evidence and policy justify it. A bot or release note is not proof of migration safety.

Keep two different loops: **maintainer** automated compatibility/release pipeline, and **operator** opt-in installation of published supported releases. A user need not track upstream versions, but blindly installing upstream latest on production is not the proposed solution. Document decisions per dependency class, advisory/patch cadence, version pin/digest refresh, compatibility chain, promotion approval and recovery. Supersede ADR-0006 and dependency policy explicitly if changed; do not weaken them incidentally.

### CI-01 / CI-02 — Delivery and self-hosted runners

Owner experiences GitHub hosted usage limits and wants to reevaluate GitHub/GitLab CI/CD and possible alternatives. Compare managed hosted runners, dedicated self-hosted runners, and other appropriate delivery modes; evaluate costs/quota, setup complexity, artifact identity, caching, credentials, throughput and recovery. Preserve the current tested GitHub Actions/GHCR path until a replacement is proven; GitLab support is new work, not current functionality.

Potential optional profile: Solo VPS installs/registers/configures, verifies, updates and removes a GitHub Actions runner or GitLab Runner with clear scope, labels, job isolation, cache/cleanup and a single operator interface. Keep the project repository's source CI distinct from consumer app deployment. Consider CI jobs executing arbitrary repository code, untrusted PRs, runner registration and secret rotation, Docker socket/root access, CPU/RAM/disk contention and backup/restore. A shared privileged runner on the application host is unsafe by default; evaluate restricted/ephemeral jobs or a separate explicitly authorized runner environment. The existing "build outside production" and one-VPS product contract are not silently relaxed; require an ADR/owner choice if a same-host runner or additional managed node changes those boundaries. A runner should not become required for a simple installation.

### OBS-01 / OPS-01 — Reevaluate surrounding infrastructure

Explore an optional **self-hosted Grafana** installation/management capability instead of assuming the existing managed Grafana Cloud approach is always appropriate. Compare managed vs self-hosted dashboard, logs/metrics collectors, storage, alerts, retention, TLS/authentication, upgrades, resources and recovery. Grafana alone is not a log/metric data backend; choose Loki/Prometheus or other storage only after evaluating need. Reuse current non-root Alloy/protected Docker boundary where appropriate. Keep Grafana/observability off the mandatory base path.

Review the current S3-compatible off-site restic/recovery path, PostgreSQL logical backups, uptime and alerting, and the full CI/CD-to-runtime flow. Determine what Solo VPS should actually automate vs document as optional provider-specific choices; compare managed/self-hosted and simpler alternatives, ongoing cost, availability and recovery. A service on the same VPS cannot independently detect total VPS outage or protect against loss of that VPS; preserve off-host uptime/backup boundaries when claiming those capabilities. Do not assume local Grafana or same-host object storage replaces external monitoring/recovery. Current proven optional integrations stay supported until an explicit alternative is selected and tested.

### SHELL-01 — Optional attractive terminal environment (existing M21)

One opt-in command should install and configure zsh, curated plugins, a clean theme/prompt, a few useful modern Unix tools (examples to evaluate: ripgrep, fd, fzf, bat, eza, zoxide), Git and navigation shortcuts. Make profile configurable, idempotent and reversible; preserve existing dotfiles, shell/login/recovery path, non-interactive scripts and SSH automation. Do not install for all users/root or overwrite shell settings without permission. Keep this separate from the server core and choose supported platforms and packages before implementing.

## 4. Other retained earlier ideas

The following were already present in [ROADMAP](ROADMAP.md), [Project Passport](PROJECT_PASSPORT.md), or [dependency hygiene](docs/dependency-hygiene.md); retain them rather than treating today's proposals as the entire project plan.

| Earlier item | Status / boundary |
| --- | --- |
| M8: optional Tailscale administrative/private network | Deferred |
| Developer/team onboarding, dev/prod permissions, access separation and offboarding | Deferred; not core for one operator |
| CRIT-012: CI deployment transport alternatives | Deferred; existing restricted SSH tunnel remains the proven default |
| M23: application error tracking (GlitchTip/Sentry-like) | Deferred |
| M25: database administration UI / pgAdmin and PostgreSQL guidance | Deferred |
| M24: richer host/container metrics, additional observability components | Existing optional retained logs/metrics are proven in a bounded scope; expansion deferred/review under OBS-01 |
| Provider-specific snapshot/DNS convenience automation | Optional idea in Passport, not an accepted implementation |
| Vulnerability scanning gates, SBOM/provenance, signing, image retention, automatic dependency merges | Deferred dependency-hygiene follow-up; reevaluate under DEP-01 |
| Multi-node, HA, Kubernetes/Nomad, self-hosted S3 | Explicitly outside current core scope / deferred; no decision to adopt |

## 5. Suggested sequencing and acceptance

1. Baseline the observed install/update friction; design the smallest public CLI contract and a common operation/result/report schema. Decide ownership and migration from the current Make interface before broad rewriting.
2. Implement and verify a reliable manual install/update path with transaction/resume, no-op, redaction and concise progress; test the exact failure cases from v0.2.8.
3. Write/verify human and agent quickstarts, contribution/issue guidance and the redesigned documentation against the actual CLI. Do not wait for every optional feature to simplify the core.
4. Add opt-in scheduled updates and separately evaluate maintainer-side dependency automation; test failure handling and safety before enabling real scheduled mutation.
5. Reassess the infrastructure options and introduce new runner/observability/shell capabilities independently, with optional profile boundaries and proportional runtime evidence.

Acceptance is outcome-based: a supported clean VPS can be configured with minimal commands and no undocumented workarounds; a supported release transition uses one manual command or the same opted-in scheduled workflow; repeated runs are safe/no-op; failure states are truthful and resumable when supported; agents and humans can find the correct next action from a compact report. Confirm this through independent clean/disposable replay and guarded production evidence, not just contract tests. Preserve all existing access, secrets, network, compatibility and data-recovery protections. No implementation, release number, priority lock-in, or live mutation is authorized by this backlog alone.
