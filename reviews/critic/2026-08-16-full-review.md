# Solo VPS — FULL adversarial project review

**Дата:** 2026-08-16  
**Режим:** FULL (`.agents/skills/solo-vps-project-critic/SKILL.md`)  
**Материал:** переданный source archive `solo-vps.zip`  
**Revision hint:** archive comment `06dd7e37d8d1f7cb62f01a2521fcce2dbf47a2d9`  
**Git metadata:** отсутствует в архиве; revision hint нельзя независимо подтвердить через `git log`/`git status`  
**Reviewer stance:** независимый DevOps/platform/product critic; проектные файлы не изменялись, кроме этого нового review.

---

## 1. Executive verdict

### Вердикт: **REJECT для production / CONDITIONAL PASS как PRE-ALPHA engineering prototype**

README честно говорит, что проект PRE-ALPHA и не production-ready. Это правильная оговорка. Но Passport и сама продуктовая архитектура обещают гораздо более сильный результат: один VPS, production-ready baseline, CI/CD, backups, recovery и минимальный DevOps overhead. На текущем состоянии это обещание не выполняется.

Главная проблема проекта не в качестве отдельных Ansible-задач. Во многих местах они аккуратнее среднего: staged SSH hardening, fail-closed guards, persistent state вне checkout, immutable image handoff, checksum-pinned tooling, SOPS/age boundary, read-only verify/audit. Проблема — **приоритет и доказательства**. Проект построил большую систему contract validators, documentation drift tests и observability tooling до того, как доказал базовую вещь: что потерянный единственный VPS можно восстановить, что failed deployment автоматически возвращает известное хорошее приложение, что onboarding не требует скрытой ручной операции с SSH-ключом и что репозиторий сам гоняет свои release gates в CI.

Если бы этот репозиторий сегодня был представлен как «production VPS platform for solo developers», я бы не доверил ему единственную копию важных данных и не рекомендовал бы новичку использовать его на основном VPS.

**Короткий ответ на north-star вопросы:**

- **Доверил бы свой единственный production VPS?** Нет, пока нет реального off-site restore + lost-VPS DR proof и deployment rollback.
- **Рекомендовал бы другому solo developer?** Только для disposable/test VPS с явным пониманием PRE-ALPHA статуса.
- **Может ли человек без DevOps пройти setup без импровизации?** Не полностью: стандартный same-VPS flow содержит скрытую ручную доставку workstation SSH key.
- **30–60 минут realistic?** Не доказано и по текущему количеству стадий/контекстов выглядит нереалистично для нового пользователя.
- **Главный UX bottleneck:** identity/workspace transitions + слишком большая командная поверхность.
- **Главный production risk:** данные и desired application state имеют слабее доказанный recovery path, чем host hardening.
- **Главный maintenance burden:** 145 показываемых Make targets, десятки source-contract validators и очень большой ROADMAP/Passport, которые требуют синхронизации быстрее, чем появляется runtime evidence.

---

## 2. Scope и метод

Изучены как первичные источники:

- `README.md`
- `PROJECT_PASSPORT.md`
- `ROADMAP.md`
- `SECURITY.md`
- `CHANGELOG.md`
- весь `docs/`, включая ADR, operations, testing, upgrades, backup/database/release/security runbooks
- `Makefile`
- `ansible/` roles/playbooks/defaults/templates
- `scripts/` и Windows helpers
- `tests/`
- sample app и GitHub Actions template
- `.github/dependabot.yml`
- critic skill, указанный пользователем

Repo-wide static pass охватил 227 executable/config/source files вне `legacy/` и `.agents/` (`*.py`, `*.sh`, `*.ps1`, `*.yml`, `*.yaml`, `*.j2`, `Makefile`). Отдельно глубоко проверены access/hardening, Docker, Coolify install/deploy, CI transport, secrets, backup/database, verification/audit, observability и release/upgrade codepaths.

### Проверки, выполненные в review environment

- Python source compilation (`compileall`) — PASS.
- Bash syntax (`bash -n`) — PASS.
- Поиск `shell=True`, `os.system`, pipe-to-shell installers, `chmod 777`, Ansible `shell/raw` — явных опасных runtime usage в новой реализации не найдено.
- `make test-onboarding-contract` — PASS, 12 tests.
- `make test-coolify-deploy-api` — PASS, 14 tests.
- `make test-backup-policy` — PASS, 7 tests.
- `make test-database-backup-contract` — PASS, 8 tests.
- `make test-observability-runtime` — PASS, 12 tests, ~29 s.
- `make qa-static` — **NOT RUN**: archive environment не содержит prepared M20 QA toolchain; target корректно просит `make qa-tools`.
- Полный `make validate` запускался повторно, но не завершился внутри доступного execution window; остановка произошла после ряда PASS checks, в районе Coolify contracts. Это **не трактуется как test failure**, но является UX/CI сигналом: локальный aggregate gate тяжёлый, а hosted repo CI отсутствует.
- Полный `unittest discover -s tests` также был ограничен execution window; отдельный `test_observability_log_drain` suite прошёл 17 tests примерно за 38.6 s, что объясняет часть aggregate latency.

### Repo size / maintenance surface

- `Makefile`: 149 parsed targets; `make help` показывает **145 command entries**.
- `tests/`: 37 `test_*.py` modules.
- `scripts/`: 32 `validate_*.py` validators.
- `PROJECT_PASSPORT.md`: 2,781 lines.
- `ROADMAP.md`: 3,353 lines.
- `docs/clean-vps-test.md`: 507 lines.
- `docs/command-reference.md`: 448 lines.

Количество само по себе не является дефектом. Оно становится дефектом, когда maintenance surface растёт быстрее runtime proof и усложняет путь пользователя.

---

## 3. Release blockers

До любого production/stable claim я считаю обязательными следующие blockers:

1. **CRIT-001:** реальный encrypted off-site backup + database backup + full restore + lost-VPS DR exercise.
2. **CRIT-002:** deployment rollback после failed/unhealthy rollout, а не только exception.
3. **CRIT-003:** убрать скрытую ручную workstation-key операцию из default onboarding.
4. **CRIT-004:** hosted repository CI + автоматизированный disposable clean-VPS path хотя бы для критических gates.
5. **CRIT-005:** не включать текущий Docker API observability proxy как production default, пока container inspect confidentiality не закрыта и не покрыта negative tests.
6. **CRIT-011:** определить и доказать lifecycle/upgrade path для Coolify, а не только first-install pin.
7. **CRIT-015:** добавить failure detection вне самого VPS (минимум external uptime/alert path), иначе смерть единственного host может остаться незамеченной.

---

# 4. Product promise stress test

| # | Required scenario | Verdict | Evidence-based assessment |
|---:|---|---|---|
| 1 | Obtain Solo VPS | **PASS** | Repository is a self-contained automation project with an explicit fresh-host entry path. |
| 2 | Follow Quick Start with no prior knowledge | **PARTIAL** | README is unusually candid and ordered, but the workstation SSH key handoff is not a complete first-class step and the command surface is large. |
| 3 | Configure a fresh VPS | **PASS** | `setup/init/prepare-access/bootstrap/verify/audit` cover the host baseline and staged access model. Full public-cloud/provider replay was not performed in this review. |
| 4 | Reach a secure app platform with a few primary commands | **FAIL** | The golden path requires roughly twenty project commands plus OS preparation, context switches, SSH proof, hardening gates, a tunnel, and browser registration. |
| 5 | Finish unavoidable GitHub/Coolify/Grafana UI work | **PARTIAL** | Coolify bootstrap/registration and external service setup are documented, but remain multi-context manual work; Grafana/observability is not a completed production path. |
| 6 | Deploy a sample app via `git push` | **PARTIAL** | A consumer GitHub Actions template and Coolify deploy helper exist, but the deployment helper lacks automatic rollback of desired state on a bad release. |
| 7 | See CI logs in GitHub | **PASS / repository FAIL** | Consumer-app CI is designed for GitHub Actions visibility; this Solo VPS repository itself has no hosted workflow proving its own validation surface. |
| 8 | See deployment/live logs in Coolify | **PASS / PARTIAL** | Coolify is the intended deployment/live-logs UI and contracts exist; the full fresh-host external replay remains unproven. |
| 9 | See historical logs | **FAIL / NOT TESTED** | The Alloy/Grafana direction exists, but the production runtime path and external evidence are not yet complete. |
| 10 | Observe host/app health | **PARTIAL** | Host verification and health checks are strong; durable user-facing external monitoring/alerting is not yet a complete production capability. |
| 11 | Receive a useful failure signal | **FAIL** | No proven out-of-band alert path covers the defining single-VPS failure mode: the host disappearing. |
| 12 | Recover from a bad app release | **FAIL** | The deploy helper fails closed but leaves the newly patched bad image as desired state and does not restore the previous image automatically. |
| 13 | Recover from VPS loss | **FAIL** | Live off-site backups, restore execution, and lost-VPS rebuild/restore/redeploy verification are explicitly unfinished. |
| 14 | Upgrade Solo VPS later | **PARTIAL** | Upgrade documentation and version pins exist, but lifecycle support windows and tested Coolify/host upgrade paths are incomplete. |

**Stress-test summary:** 3 clear PASS outcomes, 5 PARTIAL/mixed outcomes, and 6 FAIL/NOT TESTED outcomes. The project has a credible engineering base, but the product promise is not yet demonstrated end-to-end.

# 5. Cold-start / user journey reconstruction

## Current documented path до установленного Coolify

README требует примерно следующий путь:

```text
apt-get update
apt-get install -y make [и git при clone]
cd solo-vps
make setup
make validate
make init
make paths
edit config.yml
make use-bootstrap SSH_USER=<provider-user>
make prepare-access
make doctor
make bootstrap
make verify
make audit
make use-admin
make doctor
external workstation SSH test
[hidden: maybe generate workstation key]
[hidden: maybe manually add workstation pubkey to managed admin]
SSH_HARDENING_CONFIRM=... make ssh-harden
make verify-ssh
ssh <admin>@<server>
cd ~/solo-vps
make doctor
make coolify-readiness
make coolify
make verify-coolify
SSH tunnel to UI
browser first-registration
optional Sentinel UI disable
then first-app walkthrough
```

До первого application deploy это уже:

- ~20 project commands;
- несколько shell/SSH commands;
- минимум один config edit;
- root workspace → managed-admin workspace → external workstation контексты;
- provider recovery prerequisite;
- browser registration/UI steps;
- возможная недокументированная project-commandом доставка workstation public key;
- затем отдельный app/CI setup.

Это не «несколько primary commands». Это internal implementation workflow, вынесенный пользователю.

### Verdict по 30–60 minute north star

**Не доказано.** Нельзя честно обещать 30–60 минут до production-ready state, пока:

- clean V4 replay не завершён;
- backup/restore/DR не существует end-to-end;
- onboarding требует context switches;
- aggregate `make validate` сам по себе тяжёлый;
- Coolify first registration и app UI steps остаются manual;
- CI secrets/SSH transport добавляются отдельно.

Для опытного maintainer, который уже знает проект и provider console, host+Coolify bring-up может уложиться быстро. Для нового пользователя это другой эксперимент, которого evidence пока нет.

### Target UX, который проекту стоит восстановить

```text
get repo
make setup
make init
edit one config
make doctor
make bootstrap        # host + safe admin + SSH hardening + Coolify, staged internally
make verify

# optional later
make enable-backups
make enable-ci
make enable-observability
```

Внутренние `use-bootstrap`, `prepare-access`, `admin-handoff`, `coolify-readiness` и отдельные validators могут существовать, но не должны быть mainline UX unless failure/recovery требует их явно.

---

# 5.1 Time-to-value verdict

**30–60 minute target: NOT VALIDATED.** The repository does not contain a measured clean-VPS run proving this target, and the current flow contains enough context switching that claiming it would be misleading.

- **Automated work:** local dependency/bootstrap helpers, config rendering, access preparation, Ansible host baseline, verification/audit, Coolify readiness/install helpers, contract validation.
- **Manual work:** initial OS preparation, project config edit, independent workstation SSH key preparation/install, independent SSH proof, explicit SSH-hardening confirmation, browser registration, GitHub/Coolify credentials, optional Grafana/backup provider work.
- **Waiting/external work:** package downloads, Docker/Coolify install/start, DNS/TLS or provider-side prerequisites when used, GitHub Actions runner/deploy feedback.
- **High-friction steps:** same-VPS automation identity versus human workstation identity; repeated root/admin/workstation/browser context switches; large `make validate` gate; irreversible SSH-hardening checkpoint; SSH-tunnel-based Coolify API transport; separate unfinished backup and observability tracks.

# 5.2 Daily developer experience

| Daily task | Current UX | Verdict |
|---|---|---|
| `git push` an app change | Conventional GitHub flow | **GOOD** |
| See CI status/logs | GitHub Actions for consumer app templates | **GOOD**, but not self-proven for this repo |
| See deployment state | Coolify + deploy helper | **GOOD/PARTIAL** |
| See live logs | Coolify | **GOOD** |
| See historical logs | Planned Alloy/Grafana path | **NOT READY** |
| See runtime application errors | App-specific; no platform-level error-tracking contract | **OPTIONAL / NOT IMPLEMENTED** |
| Roll back a bad release | No automatic desired-state rollback | **BAD** |
| Edit environment variables | Coolify UI/API ownership model | **GOOD** |
| Restart/redeploy | Coolify | **GOOD** |
| See metrics/health | Strong host verification; broader external monitoring incomplete | **PARTIAL** |
| See backup freshness/status | Backup execution/schedule/restore not complete | **BAD** |

# 6. Scorecard

Scores use 1 = weak/unproven, 3 = workable with material gaps, 5 = production-grade and evidenced.

| Axis | Score / 5 | Rationale |
|---|---:|---|
| Quick Start / onboarding | 2 | Ordered and honest, but long and missing a first-class human-workstation key handoff. |
| CLI / Make UX | 2 | Discoverable but too broad: ~145 help-visible targets create a framework-like surface. |
| Configuration UX | 4 | Clear defaults, rendering, validation, and secret separation. |
| Dependency / bootstrap UX | 4 | Good helpers and readiness checks; external/environment assumptions still exist. |
| Architecture simplicity | 3 | Sensible base stack, but bespoke contracts/orchestration have accumulated around it. |
| Security | 3 | Strong SSH/secrets/fail-closed posture; observability Docker API boundary and reporting path need work. |
| CI/CD | 2 | Consumer CI exists; repository CI and clean-host proof do not. |
| Deployment correctness | 2 | Immutable image handling is good, but failed deployments do not restore desired state. |
| Rollback / recovery | 1 | Application rollback and VPS-level recovery are not production-complete. |
| Logging | 2 | Coolify live logs are usable; historical log path is unfinished. |
| Metrics / alerting | 1 | Runtime direction exists; out-of-band production alerting is not demonstrated. |
| Error tracking | 1 | No explicit platform error-tracking capability; acceptable only if deliberately app-owned. |
| Backup / restore | 1 | Policy/contracts exist, live execution and restore proof do not. |
| Upgradeability | 2 | Documentation exists, but supported/tested lifecycle is incomplete. |
| Documentation | 3 | Substantial and candid, but oversized and partly duplicated/drift-prone. |
| Testing / evidence | 2 | Many static/contract tests, little hosted or disposable-host runtime evidence. |
| Public repo hygiene | 4 | Clear security/change docs and no obvious embedded secrets in reviewed source; revision provenance is weaker in the supplied archive. |
| Daily operations UI / UX | 3 | Coolify gives a strong center of gravity, but rollback, backups, historical logs, and alerts remain gaps. |

**Total: 42 / 90 = 2.33 / 5.**

# 7. Findings — P1

### CRIT-001 — [P1] Backup/restore/DR отсутствуют как реальная система

**Area:** Backup, database, disaster recovery, product promise  
**Evidence:**

- `README.md:16` — full fresh-VPS-to-restore path not validated.
- `docs/backups-restic.md:11` — current slice explicitly does not initialize repo, schedule backups, run backup, prune, or claim protection.
- `docs/backups-restic.md:226` — retention is policy only; no `forget`, `prune`, schedule.
- `docs/backups-restic.md:263-273` — live repository, backup execution, freshness and restore remain future work.
- `ROADMAP.md:1619-1715` — M14 BLOCKED; off-site repo/init/schedule/snapshot/restore absent.
- `ROADMAP.md:1751-1801` — M15 BLOCKED; real Coolify DB backup/restore not run.
- `ROADMAP.md:1834-1883` — M16 BLOCKED; lost-VPS restore not exercised.

**Problem:** проект называется production VPS platform, но data recovery plane пока состоит из pinned restic binary, credential schema и policy docs. Это не backup system.

**User impact:** потеря единственного VPS, ошибочное удаление volume/database или corruption могут превратить «reproducible platform» в полностью невосстанавливаемую установку.

**Why this matters:** в single-VPS архитектуре backup/restore — не optional polish. Это единственная реальная HA стратегия. Проект может честно позволять «skip backups», но не может считать platform production-complete без них.

**Recommendation:** остановить новые P1 feature slices и завершить один минимальный recovery vertical slice:

```text
managed S3-compatible bucket
→ restic repo init/adopt
→ scheduled backup
→ freshness check
→ retention
→ Coolify PostgreSQL logical backup to off-site
→ new disposable VPS
→ restore control-plane/application state
→ restore DB
→ redeploy immutable app
→ verify
```

Не нужно делать generic backup framework. Нужен **один работающий, повторяемый recovery story**.

**Acceptance criteria:**

- fresh external bucket can be configured without credentials in Git;
- first backup and scheduled backup produce off-site snapshots;
- stale/missing snapshot is detected;
- retention executes with dry-run/review semantics before destructive prune;
- real PostgreSQL logical backup is restored into disposable DB and application-relevant data verified;
- documented `old VPS lost -> new VPS -> bootstrap -> restore -> redeploy -> verify` is executed end-to-end on clean Ubuntu 24.04;
- recovery inputs are enumerated and independently recoverable from workstation/provider storage;
- evidence is machine-checkable where possible and public-safe.

**Impact:** High  
**Effort:** High  
**Confidence:** High

---

### CRIT-002 — [P1] Failed deployment не откатывает desired image

**Area:** CI/CD, Coolify deployment correctness, rollback  
**Evidence:**

- `scripts/coolify_deploy_api.py:242-251` reads current state, then PATCHes new image and starts deployment.
- `scripts/coolify_deploy_api.py:271-293` raises on failed deployment, unhealthy app or timeout.
- `scripts/coolify_deploy_api.py:301-302` only reports `previous_image_*` **after success**.
- Нет codepath, который PATCH-ит previous image обратно и запускает rollback.
- `tests/test_coolify_deploy_api.py:192-223` asserts exceptions for failed/unhealthy states, but does not assert restoration of previous desired state.

**Problem:** helper является fail-closed только в смысле «CI job becomes red». Он **не является production rollback**. Desired configuration already points at the failed digest.

**User impact:** старый healthy container может временно остаться доступным благодаря behavior Coolify/rolling update, но следующий restart/redeploy/recovery может снова выбрать плохой digest. Оператор получает красный job и ручную incident procedure именно в момент, когда automation должна снижать риск.

**Why this matters:** immutable digest без rollback — только половина deployment safety. Single-VPS deployment должен иметь чрезвычайно простую «known-good image» story.

**Recommendation:** реализовать explicit application-state transaction:

1. capture previous immutable image name/tag;
2. PATCH candidate;
3. deploy + wait terminal state + health;
4. on any failure after PATCH, PATCH previous immutable state back;
5. start/redeploy previous version;
6. wait healthy;
7. return a distinct outcome: `DEPLOY_FAILED_ROLLBACK_OK` or `DEPLOY_FAILED_ROLLBACK_FAILED`;
8. print exact safe recovery command if automatic rollback fails.

Database migrations must be treated separately: do not claim rollback-safe deploy for irreversible migrations unless app owns compatible migration strategy.

**Acceptance criteria:**

- unit tests prove PATCH candidate → failed deploy → PATCH previous → start previous → healthy;
- unhealthy-after-finished path also rolls back;
- timeout path rolls back;
- rollback failure produces non-zero exit and explicit previous/candidate identifiers without leaking token;
- current production image is never mutable tag;
- CI distinguishes build/publish failure (no runtime mutation) from rollout failure and rollback failure.

**Impact:** High  
**Effort:** Low  
**Confidence:** High

---

### CRIT-003 — [P1] Default same-VPS onboarding имеет скрытый workstation SSH-key handoff

**Area:** Quick Start, SSH access, lockout safety  
**Evidence:**

- `README.md:95` — `make setup` creates/reuses default key on the machine where it runs.
- `README.md:110` — default `admin.ssh_public_key_file` points to that key.
- `README.md:121` — same-VPS mode authorizes generated controller key for root path.
- `README.md:146` — before hardening user must prove real login from normal workstation.
- `docs/clean-vps-test.md:291` — explicitly admits VPS-created automation key is not workstation proof because private half never left server.
- `docs/clean-vps-test.md:301` — if login fails, user must “add the workstation's public key to the managed admin”, but no canonical Solo VPS command is provided.

**Problem:** standard root-first flow creates the wrong identity for the later human-login proof. Internal automation works, but the user’s real administration key may never have been installed.

**User impact:** novice reaches the most security-sensitive point of setup, discovers external admin login fails, and is told to perform an ad-hoc authorized_keys operation while keeping root/provider session alive.

**Why this matters:** hidden manual work in SSH hardening is exactly the class of failure the product claims to eliminate.

**Recommendation:** separate identities explicitly:

- `controller automation key` for same-VPS loopback Ansible;
- `human admin public key` supplied from workstation from the beginning.

Best UX: config should accept/prompt for a public key value or a safe copy helper should read workstation public key and install it through the bootstrap session. Do not require users to reason about private-key locality mid-flow.

**Acceptance criteria:**

- following only Quick Start on a fresh VPS results in a working external workstation admin login without undocumented `authorized_keys` editing;
- same-VPS automation still works with a separate key;
- `doctor` can report `automation_admin_access=PASS` and `human_admin_key=CONFIGURED`, but must not falsely claim external reachability until tested;
- hardening refuses to continue without explicit external-login/recovery proof;
- clean test demonstrates root disabled after hardening and workstation admin login succeeds.

**Impact:** High  
**Effort:** Low  
**Confidence:** High

---

### CRIT-004 — [P1] Репозиторий не проверяет сам себя в hosted CI, disposable clean-VPS automation остаётся blocked

**Area:** CI, release engineering, evidence  
**Evidence:**

- `.github/` содержит только `dependabot.yml`; `.github/workflows/` отсутствует.
- GitHub Actions YAML в `templates/` — consumer/app template, а не CI самого Solo VPS.
- `ROADMAP.md:2007-2047` — M20 BLOCKED on disposable-target integration.
- `ROADMAP.md:3253` — v1 checklist: “CI repository checks exist” unchecked.
- `ROADMAP.md:3303` — V4 clean replay pending.
- `make validate` — большой локальный aggregate gate; в review environment повторно не завершился в execution window.

**Problem:** проект имеет множество validators, linters и tests, но они не являются обязательным evidence gate на каждом PR/revision в самом public repository.

**User impact:** regression может попасть в main/archive даже при наличии теста, потому что никто автоматически не гарантирует, что этот тест был запущен. Maintainer-specific V3 narratives в ROADMAP заменяют reproducible public evidence.

**Why this matters:** infrastructure automation особенно зависит от repeatable CI. Текст “PASS on maintainer VPS” полезен как integration evidence, но не заменяет public CI.

**Recommendation:** сначала добавить очень маленький hosted CI:

```text
job 1: fast source gate (<5–10 min target)
  python compile
  YAML parse
  selected validators/unit tests
  pinned yamllint/ansible syntax/ansible-lint

job 2: nightly/manual disposable Ubuntu target
  doctor -> bootstrap -> verify -> audit
  critical idempotency rerun

job 3: periodic release-candidate clean replay
  SSH hardening + Coolify + sample app
```

Не нужно сразу строить сложный cloud test lab. Даже self-hosted disposable runner/provider API later is better than none.

**Acceptance criteria:**

- public workflow runs on PR and main;
- required status check covers fast gate;
- no test depends on maintainer-local paths/state;
- clean/disposable integration is automated on a documented cadence/manual dispatch;
- result artifacts preserve sanitized evidence;
- a release cannot be cut when CI gate is red/missing.

**Impact:** High  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-005 — [P1] M24 Docker API proxy может раскрывать container environment secrets

**Area:** Security, observability, Docker boundary  
**Repository evidence:**

**Evidence:** Repository observability role configuration plus official docker-socket-proxy and Docker API/CLI documentation; exact secret-read exploit was not executed, so the confidentiality conclusion is explicitly marked as inference.

- `ansible/roles/observability/defaults/main.yml:37-46` — Alloy uses `tcp://127.0.0.1:2375`, proxy pinned and loopback-bound.
- `ansible/roles/observability/tasks/install-runtime.yml:180-213` — proxy created `--privileged --read-only`, with `CONTAINERS=1`, `NETWORKS=1`, `POST=0`, Docker socket mounted read-only, TCP published on loopback.
- `ansible/roles/observability/tasks/verify-runtime.yml:90-115` — tests `/containers/json` allowed, `/networks` allowed, `/info` denied.
- `verify-runtime.yml:238` correctly labels scope as “coarse CONTAINERS + NETWORKS API read boundary; high-trust”.
- Нет negative probe для `/containers/<id>/json` / Docker inspect and no auth boundary on localhost TCP.

**Official external evidence:**

- Tecnativa docker-socket-proxy says access variables normally map to URL prefixes and explicitly lists `CONTAINERS` as an API section that can expose information; it recommends revoking every unneeded section and limiting network access:  
  <https://github.com/Tecnativa/docker-socket-proxy/blob/master/README.md>
- Docker documentation warns that environment variables are stored in container configuration and can be inspected through the remote API:  
  <https://docs.docker.com/reference/cli/docker/>

**Inference:** because this proxy grants the whole `CONTAINERS` prefix and Docker’s inspect representation includes container configuration, an unprivileged process able to connect to host `127.0.0.1:2375` is likely able to read environment variables of containers. `POST=0` prevents mutation; it does **not** create confidentiality. This review environment has no real M24 Docker runtime, so the exact endpoint was not runtime-probed here. The repository should treat the absence of a negative inspect test as a blocker, not as proof of safety.

**Problem:** “read-only Docker API” sounds safer than it is. For production apps, read access can include credentials, database URLs, API tokens and other env configuration.

**User impact:** a host-local foothold that does not otherwise have Docker/root can potentially become a secrets disclosure incident.

**Why this matters:** observability is optional. It must not widen the host trust boundary more than the logs it is supposed to collect.

**Recommendation:** **do not promote this runtime to default** until one of these designs is proven:

1. a narrow Unix socket/path-filter proxy accessible only to Alloy service identity and exposing only exact required endpoints without inspect secrets; or
2. an alternative log source that does not require container API read access; or
3. a separately isolated network namespace + authenticated/identity-bound access plus endpoint-level ACL.

At minimum, add explicit negative tests for container inspect, exec, images, volumes, secrets, info and any endpoint that can expose environment/config. `--privileged` follows upstream proxy guidance for some AppArmor/SELinux contexts, so this review does not claim it is automatically removable; it does increase the need for strong containment.

**Acceptance criteria:**

- `GET /containers/<known-id>/json` cannot return secret-bearing environment/config to an unprivileged non-Alloy host process;
- only Alloy identity can reach the proxy endpoint, not every localhost process;
- exact required Docker endpoints are documented from Alloy behavior;
- denied endpoint regression tests exist;
- direct Docker socket remains unavailable to Alloy;
- threat model explicitly covers host-local unprivileged compromise.

**Impact:** High  
**Effort:** Medium  
**Confidence:** High

**Confidence note:** endpoint exposure is a strong source-backed inference; runtime exploit was not executed in this review environment.

---

# 8. Findings — P2

### CRIT-006 — [P2] Quick Start exposes too much internal orchestration

**Area:** Product UX, onboarding  
**Evidence:** README flow reconstructed above; `make help` exposes 145 commands.

**Problem:** users must understand bootstrap identity, admin identity, controller identity, handoff, state path, separate hardening phase, Coolify readiness phase and UI tunnel before they deploy an app.

**User impact:** high cognitive load, many failure points, difficult support/debugging. A user can follow commands mechanically without understanding which machine/key/workspace is currently authoritative.

**Why this matters:** The product promise is to remove DevOps burden for a solo operator; bespoke orchestration that duplicates platform behavior moves that burden into the project itself.

**Recommendation:** keep internal stages but wrap normal path into 3–5 primary commands. Make each stage resumable and print next action. Recovery docs can expose internals.

**Acceptance criteria:** Quick Start from repo to Coolify contains <= 8 intentional primary commands excluding source acquisition/SSH reconnect; one config edit; no manual key surgery; `make help` default highlights only primary lifecycle commands.

**Impact:** High  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-007 — [P2] `make help` — это internal API dump, а не пользовательский CLI

**Area:** Make/CLI UX  
**Evidence:** `make help` prints 148 lines / 145 command entries.

**Problem:** validator/test/internal helper targets смешаны с lifecycle commands. Пользователь видит `validate-observability-log-drain`, `test-public-product-hygiene`, confirmation guards и operational commands в одном списке.

**User impact:** продукт выглядит сложнее, чем он есть; сложнее понять supported path; internal target становится de facto public API, что увеличивает compatibility burden.

**Why this matters:** Every public command becomes a compatibility and support obligation, so a flat expert-facing surface directly increases maintenance cost and onboarding ambiguity.

**Recommendation:**

- `make help` — 10–15 primary commands;
- `make help-ops`, `make help-dev`, `make help-all`;
- internal validators prefix or undocumented implementation targets;
- one `make validate` instead of advertising every validator to ordinary user.

**Acceptance criteria:** first-time user can identify setup/doctor/bootstrap/verify/update/backup/recover from one screen; internal test targets remain discoverable separately.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-008 — [P2] Passport product promise и factual implementation расходятся

**Area:** Documentation truthfulness / architecture governance  
**Evidence:**

- `PROJECT_PASSPORT.md:191-215` presents sequence ending in a result checklist including SSH hardened, Tailscale, backups configured, Coolify installed.
- `README.md:135` says current `make bootstrap` stops at Docker and does not harden SSH/install Coolify.
- README explicitly says backups are incomplete/optional.
- Passport still carries Tailscale/default-profile language while current implementation defers it.

**Problem:** intended architecture is written like current product contract in several places. Evidence hierarchy becomes ambiguous.

**User impact:** contributor/AI can implement toward stale Passport text or assume a feature is part of default profile when README/code say otherwise.

**Why this matters:** For an operations project, documentation is part of the control plane: conflicting current-state narratives cause unsafe or wasted operator decisions.

**Recommendation:** split Passport into **north-star target** and **current supported contract**. Current contract should be generated/referenced from README/status, not duplicated narratively.

**Acceptance criteria:** no current-state checklist marks a feature complete/implicit unless code+evidence support it; aspirational sections are visibly labeled TARGET/FUTURE.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-009 — [P2] ROADMAP хранит слишком много исторической state machine и противоречивых статусов

**Area:** Engineering process, documentation maintainability  
**Evidence:**

- ROADMAP is 3,353 lines.
- top summary says current M24, host baseline integration PASS, etc.; old milestone sections still carry multiple `[IN_PROGRESS]` headings and stale “pending” narratives.
- `ROADMAP.md:3318` itself says aggregate `make validate` exceeded sandbox limit and QA runtime unavailable in that iteration, while older milestone blocks retain earlier PASS narratives.

**Problem:** ROADMAP одновременно служит plan, changelog, lab notebook, evidence ledger and AI handoff. Эти роли конфликтуют.

**User impact:** трудно ответить “что реально готово сейчас?” без чтения тысяч строк и интерпретации temporal context.

**Why this matters:** Evidence governance must answer “what is true now?” quickly; otherwise historical PASS notes can outweigh current blockers in human review.

**Recommendation:** оставить ROADMAP коротким: milestone, state, blocker, next action, current evidence link. Исторические transcripts/iterations вынести в `docs/history/` or release notes/evidence artifacts.

**Acceptance criteria:** current status can be read in <5 minutes; each milestone has one canonical state; historical statements do not выглядят current.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-010 — [P2] Contract-test investment превышает runtime-test investment

**Area:** Testing strategy, overengineering  
**Evidence:**

- 32 `validate_*.py` scripts + 37 unit modules.
- Many tests mutate copied source/docs strings and rerun validators, e.g. `tests/test_observability_log_drain.py` creates temp trees and invokes the validator once per negative textual mutation.
- That suite alone ran 17 tests in ~38.6 s in review environment.
- M20 disposable integration remains BLOCKED.
- Onboarding contract tests PASS even though the real user flow still has hidden workstation-key work.

**Problem:** project has become very good at proving that its own text/source patterns match expectations, while the most important production properties are still not executable tests.

**User impact:** large validation time and maintenance burden can create false confidence: “many green tests” != “fresh user can restore production after VPS loss”.

**Why this matters:** Test cost should correlate with runtime risk. Slow source-contract mutation tests consume validation budget without proving the fresh-host scenarios that dominate production risk.

**Recommendation:** classify tests:

```text
Tier A: semantic unit tests (keep)
Tier B: critical security/source invariants (keep small)
Tier C: doc wording/drift tests (reduce sharply)
Tier D: disposable runtime integration/restore (increase)
```

Do not write a negative string-mutation test for every sentence in ROADMAP. Prefer behavior.

**Acceptance criteria:** fast PR suite has an explicit time budget; doc contracts are limited to public invariants; clean host and recovery tests receive more engineering attention than documentation string tests.

**Impact:** High  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-011 — [P2] Docker/Coolify version lifecycle is not reproducible enough for a long-lived platform

**Area:** Dependency lifecycle, upgrade correctness  
**Repository evidence:**

**Evidence:** Repository Docker/Coolify version-management code and docs plus current official Coolify release/upgrade documentation.

- `ansible/roles/docker/defaults/main.yml:10-15` uses unversioned `docker-ce`, `docker-ce-cli`, `containerd.io`, plugins.
- Docker guard is only `solo_vps_docker_minimum_major_version: 24`; no tested maximum.
- `ansible/roles/docker/tasks/main.yml` installs `state: present` from current Docker apt repo candidate.
- `docs/upgrades.md` acknowledges existing hosts are not automatically advanced and package-specific recovery is required.
- Coolify is exact-pinned to `v4.1.2`, but Solo VPS upgrade is explicitly unsupported in current docs.

**Official external evidence:**

- On review date 2026-08-16, Coolify’s official releases page lists **v4.3.3** as latest, while project remains on v4.1.2:  
  <https://github.com/coollabsio/coolify/releases>
- Coolify provides documented upgrade methods and version-specific manual upgrade:  
  <https://coolify.io/docs/get-started/upgrade>

This does **not** mean v4.1.2 is insecure. It means Solo VPS is accumulating compatibility/lifecycle debt while upstream moves quickly (including API behavior changes in later releases).

**Problem:** fresh Docker hosts can resolve different package versions over time; existing hosts may remain old; Coolify is tightly pinned with no project-managed upgrade path.

**User impact:** Fresh installs made from the same Solo VPS release can diverge in Docker behavior, while an older installed host can drift in the opposite direction; upgrades become harder to predict and reproduce.

**Why this matters:** Infrastructure reproducibility is a core property of a rebuildable single VPS; unbounded package drift makes identical configuration produce materially different hosts over time.

**Recommendation:**

- define a **tested Docker major/minor support window**, not only minimum;
- fail/warn on untested future major;
- document how new tested versions graduate;
- for Coolify, maintain `current_supported` + tested upgrade path from previous supported version;
- run compatibility CI against at least current project pin and candidate next version before bump.

**Acceptance criteria:** two fresh installs from the same release cannot silently select an untested Docker major; Coolify upgrade has backup, preflight, execution, verification and recovery evidence.

**Impact:** High  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-012 — [P2] CI deployment transport is secure but overcomplicated for the product goal

**Area:** CI/CD architecture, simplification  
**Current decision:** GitHub-hosted runner uses dedicated restricted SSH identity and local port-forward to Coolify loopback API.

**Evidence:** Repository CI tunnel design and current official Coolify API authorization documentation.

**Problem:** this requires SSH key lifecycle, host fingerprint pinning, dedicated sshd Match rules, fixed tunnel ports, CI secrets and transport-specific tests. It is a lot of platform code to call an authenticated HTTP API.

**User impact:** Operators carry an extra SSH identity, host-key pin, tunnel configuration, CI secrets, and a bespoke transport failure mode in addition to Coolify’s own API authentication.

**Why this matters:** A transport layer should reduce risk relative to the platform capability it wraps; otherwise it creates more keys, secrets, failure modes, and recovery procedures than it removes.

**Official external evidence:** Coolify documents a normal HTTPS API base on the instance domain, scoped bearer token permissions (`read`, `write`, `deploy`) and optional API IP allowlisting:  
<https://coolify.io/docs/api-reference/authorization>

**Better alternative:** once the Coolify dashboard has a proper HTTPS domain (already a planned M22 item), evaluate direct HTTPS API deploy with narrowly scoped token. Do not expose raw `:8000`; expose the same authenticated web surface the product already needs for browser operation.

**Migration impact:** medium. Existing restricted SSH tunnel can remain supported during transition. A direct HTTPS path may reduce code/keys significantly, but GitHub-hosted runner IP allowlisting is operationally awkward; token scope/rate limits/TLS must be evaluated rather than assumed.

**Recommendation:** **REVISE**, not immediate remove. Prove whether HTTPS API is sufficiently safe and simpler; if yes, retire CI SSH transport from default.

**Acceptance criteria:** architecture decision compares threat model, token blast radius, network exposure, key rotation and operational steps; selected default has fewer moving parts without lowering security.

**Impact:** Medium  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-013 — [P2] Roadmap priority is inverted: observability before recovery

**Area:** Product prioritization / overengineering  
**Evidence:** ROADMAP current milestone/priority is M24 observability while M14/M15/M16 recovery remains BLOCKED and M20 integration testing remains BLOCKED.

**Problem:** historical logs are valuable, but a production single-VPS platform that cannot restore data has a more fundamental problem.

**User impact:** project spends complexity budget on Alloy, Grafana Cloud credentials, Docker API proxy and multiple observability contract suites while the user still cannot recover from the primary failure mode: VPS loss.

**Why this matters:** On a single VPS the irreversible risks are data loss and failed recovery, so optional observability depth should not outrank backup/restore and clean-host evidence.

**Recommendation:** freeze M24 after minimal safe diagnostic logging. Finish M14–M16 and CRIT-002 first. Then revisit observability with a smaller threat surface.

**Acceptance criteria:** no new observability feature becomes P1 priority while restore/DR release blockers remain open.

**Impact:** High  
**Effort:** Low  
**Confidence:** High

---

### CRIT-014 — [P2] Security reporting has no guaranteed private channel

**Area:** OSS security process  
**Evidence:** `SECURITY.md:33-35` says use GitHub private vulnerability reporting **if enabled**; archive cannot prove it is enabled; no security email is defined; fallback is a minimal public issue asking for private contact.

**Problem:** a reporter with a real lockout/secret-exposure vulnerability may have no confidential contact path.

**User impact:** delayed disclosure, accidental public hinting, or lost reports.

**Why this matters:** A guaranteed private disclosure route is baseline security hygiene for a public infrastructure repository and avoids forcing sensitive reports into public issue metadata.

**Recommendation:** before public release, enable GitHub Private Vulnerability Reporting and/or publish a dedicated security contact email/PGP/minisign policy. Keep current “do not put exploit details in issue” language.

**Acceptance criteria:** one guaranteed private channel is visible in `SECURITY.md` and tested by maintainers.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-015 — [P2] Нет доказанного внешнего detection/alert path для смерти единственного VPS

**Area:** Observability, uptime, operations  
**Evidence:** project has local `verify`, `audit`, `ops-status`, logs work and M24 Grafana direction, but no completed external uptime/availability alerting contract in current core path. M24 retained runtime itself is not yet integration-proven.

**Problem:** monitoring running on the same VPS cannot tell the user that the VPS is gone if there is no independent external check/notification.

**User impact:** outage may last until user manually notices. For solo developer this can be worse than missing rich metrics.

**Why this matters:** Same-host monitoring cannot report the host’s total disappearance; the defining failure mode therefore requires an out-of-band signal to be operationally useful.

**Recommendation:** before full metrics, add one cheap independent heartbeat/HTTP check against a chosen public app or Coolify health endpoint, with a tested notification path. Keep provider-neutral; allow UptimeRobot/Better Stack/Grafana synthetic/etc. as documented choices rather than building a server.

**Acceptance criteria:** shutting down the test VPS results in an external alert within a documented interval; recovery/false-positive behavior documented.

**Impact:** High  
**Effort:** Low  
**Confidence:** High

---

### CRIT-016 — [P2] App deployment contract не отделяет migration safety от container rollback

**Area:** CI/CD, databases  
**Evidence:** sample delivery focuses on immutable image, Coolify deploy status and health. M15 database ownership is Coolify-native backup; generic application migration/rollback semantics are not a first-class contract in deploy helper/docs.

**Problem:** even after CRIT-002 image rollback is added, an application deployment with irreversible schema migration may not be rollback-safe.

**User impact:** “rollback successful” can be false if old app binary cannot run against new schema.

**Why this matters:** Image rollback cannot reverse schema or data mutations, so deployment safety remains incomplete unless migration policy is explicitly separated and recoverable.

**Recommendation:** do not build a generic migration engine. Add an explicit boundary in app template/docs:

- Solo VPS rolls back container image only;
- app owns migrations;
- recommended strategy is backward-compatible expand/contract migration;
- irreversible migration requires backup/restore/recovery plan before deploy.

**Acceptance criteria:** deployment docs never imply database rollback from image rollback; sample CI provides a hook/stage for app-owned migration/preflight if used.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-017 — [P2] Source upgrade/release story пока слишком maintainer-centric

**Area:** Release process, upgrades  
**Evidence:** no stable tag/release; CHANGELOG only Unreleased; docs explain source replacement and pins, but Coolify upgrade unsupported and project source upgrade is essentially “use another reviewed checkout/revision, then validate”.

**Problem:** external user cannot answer simply: “какую версию Solo VPS мне поставить?”, “как обновить с N до N+1?”, “какой migration/recovery contract?”

**User impact:** users stay on arbitrary snapshots or pull too much change at once; support becomes revision archaeology.

**Why this matters:** External adopters need a small, versioned support contract to know which host/runtime/platform combinations are expected to work and which upgrades are safe.

**Recommendation:** when first public alpha is ready, publish semver-ish tagged releases (even `0.x`), per-release supported Ubuntu/Coolify/Docker matrix, upgrade notes and one previous-version upgrade test.

**Acceptance criteria:** install docs point to a released version, not moving source; release dry-run is enforced by CI; upgrade from previous release is exercised on disposable target.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

# 9. Findings — P3/P4

### CRIT-018 — [P3] Documentation volume is disproportionate to current product surface

**Area:** Documentation / maintenance  
**Evidence:** Passport 2,781 lines + Roadmap 3,353 + clean runbook 507 + command reference 448, before ordinary docs.

**Problem:** core concepts are repeated across README, Passport, Roadmap, command reference and runbook. Validators then enforce parts of this duplication.

**User impact:** contributors spend time deciding which document is authoritative; drift becomes inevitable.

**Why this matters:** Documentation duplication is not cosmetic in an ops project; it raises support cost and increases the chance that an obsolete procedure is treated as current.

**Recommendation:** preserve deep docs, but aggressively reduce duplicated state. README = user truth; architecture/ADR = design truth; ROADMAP = next state; evidence = artifacts; Passport = concise north star.

**Acceptance criteria:** One canonical current-state document owns supported capabilities and blockers; Roadmap links to evidence/history instead of duplicating it; README/Passport reference that source without contradictory state claims.

**Impact:** Medium  
**Effort:** Medium  
**Confidence:** High

---

### CRIT-019 — [P3] Optional features leak into the conceptual default profile

**Area:** Architecture clarity  
**Evidence:** Passport contains Tailscale and broad monitoring/backup default-profile language while current README/roadmap intentionally defer or make these optional.

**Problem:** future contributors can reintroduce complexity because old “default” language remains architecturally prestigious.

**User impact:** A solo operator can be pushed toward extra accounts, agents, credentials, and failure modes before the core recovery loop is reliable.

**Why this matters:** Optionality is valuable only when it does not contaminate the minimal product path or consume priority ahead of data protection and rebuildability.

**Recommendation:** mark Tailscale, richer observability, shell UX and DB admin UI as explicit optional modules with zero dependency from core acceptance criteria.

**Acceptance criteria:** The v1 core Quick Start does not require Tailscale, Grafana/Alloy, or error tracking; each remains independently opt-in behind a documented capability boundary.

**Impact:** Medium  
**Effort:** Low  
**Confidence:** High

---

### CRIT-020 — [P4] Archive/review reproducibility is weaker without Git metadata

**Area:** Review/release evidence  
**Evidence:** source archive contains an archive comment that looks like a commit SHA, but no `.git` metadata.

**Problem:** reviewer can reference the revision hint but cannot independently prove worktree cleanliness, branch/tag or exact ancestry.

**User impact:** A reviewer or adopter cannot reliably map this supplied archive to a public immutable source revision, weakening reproducibility and audit trails.

**Why this matters:** Infrastructure reviews and incident follow-up depend on knowing exactly which source revision produced a host or artifact.

**Recommendation:** release/review archives should include a generated `REVISION`/manifest with commit, tree hash, release tag and build timestamp, or ship a GitHub source archive whose tag is externally verifiable.

**Acceptance criteria:** Published archives/releases carry an unambiguous tag/commit identifier and can be mapped back to an immutable public revision without relying on archive comments alone.

**Impact:** Low  
**Effort:** Low  
**Confidence:** High

---

# 10. Overengineering / complexity that should be deleted or simplified

## 10.1 Contract validators

**Current value:** they protect specific security/document invariants and have caught regressions.  
**Cost:** 32 validators + 37 test modules, many tests copy source trees and mutate text; aggregate validation is slow.  
**Main risk:** green source contracts become a proxy for runtime confidence.  
**Verdict:** **REVISE**.

Delete/reduce tests whose only value is preserving incidental wording or internal implementation shape. Keep tests for security boundaries, parser behavior, atomic file handling and mutation safety.

## 10.2 ROADMAP as evidence database

**Current value:** excellent maintainer memory.  
**Cost:** 3,353 lines of mixed present/past state.  
**Main risk:** stale evidence appears current.  
**Verdict:** **REVISE aggressively**.

## 10.3 CI SSH tunnel

**Current value:** keeps raw Coolify management port loopback-only and limits forwarding identity.  
**Cost:** dedicated SSH lifecycle + host keys + Match rules + runner tunnel logic.  
**Main risk:** operational complexity and more secrets than necessary.  
**Verdict:** **REVISE**, evaluate HTTPS API after dashboard domain.

## 10.4 M24 Docker socket proxy

**Current value:** avoids direct Alloy socket access.  
**Cost:** privileged proxy, coarse Docker API read surface, extra service and secret-confidentiality concern.  
**Main risk:** container inspect disclosure.  
**Verdict:** **OPTIONAL / REVISE; do not default-enable**.

## 10.5 Tailscale in north-star documents

**Current value:** private admin access can be useful.  
**Cost:** another account/network/control plane.  
**Main risk:** distracts from simple public SSH + provider recovery model.  
**Verdict:** **OPTIONAL**. Do not let it into core definition of done.

---

# 11. Missing production capabilities

Not every production platform needs Kubernetes, HA database clusters or multiple VPSes. Solo VPS correctly rejects that complexity. But a single-VPS product still needs these minimum capabilities:

1. **Off-site data survival** — not implemented end-to-end.
2. **Exercised restore** — not implemented.
3. **Lost-host rebuild runbook + proof** — not implemented.
4. **Deployment rollback** — not implemented.
5. **External outage alerting** — not proven.
6. **Repository CI** — missing.
7. **Supported upgrade lifecycle** for Coolify/project source — incomplete.
8. **Capacity thresholds** — disk exhaustion, backup growth, Docker image/log growth need at least documented/alertable thresholds; `ops-status` alone is manual observation.
9. **Security report channel** — not guaranteed.
10. **Release version compatibility matrix** — not yet published.

What is **not** missing and should not be added merely for optics:

- Kubernetes;
- multi-node HA;
- self-hosted Prometheus/Grafana/Loki stack on another VPS;
- Vault/consul-class secrets platform;
- bespoke database orchestrator;
- generic plugin framework;
- service mesh.

---

# 12. Technology verdicts

## Ansible

**Value:** excellent fit for one Ubuntu host, desired state and staged mutation.  
**Cost:** Python/toolchain/collection setup and verbose playbooks.  
**Main risk:** source validation can masquerade as real host proof.  
**Verdict:** **KEEP**.

The project uses Ansible responsibly: no obvious `shell`/`raw` sprawl, explicit preflight and idempotency focus.

## Coolify

**Value:** eliminates custom application orchestrator/UI and provides deployment, TLS, DB/service lifecycle.  
**Cost:** fast-moving upstream, own database/state, upgrade/recovery complexity.  
**Main risk:** Solo VPS pins deeply into one version while upgrade lifecycle lags.  
**Verdict:** **KEEP + REVISE lifecycle**.

Do not replace Coolify with Kubernetes. Finish tested upgrade/backup/recovery around it.

## GitHub Actions + GHCR

**Value:** appropriate managed CI/registry for solo user.  
**Cost:** credentials and provider coupling.  
**Main risk:** current runtime deploy rollback and transport complexity.  
**Verdict:** **KEEP**.

## SOPS + age

**Value:** simple recoverable workstation-owned secret encryption without running a secrets server.  
**Cost:** one important private key + backup procedure.  
**Main risk:** recovery key loss/operator mistakes.  
**Verdict:** **KEEP**.

Current implementation is one of the better-balanced parts of the project.

## restic

**Value:** good fit for encrypted off-site single-host backup.  
**Cost:** repository credentials, retention, restore discipline.  
**Main risk:** false confidence if tooling installation is called backup.  
**Verdict:** **KEEP, FINISH NOW**.

## Grafana Cloud + Alloy

**Value:** avoids a second monitoring VPS; managed historical logs/metrics are useful.  
**Cost:** provider account, credentials, agent, Docker discovery boundary.  
**Main risk:** M24 proxy confidentiality + priority inversion.  
**Verdict:** **OPTIONAL / REVISE**.

Current pinned Alloy `1.18.1` is fresh as of review date according to official Grafana releases. Fresh versioning is not the issue; integration boundary is.

## docker-socket-proxy

**Value:** can restrict Docker API compared with raw socket.  
**Cost:** coarse prefix ACL and another privileged component.  
**Main risk:** read-only container inspect may expose secrets.  
**Verdict:** **REVISE or SUPERSEDE for M24**.

## Tailscale

**Value:** useful private access option.  
**Cost:** external account/control plane and onboarding.  
**Verdict:** **OPTIONAL, not core**.

---

# 13. Quick Start critique

## What is good

- PRE-ALPHA warning is prominent.
- Mutating vs read-only commands are often explicit.
- `doctor` before mutation is strong.
- state lives outside Git checkout.
- config is intentionally small.
- provider console/recovery gate before SSH hardening is correct.
- root session retention and staged handoff are thoughtful.

## What is bad

1. Quick Start is too long for its promise.
2. `make setup` installs full QA/runtime; first user pays maintainer-tooling cost.
3. `make validate` is placed on first-run critical path despite being a large developer-grade suite.
4. same-VPS controller key and workstation admin key are conflated until late.
5. `bootstrap` name suggests a fuller outcome than it performs; it stops before hardening/Coolify.
6. user moves across root checkout, admin checkout and workstation with state/keys in each.
7. Coolify UI access still requires tunnel/registration/manual Sentinel decision.
8. actual production completeness later requires CI, secrets, backup and observability flows not represented by one coherent install outcome.

### Recommendation

Create a **fast user validation** distinct from full developer validation:

- `make doctor` / `make preflight` should verify prerequisites and config in seconds.
- `make validate` can remain maintainer/CI gate and should not block every fresh user before the first bootstrap unless its full cost is required for safety.

If syntax/lint is a release property, prove it in repo CI once; do not make every operator rerun the entire source QA suite just to install a tagged release.

---

# 14. CI/CD critique

## Build/publish

Strong points:

- immutable GHCR digest identity;
- action pins;
- narrow permissions;
- separate verify/deploy concepts;
- no `latest` handoff;
- token handling avoids URL/body leakage.

Critical weakness: CRIT-002 rollback.

## Transport

The restricted SSH tunnel is defensible, but disproportionately complex relative to Coolify’s authenticated HTTPS API. Re-evaluate after dashboard domain is production-supported.

## Failure taxonomy that docs/tests should expose

```text
build failure
  => no runtime mutation

registry publish/verify failure
  => no runtime mutation

API preflight failure
  => no runtime mutation

deploy PATCH/start failure
  => restore previous desired image

new image unhealthy
  => restore/redeploy previous image

rollback failure
  => incident: explicit operator recovery

DB migration incompatibility
  => app-owned recovery; image rollback may be insufficient

VPS lost
  => M16 restore path, not deployment rollback
```

Today these categories are not all operationally closed.

---

# 15. Coolify critique

The M9 implementation is one of the most carefully defended integrations in the repo: pinned artifacts/checksums, loopback management ports, transaction marker, recovery/adoption path, runtime verification and protection of M7 Docker baseline.

But product lifecycle is incomplete:

- exact v4.1.2 pin while upstream has moved to v4.3.3 as of 2026-08-16;
- no Solo VPS supported upgrade path;
- downstream behavior has already required version-specific workarounds and contract tests;
- dashboard-domain/terminal proof remains pending;
- first-registration and some operations remain manual UI.

**Recommendation:** define Coolify as a supported platform dependency with explicit release matrix, not a one-time installer artifact.

---

# 16. Observability critique

The project correctly avoided building a second self-hosted monitoring VPS. That is aligned with solo-user economics.

However, M24 currently has three problems:

1. **Priority:** recovery is unfinished.
2. **Boundary:** coarse Docker API access may expose secrets.
3. **Evidence:** Alloy retained app-log runtime is only source-ready, not integration-proven.

Minimum viable observability for v0.x should probably be:

- Coolify deployment/live logs;
- bounded CLI fallback;
- external uptime alert;
- basic disk/memory/cpu visibility;
- optional external retained logs only after security boundary is proven.

Error tracking should remain app-specific optional integration (Sentry/GlitchTip/Bugsink class), not host platform scope.

---

# 17. Secrets critique

SOPS + age is a good decision here because it preserves the one-workstation + one-VPS topology and avoids running a secret-management server.

Positive evidence:

- production private age identity stays on workstation;
- ciphertext and runtime material are separated;
- atomic root-only credential installation;
- strict schemas;
- no plaintext file requirement for push helpers;
- public-source hygiene tests.

Remaining issue is not cryptography but **recovery composition**: until M14–M16 prove that a new VPS can be rebuilt using the saved workstation identities plus off-site data, the secret boundary is only one component of recovery, not recovery itself.

---

# 18. Backup / DR critique

This is where engineering attention should move immediately.

The current docs are admirably honest that tooling is not backup. Keep that honesty and stop adding adjacent features until the statement can change.

A solo project does not need a sophisticated backup abstraction. It needs:

```text
one supported object-storage example
one generic S3 config model
one timer
one backup command
one freshness command
one restore command/runbook
one database backup flow
one destructive retention path with safeguards
one clean-VPS DR exercise
```

That would provide more production value than another 20 source validators.

---

# 19. Security critique

## Strong design choices

- root hardening is staged rather than automatic lockout risk;
- provider recovery is an explicit gate;
- UFW exposure model is verified;
- Docker group privilege is acknowledged rather than hidden;
- secrets boundaries are explicit;
- Coolify management ports stay loopback-only by default;
- scripts favor argv/subprocess and Ansible modules over shell strings;
- public hygiene avoids embedding operator evidence.

## Gaps

- M24 proxy confidentiality (CRIT-005);
- no guaranteed private vulnerability channel (CRIT-014);
- no hosted security/dependency CI for repository itself;
- future Docker major compatibility not bounded;
- backup/restore gaps are security gaps because ransomware/operator error/data loss are part of availability/integrity.

Do not add generic vulnerability scanners as a substitute for the blockers above. Once repo CI exists, lightweight dependency/action/image scanning is reasonable.

---

# 20. Docs critique

README is currently the most trustworthy document because it states limitations explicitly. That should remain factual source for users.

Passport should be shorter and aspirational. Roadmap should be current. ADR should explain decisions. Testing evidence should live separately. The current overlap causes repeated truth maintenance.

Recommended documentation hierarchy:

```text
README / Quick Start       current user contract
SECURITY / CONTRIBUTING    public policy
architecture.md + ADR      stable design boundaries
ROADMAP                    current priorities/blockers only
CHANGELOG                   released change history
reviews/critic              independent audits
artifacts/evidence          sanitized machine/run evidence
legacy/                     historical research only
```

---

# 21. Top 5 ROI actions

## 1. Finish M14–M16 before new platform features

**ROI:** maximum. Converts “reproducible host” into survivable platform.

## 2. Add deployment rollback

**ROI:** very high, relatively small code change. Current helper already captures all inputs needed.

## 3. Fix human SSH key onboarding

**ROI:** very high. Removes a hidden manual step from the most dangerous stage.

## 4. Add fast hosted repo CI and shift test budget from text contracts to disposable runtime

**ROI:** high. Makes existing quality work credible and reduces maintainer-specific evidence.

## 5. Simplify the surface

In one pass:

- hide internal Make targets from default help;
- separate user preflight from full source QA;
- freeze/revise M24 proxy;
- evaluate HTTPS Coolify API instead of default CI SSH tunnel;
- shorten Roadmap/Passport.

**ROI:** high because it reduces every future feature’s maintenance cost.

---

# 22. What NOT to build yet

Do **not** spend next milestones on:

- Kubernetes;
- second VPS / HA cluster;
- self-hosted Grafana/Loki/Prometheus;
- generic secrets service;
- generic backup provider plugin system;
- multi-cloud abstraction;
- elaborate Tailscale automation;
- pgAdmin platform automation;
- additional documentation contract tests;
- richer dashboard UI owned by Solo VPS;
- generalized deployment orchestrator.

Every one of these is lower ROI than restore, rollback, CI and onboarding simplification.

---

# 23. Technology freshness check — official sources

This review checked current upstream state because dependency conclusions are time-sensitive.

| Component | Project state observed | Official current evidence on 2026-08-16 | Review conclusion |
|---|---|---|---|
| Coolify | pinned v4.1.2 | official release list shows v4.3.3 latest (2026-08-15) | pin is behind; not automatically bad, but upgrade/test lifecycle is required |
| Grafana Alloy | pinned 1.18.1 | official releases show 1.18.1 (2026-08-06) | freshness good; security boundary is the problem |
| restic | pinned 0.19.1 | official release 0.19.1 (2026-07-05) | freshness good; missing execution/restore is the problem |
| SOPS | pinned 3.13.3 | official release list has 3.13.3 | freshness good |
| docker-socket-proxy | pinned 0.5.0 image/digest | upstream docs still describe coarse API-section ACL and `--privileged` usage | design must account for read confidentiality |

Official sources:

- Coolify releases: <https://github.com/coollabsio/coolify/releases>
- Coolify API auth: <https://coolify.io/docs/api-reference/authorization>
- Coolify upgrades: <https://coolify.io/docs/get-started/upgrade>
- Docker socket proxy: <https://github.com/Tecnativa/docker-socket-proxy/blob/master/README.md>
- Docker CLI/config security note: <https://docs.docker.com/reference/cli/docker/>
- Grafana Alloy releases: <https://github.com/grafana/alloy/releases>
- restic releases: <https://github.com/restic/restic/releases>
- SOPS releases: <https://github.com/getsops/sops/releases>

---

# 24. Final decision matrix

| Question | Answer |
|---|---|
| Is the repository careless? | No. Many safety boundaries are unusually deliberate. |
| Is it production-ready? | **No.** README is correct to deny this. |
| Is the architecture fundamentally wrong? | No. One VPS + Ansible + Coolify + managed CI/storage is coherent. |
| Is there overengineering? | **Yes:** validators/docs/evidence machinery and CI/observability transport exceed current recovery maturity. |
| Is there dangerous underengineering? | **Yes:** restore/DR, deployment rollback, external outage detection, onboarding human-key handoff. |
| Should Coolify be replaced? | No. Fix lifecycle and rollback around it. |
| Should Ansible be replaced? | No. |
| Should SOPS/age/restic be replaced? | No. Finish restic recovery path. |
| Should Alloy be core now? | No. Optional until proxy boundary and recovery priorities are resolved. |
| Main thing to delete/simplify | public Make surface + redundant doc/contract state machine. |
| Main thing to build next | real off-site restore/DR. |

---

# 25. Final verdict

## **REJECT** — production release

A production release should be rejected until at least CRIT-001 through CRIT-005 are resolved with runtime evidence.

## **CONDITIONAL PASS** — continued PRE-ALPHA development

As a PRE-ALPHA engineering project the foundation is credible. The next phase should not be “more platform”. It should be **completion and simplification**:

```text
backup/restore/DR
→ deployment rollback
→ clean onboarding
→ hosted CI/runtime evidence
→ simplify CLI/docs
→ only then optional observability polish
```

The project is closest to being good when it behaves like a small, opinionated recovery-first appliance. It is furthest from that goal when it turns every internal invariant into another public command, validator, document state machine or auxiliary runtime service.

**The fastest route to a trustworthy Solo VPS is to build less and prove more.**
