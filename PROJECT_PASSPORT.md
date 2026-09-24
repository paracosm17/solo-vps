# PROJECT PASSPORT — Solo VPS

> **Role:** concise north-star product and architecture contract.  
> **Status:** TARGET / DESIGN BOUNDARY — this file is **not** the current implementation-status ledger.  
> **Current supported contract:** [`README.md`](README.md).  
> **Current development state / blockers / next action:** [`ROADMAP.md`](ROADMAP.md).  
> **Engineering process:** [`.agents/skills/solo-vps-project-engineer/SKILL.md`](.agents/skills/solo-vps-project-engineer/SKILL.md).

Solo VPS is an opinionated open-source path from a clean Ubuntu VPS to a small, reproducible application platform for a solo developer operating it directly.

The project optimizes for **one operator workstation + one Ubuntu VPS**, boring technology, explicit recovery, and a small public operator surface. It is not a multi-node platform and should not grow into one accidentally.

---

## 1. Product promise

The base profile requires one VPS only: no scheduled backups, snapshots, external storage or Grafana. Local control-plane checkpoints may protect explicit upgrades. Scheduled local application backups and off-site backup/recovery are separate optional capabilities; local copies never imply recovery after loss of the VPS.

A user should be able to take a supported clean VPS and, with a small number of documented commands, reach a state where:

- administrative access is non-root, key-based, recoverable, and verified;
- host firewall and security-update policy are explicit;
- Docker is installed and bounded by a known host policy;
- Coolify owns application/service lifecycle and browser-first operations;
- application delivery can use GitHub Actions + GHCR with immutable images;
- infrastructure/recovery secrets are not stored in plaintext Git;
- off-site backup and restore are available when the recovery profile is enabled;
- verification, audit, upgrade, and disaster-recovery paths are documented and testable.

The project should feel like a **small product**, not a bag of shell snippets.

The normal operator workflow should converge toward:

```text
make setup
make apply
make secure
make platform
make verify
```

Additional operations such as backup, recovery, upgrades, diagnostics, and optional observability must remain explicit and independently understandable.

---

## 2. Audience

### Primary audience

- solo developers;
- freelancers;
- people running a few applications on one VPS;
- operators who want reproducibility without Kubernetes/Nomad-scale complexity.

Team onboarding and role separation are future capabilities, not part of the `v0.1.0` support promise.

The normal ownership model is:

```text
Windows or Linux workstation
        +
one Ubuntu VPS
```

A managed external service such as GitHub, GHCR, object storage, or Grafana Cloud does not become another operator-managed compute node.

### Not the primary audience

Solo VPS is not designed as the default answer for:

- multi-region or HA clusters;
- fleets of dozens/hundreds of servers;
- zero-trust enterprise identity platforms;
- regulated environments requiring a bespoke compliance control plane;
- Kubernetes/Nomad replacement projects;
- teams that already have a mature internal platform.

---

## 3. Core principles

1. **One VPS first.** There is exactly one maintained application VPS in the core compute topology.
2. **Boring technology first.** Prefer standard Linux, Ansible, Docker, systemd, OpenSSH, and documented platform APIs.
3. **Automate repeated operations.** Documentation explains intent; automation performs recurring mutation.
4. **Secure by default.** Minimize public ports, credentials, mutable tags, and privileged surfaces.
5. **Recovery is a feature.** Backup without an exercised restore is incomplete evidence.
6. **Build outside production.** CI builds/tests artifacts; production consumes reviewed immutable artifacts.
7. **Reproducibility over cleverness.** Hidden manual state is a defect.
8. **UI-first operations.** Prefer GitHub/Coolify/Grafana browser workflows for daily use; CLI is the deterministic fallback/control layer.
9. **Optional complexity stays optional.** An optional module must not become a prerequisite for the core acceptance path.
10. **Evidence must match the claim.** Static/local tests do not become clean-VPS or production proof by wording.

---

## 4. Responsibility boundaries

### 4.1. Host layer

**The Ansible project owns the host layer**:

- supported Ubuntu baseline;
- administrator identity, SSH and sudo policy;
- UFW host-input policy;
- unattended security updates;
- Docker host installation/configuration;
- host-side recovery tooling;
- read-only verification/audit;
- optional host-side agents that are explicitly selected.

Ansible must not become a second application orchestrator beside Coolify.

### 4.2. Application platform

**Coolify owns the application platform**:

- applications and services;
- reverse proxy / TLS / domains;
- runtime environment variables and application secrets;
- deployment lifecycle and browser logs;
- managed databases/services;
- terminals and ordinary day-to-day runtime UI;
- Coolify-native PostgreSQL logical backup scheduling where selected by ADR.

Host hardening/firewall ownership must not silently migrate into Coolify.

### 4.3. Delivery

**GitHub Actions** owns the reference CI flow:

```text
source
→ tests
→ application migration preflight
→ image build
→ GHCR
→ immutable digest verification
→ Coolify deployment
```

**GHCR** owns built container artifacts and immutable image identity.

Automatic deployment rollback is **container-image-only**. It does not imply database schema/data rollback or reversal of external side effects.

### 4.4. Secrets

**SOPS + age** own infrastructure/recovery secret files and their encrypted-at-rest workflow.

The production age private identity belongs on the normal operator workstation. It is not copied to the VPS by default.

SOPS + age is not a Vault replacement. Ordinary **application runtime secrets** remain primarily inside **Coolify Environment Variables** / the selected application-platform boundary.

### 4.5. Backup and recovery

**restic + off-site storage** own the host/Coolify filesystem recovery-material layer.

Database-aware recovery remains logical and platform/application specific:

- Coolify instance database recovery is separate from filesystem recovery;
- Coolify-managed PostgreSQL application data uses Coolify-native logical backup ownership;
- raw Docker/PostgreSQL data directories are not treated as portable backups;
- disaster recovery composes these sources rather than pretending one archive owns everything.

A same-VPS copy or provider snapshot may be useful, but it does not replace encrypted off-site recovery evidence.

---

## 5. Core profile vs optional capabilities

The **core Quick Start** must not require Tailscale, Grafana/Alloy, error tracking, pgAdmin, shell customization, or a second VPS.

### Core platform

Required for the normal product path:

- supported Ubuntu VPS;
- Ansible host automation;
- verified non-root administrative access;
- UFW + unattended security updates;
- Docker;
- Coolify;
- verification/audit;
- reference CI/CD integration when the user chooses GitHub/GHCR delivery.

### Recovery profile

Required before making a **recovery-complete** claim, but it may be configured after the initial platform is usable:

- SOPS + age recovery secrets;
- managed off-site S3-compatible storage;
- restic repository/snapshots/retention;
- Coolify/PostgreSQL logical backup inputs;
- tested restore and lost-VPS procedure.

### Optional modules

These are valuable but have **zero dependency from core acceptance criteria**:

- **Tailscale** administrative/private networking;
- **Professional observability** such as retained logs through **Grafana Alloy** + Grafana Cloud;
- application error tracking (for example GlitchTip/Sentry-like services);
- pgAdmin or other database administration UIs;
- author shell/profile UX;
- richer host/container metrics;
- provider-specific snapshot/DNS conveniences.

Optional modules may have their own safety/evidence contracts, but must not silently contaminate the default installation path.

---

## 6. Supported operator model

### Public command surface

The project should expose a small stable lifecycle:

```text
make setup       # prepare controller + persistent project state
make apply       # apply/resume the host baseline
make secure      # access-critical SSH hardening after explicit proofs
make platform    # install/verify the application platform
make verify      # read-only verification
```

Operational helpers such as `make backup`, `make recover`, `make update`, and bounded diagnostics may exist around that lifecycle.

Internal validators/tests are not automatically public compatibility promises. They belong behind maintainer/developer help tiers.

### State ownership

The Git checkout is disposable product source. Installation state belongs outside it, normally under:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/solo-vps/
```

Host runtime state remains in normal service locations such as `/etc` and `/data/coolify`.

A source update must not silently overwrite installation-specific configuration or credentials.

---

## 7. Security boundaries

### Administrative access

- preserve a working provider/recovery path before access-critical mutation;
- use a normal human workstation SSH public key distinct from same-VPS automation identity;
- verify fresh non-root admin login and passwordless sudo before disabling older access paths;
- root login should not remain the normal administrative interface after hardening.

### Network exposure

Expected public host ingress is intentionally small, normally:

```text
22/tcp
80/tcp
443/tcp
```

Coolify raw management/realtime ports must not become public merely to make automation convenient.

Docker-published ports are a separate exposure surface and must be audited explicitly; UFW alone is not assumed to contain arbitrary Docker publications.

### Secret handling

Never commit or print:

- private SSH keys;
- age private identities;
- S3 credentials;
- restic passwords;
- Coolify API tokens;
- application secrets.

Public examples also avoid operator-specific infrastructure identifiers even when they are not cryptographic secrets.

---

## 8. Deployment and migration contract

Solo VPS does not own application schema migrations.

Applications that mutate persistent state must provide an application-owned preflight/compatibility policy. Recommended database evolution is backward-compatible **expand/contract**:

```text
expand schema
→ old + new application versions remain compatible
→ deploy new image
→ observe
→ retire old rollback target
→ contract/remove obsolete schema later
```

An irreversible schema/data operation requires fresh backup evidence plus an exercised restore or explicit forward-fix recovery plan before deployment.

A successful container rollback must never be documented as a successful database rollback.

---

## 9. Backup and disaster-recovery contract

A meaningful recovery story must answer:

1. Where are infrastructure/recovery secrets stored off the VPS?
2. Where is filesystem recovery material stored off the VPS?
3. How is the Coolify instance database recovered?
4. How is application database data recovered?
5. Which immutable application image/source revision is redeployed?
6. How is the restored platform verified and audited?

A release-quality claim requires a clean replacement-host exercise, not only source/unit tests.

The product itself still runs on one VPS. A temporary validation/replacement VPS is test/recovery infrastructure, not a permanent second node in the product topology.

---

## 10. Observability philosophy

Daily operations are browser-first through GitHub Actions and Coolify. Local CLI status/log commands are bounded fallback diagnostics.

Retained logs/metrics may use managed external services, but observability must not become the largest stateful workload on the VPS.

If **Professional observability** is enabled, the accepted direction is a non-root host collector with a narrowly constrained Docker-data boundary; it must not require exposing the Docker daemon publicly or adding a local Loki/Grafana stack by default.

Observability remains optional to the core Quick Start even when an implementation is integration-proven.

---

## 11. Documentation governance

Document roles are intentionally separated:

- [`README.md`](README.md) — **canonical current user contract**, supported happy path, current blockers;
- [`docs/`](docs/index.md) — user operations and reference documentation;
- [`docs/architecture.md`](docs/architecture.md) + ADRs — current design/ownership truth;
- [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md) — concise north-star product/architecture boundary;
- [`ROADMAP.md`](ROADMAP.md) — short current development plan, blockers, validation level, next action;
- [`CHANGELOG.md`](CHANGELOG.md) + Git history/releases — historical source changes;
- private/sanitized evidence artifacts — installation-specific validation details.

The Passport must not duplicate a changing milestone checklist. The ROADMAP must not become a lab notebook or eternal changelog.

### First-run documentation contract

The detailed authoring policy for contributors and AI agents is [`DOCUMENTATION_GUIDE.md`](DOCUMENTATION_GUIDE.md). The base runbook consists of two consecutive pages: VPS/Coolify, then application/CI/CD/ENV/logs. Long instructions are acceptable when each action is simple and complete; mandatory detours and chat-only missing steps are not.

The canonical Quick Start must be one continuous, numbered journey from `apt-get update` on a fresh VPS to a working HTTPS application. It includes host setup, first Coolify registration and the exact onboarding choice, the existing localhost server, the dashboard domain, a reference GitHub application, Actions/GHCR delivery, the first deployment, a subsequent automatic deployment, basic runtime ENV/secrets handling and live logs. A reader must not have to discover the next required page or infer a missing UI action.

Each step states where to act, gives the necessary copyable command or exact UI action, and briefly explains its purpose and visible result. Required inputs are introduced before use. Commands should work in sequence on the supported baseline; defects belong in automation fixes rather than extra manual workarounds in the main path.

Second-run idempotency, repeated verify/audit commands, fault injection and release-evidence collection belong in maintainer acceptance procedures. Routine verification should run inside the public lifecycle commands wherever implemented; users should see the result without repeating those checks. Keep only essential access/data safety steps in the main path, with troubleshooting and exceptional recovery in separate task pages.

The end of Quick Start links to optional advanced runtime configuration/secrets, external uptime alerts, restic/off-site storage, PostgreSQL backups and retained logs. Basic application ENV and live logs are part of the initial result; optional recovery and observability services are not prerequisites. Simplicity is an implementation and documentation requirement, not a promise that unsupported environments or external services cannot fail. Production and recovery claims must retain their stated validation scope.

---

## 12. Validation and release quality

Evidence levels are defined in [`ROADMAP.md`](ROADMAP.md) and range from static/local evidence through integration and clean-VPS evidence.

Before a public alpha is treated as a credible single-VPS platform, the project should have at minimum:

- bounded source CI and real hosted repository evidence;
- one complete fresh Ubuntu 24.04 user replay;
- second-run idempotency for host automation;
- external off-site backup plus restore evidence;
- PostgreSQL logical restore evidence for a stateful example/fixture;
- tested lost-VPS recovery sequence;
- tested Coolify upgrade/recovery sequence;
- one independent external uptime/alert path;
- versioned release metadata and a private security reporting channel;
- documentation reviewed from the perspective of a first-time user.

A large number of green source-contract tests is not a substitute for these runtime proofs.

---

## 13. Technology-change rule

Before adding a new technology, answer:

1. What concrete single-VPS problem does it solve?
2. Can the selected stack already solve it?
3. What new credentials, ports, state, upgrades, backups, and failure modes does it add?
4. Is it required for the core path or truly optional?
5. How is it diagnosed and recovered?

If the answer is weak, do not add the technology.

Long-lived responsibility/security/storage/deployment decisions should be captured in an ADR. Small reversible implementation details do not need ADR ceremony.

---

## 14. Source hierarchy for future engineering work

When sources conflict, use:

1. current explicit maintainer instruction;
2. accepted ADR / explicit owner decision;
3. this Passport for product intent and architecture boundaries;
4. `README.md` for current supported user contract;
5. `ROADMAP.md` for current development state;
6. repository implementation as factual implementation evidence;
7. `legacy/` only as historical requirements/research.

Implementation facts must not be invented to satisfy an aspirational Passport sentence.

---

## 15. License

The project license is **Apache-2.0**.

Use SPDX identifier:

```text
SPDX-License-Identifier: Apache-2.0
```

The canonical license text is [`LICENSE`](LICENSE); rationale is in [`docs/license-choice.md`](docs/license-choice.md).
