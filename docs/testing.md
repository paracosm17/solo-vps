# Testing and controller QA

## Basic runbook acceptance

The user-facing path is `quick-start.md` followed by `operations/first-app.md`, with matching Russian pages. Follow `DOCUMENTATION_GUIDE.md` when editing it. Maintainer checks must not become required detours in that path.

Before accepting CI-template changes, run these from the Solo VPS checkout on the supported controller:

```bash
make validate-ci-template
make test-ci-template
make validate-application-migration-contract
make test-application-migration-contract
```

Replay the written basic instructions through dashboard HTTPS, initial public GHCR image, healthy first deployment, restricted CI access, API/GitHub settings, subsequent PR/main delivery, changed runtime ENV and visible request logs. Record each observed stage separately. A documentation build does not establish runtime proof.

Second-run idempotency, repeated audit chains, reboot, controlled interruption/resume and negative checks belong to clean-target acceptance below and in `clean-vps-test.md`. For application CI, a disposable PR with an intentionally failing test must block publication/deployment. Keep that negative proof outside the new-user installation walkthrough.

Solo VPS separates **source/local quality checks** from **host integration evidence**. M20 starts by making the Ansible parser/lint layer reproducible on a controller; it does not claim disposable-host integration yet.

## Why this layer exists

Before M20, `make validate` could run the repository's Python/YAML contract tests everywhere, but real `ansible-playbook --syntax-check` was skipped whenever Ansible was absent. That leaves a gap: PyYAML can parse a file that Ansible itself rejects.

The M20 reference toolchain therefore pins:

- `ansible-core==2.21.3`;
- `ansible-lint==26.6.0`;
- `yamllint==1.38.0`;
- `community.general==13.0.1` through `ansible/requirements.yml`.

These are controller-runtime dependencies only. On a separate controller they do not touch the VPS; in the default same-VPS first-run flow they live as local tooling on that machine and are not part of the Ansible-managed host baseline. The pinned Ansible Core and collection path are also the default runtime used by Ansible-backed `make` commands, which avoids a second unpinned/global Ansible installation.

## Bootstrap the QA environment

The standard Ubuntu 24.04 first-run entry point is:

```bash
sudo apt-get update
sudo apt-get install -y make
make setup
```

GNU Make is the only package that must exist before the repository can bootstrap itself. `make setup` then installs `python3`, `python3-yaml`, `python3-venv`, `openssh-client`, and `ca-certificates`, creates/reuses the default controller SSH identity, and installs the pinned persistent QA toolchain. Existing SSH keys are never overwritten.

For an already prepared controller, reinstall only the pinned persistent toolchain with:

```bash
make qa-tools
```

Both `make setup` and `make qa-tools` require network access to the Python package index and Ansible Galaxy for the toolchain install. The resulting controller state lives outside the Git checkout by default:

```text
~/.local/share/solo-vps/toolchain/qa/
~/.local/share/solo-vps/toolchain/ansible-collections/
```

Use `make paths` to print the effective location. `XDG_DATA_HOME` and `SOLO_VPS_DATA_DIR` overrides are supported.

A `.solo-vps-ready` marker is written only after both the Python tools and the pinned Ansible collection install successfully; partial bootstrap state is ignored by `make validate` and rejected by `make qa-check`.

The top-level QA dependencies are exact pins. Transitive Python dependencies are still resolved by pip at install time; M20 intentionally does not introduce a large hash-locked Python dependency graph yet. If hosted CI later needs stronger hermetic reproducibility, add a reviewed lock step as a separate change.

## Repository CI fast gate (CRIT-004)

`.github/workflows/repository-ci.yml` defines the public **Repository CI** workflow. It runs the stable `fast-source` status check on pull requests, pushes to `main`, and manual `workflow_dispatch` runs using the explicitly selected `ubuntu-24.04` GitHub-hosted runner.

The workflow intentionally has only `contents: read` permission, keeps mutable Solo VPS controller state under `${{ runner.temp }}`, and **does not use deployment secrets** or any VPS/Coolify/GHCR production credential. The only GitHub credential referenced is the runner-provided read-only `github.token`, scoped to the checkout step and passed to one `git fetch` through an ephemeral HTTP extra-header rather than persisted in the remote URL/config. This lets the same source gate be tested before public release while keeping later repository code outside the token-bearing step. It also avoids external `uses:` actions in this first gate: the job fetches the exact `${GITHUB_REF}`, checks out `FETCH_HEAD`, and asserts that `HEAD == ${GITHUB_SHA}` before running repository code.

The bounded command is:

```bash
make ci-fast
```

`ci-fast` first runs a selected source contract/regression set through `ci-fast-source`, then creates the pinned QA environment with `make qa-tools` and runs the real `make qa-static` sequence. It deliberately does **not** call the full `make validate` aggregate because that aggregate is the comprehensive local/release surface and has exceeded short execution windows in prior review environments.

The target for this hosted gate is a fast public regression signal, not host integration. A green `fast-source` run proves the checked revision passes the selected Python/YAML/contracts plus pinned yamllint, Ansible syntax and ansible-lint layers. It does not prove firewall, SSH reconnect, Docker/Coolify runtime, backup or restore behavior.

CRIT-004 is not closed by adding this YAML alone. The `fast-source` job is a **self-repository** check for Solo VPS and cannot receive V3 hosted evidence until Solo VPS itself has an upstream GitHub repository. A standalone consumer application repository proves M10/M11 delivery, not Solo VPS repository CI. Do not add `fast-source` to a consumer repository's required checks: if that repository never emits the job, GitHub will keep it `Expected`/waiting rather than proving anything. The actionable CRIT-004 half now is controlled disposable/clean Ubuntu target automation with sanitized retained evidence; self-repository PR/main/manual + required-check proof returns when the upstream Solo VPS repository exists.

## Disposable clean-target core proof (CRIT-004)

`scripts/prove_disposable_clean_target.py` and the hidden `make prove-disposable-clean-target` target automate the provider-neutral **disposable clean-target core proof** against one explicitly marked fresh Ubuntu 24.04 VPS. The harness does not provision or delete provider resources. It refuses the current controller/configured production target, verifies the provider-console Ed25519 host-key fingerprint with strict host-key checking, requires a clean-state marker, uses temporary automation/human test identities, runs bootstrap/verify/SSH-hardening/audit, and requires the second bootstrap recap to converge with `changed=0` and `failed=0`.

The retained artifact is sanitized evidence JSON outside the source checkout. Target address, target marker value, host-key fingerprint, generated private keys and raw command logs are not retained. The VPS is deliberately left intact on failure for diagnosis and must be destroyed manually in the provider control plane after the evidence is reviewed.

This proof is V3 host-core evidence only. Coolify, application delivery, backup/restore and observability credential flows remain separate evidence layers, and it **does not satisfy the deferred self-repository `fast-source` proof**. The full maintainer procedure is in `docs/disposable-clean-target.md`.

## Verify the installed toolchain

```bash
make qa-check
```

This checks the exact three Python package versions and confirms that the pinned `community.general.ufw` module is discoverable from the persistent collection path.

## Run static Ansible QA

```bash
make qa-static
```

Execution order is fail-fast:

```text
yamllint
↓
ansible-playbook --syntax-check for all project playbooks
↓
ansible-lint (basic profile, offline)
```

The lint policy keeps the `basic` profile and all normal variable-name safety checks. Solo VPS deliberately uses one project-wide `solo_vps_*` variable namespace across roles, so only `var-naming[no-role-prefix]` is skipped. The broader `var-naming` rule is **not** disabled. Top-level `import_playbook` entries are named normally and are protected by the source QA contract, rather than suppressing `name[play]`.

The standalone `.yamllint` rules are also kept compatible with ansible-lint's embedded YAML rule requirements (`comments`, `comments-indentation`, `braces`, and octal-value handling) so the two lint layers do not disagree about formatting policy.

`qa-static` never installs packages or collections. Bootstrap is deliberately separate so a validation run cannot unexpectedly contact package registries.

The existing `make validate` always checks the source QA contract. If the persistent QA venv already exists, it also runs `qa-static`; otherwise it reports the tool layer as skipped instead of pretending Ansible syntax/lint passed.

## Why not Molecule for the first clean-target harness?

The first controlled backend is intentionally smaller than Molecule: a provider-neutral SSH harness against an explicitly marked disposable Ubuntu 24.04 VPS. It exercises the real systemd/UFW/Docker/SSH host behavior without committing Solo VPS to a cloud provider API or local VM runtime. Molecule remains an option later if a stable VM backend materially simplifies repeated release-candidate scenarios.

## Evidence boundary

This M20 slice can establish:

```text
V1 — real Ansible syntax/lint when the pinned QA tools are available
V2 — local QA contract/unit tests
```

With only source/QA checks it cannot establish host integration. A successful `prove-disposable-clean-target` run adds **V3 disposable host-core integration** for bootstrap, SSH hardening, audit and idempotency, while V4 still requires the corrected release-candidate clean replay including the broader platform path.

Do not translate a clean linter run into claims about firewall reachability, systemd behavior, Docker networking, SSH lockout safety, backup recovery, or application deployment.

## Strict Ansible conditional source guard

The pinned `ansible-core` line rejects malformed/non-string conditional expressions. YAML text containing `: ` inside an unquoted `assert.that` expression can parse as a mapping even when the colon visually appears inside an inner Jinja/string literal. `scripts/validate_qa_contract.py` therefore walks every Ansible YAML file and requires every `assert.that` entry to parse as a string before remote execution. This complements, rather than replaces, the real pinned `ansible-playbook --syntax-check` and target run.

The QA contract also rejects dependencies between sibling keys in one `set_fact` mapping. A fact derived from another newly assigned fact must live in a later `set_fact` task; this mirrors the pinned Ansible runtime behavior and prevents source validation from missing same-task variable-resolution failures.


## Real M5 parser regression evidence

The fifth Ubuntu 24.04 operator run proved the repeated M3/M4/M5 mutating path converges with `ok` results and retains SSH after UFW, but the read-only firewall verifier rejected the host because its parser assumed the numbered UFW action text was always `ALLOW IN`. The M5 contract now tests both `ALLOW` and `ALLOW IN` fixtures and rejects `ALLOW OUT/FWD`.

The sixth operator run proved the corrected parser sees the exact expected UFW allow set (`22/tcp`, `80/tcp`, `443/tcp`). It then exposed a second verification-boundary defect: a wildcard TCP listener on port 53 was treated as public exposure even though port 53 was absent from the exact UFW allow set and incoming policy was default-deny. M5 now enforces firewall exposure through UFW state/rules and reports wildcard listeners plus `ss -lntp` process evidence diagnostically. The focused post-fix verifier remains pending the next operator rerun.

The seventh operator run proved the complete pinned source/QA gate for that revision (`make validate`, yamllint, all syntax checks, ansible-lint production profile) and then exposed a runtime task-structure defect before the firewall assertion: `solo_vps_firewall_unexpected_wildcard_tcp_ports` referenced facts assigned by sibling keys in the same `set_fact` task. The dependent diagnostic is now derived in a second task, and the repository-wide QA contract rejects any future same-task sibling dependency. Focused M5 verification remains the next real checkpoint.

The latest operator run proves the corrected focused M5 verifier PASS and then reaches M6/M7 for the first time. M6 automatic updates applied and verified successfully. M7 created the official Docker key/source but failed at package install with `No package matching 'docker-ce' is available`. The source bug was sequencing: the install task used `cache_valid_time: 3600`, and M6 had refreshed APT metadata less than an hour earlier, before the Docker repository existed. M7 now performs an explicit post-repository APT metadata refresh, checks the Docker CE candidate, and only then installs packages. A dedicated source contract rejects reintroducing the stale-cache shortcut or moving package installation ahead of the refresh/candidate gate.


## Consumer repository branch-protection proof

For the standalone application template, the relevant pull-request checks are the jobs the application workflow actually emits:

```text
Application tests
Build pull request image
```

`fast-source` is **not** a consumer-app check. Requiring a non-existent `fast-source` status produces a permanently expected/pending requirement and does not prove that a broken application PR is blocked by its real CI.

A negative application proof should intentionally fail `Application tests`, keep publish/verify/deploy skipped, and verify that merge is blocked by the real required application check. If the build job depends on tests, remember that a dependency-skipped GitHub Actions job can be reported as a successful/skipped conclusion; `Application tests` therefore needs to be required independently rather than relying on the downstream build job to carry test failure.

Keep this evidence separate from CRIT-004. Solo VPS still needs its own `fast-source` required-check proof once its upstream repository exists.

## Real M3–M9 clean-target progression

The next Ubuntu 24.04 maintainer-integration runs substantially advance the integration boundary beyond the earlier M5/M7 failures:

- M7 Docker installs from the official repository after the explicit metadata refresh; focused `make verify-docker` passes with Engine `29.7.2`, Compose `5.4.0`, `live-restore=true`, the `local` logging driver, no Docker daemon TCP listener, and admin Docker access;
- aggregate `make bootstrap` then converges with `changed=0`, followed by read-only `make verify` and `make audit` PASS;
- a dedicated second aggregate bootstrap again reports `changed=0`, providing real idempotency evidence for M3–M7 on the current target;
- after inventory switches to `ops`, `make doctor`, `make verify`, and `make audit` pass through the non-root administrator with passwordless sudo;
- an external workstation proves `ops` login before hardening, `make ssh-harden` and `make verify-ssh` pass, a fresh external `ops` login still succeeds, and external `root` SSH is denied;
- M9 `make coolify-readiness` passes and first-install mutation reaches running containers, a converged Docker healthcheck, and HTTP 200 from `127.0.0.1:8000/api/health`.

The M9 run then exposed a verifier race rather than a runtime failure: `docker inspect` for the main/realtime containers had been registered **before** the health wait. The wait and HTTP probe later passed, but the final assertion decoded the old pre-wait JSON and therefore saw the earlier health state. The verifier now re-inspects both containers after health convergence and prints that fresh evidence before enforcement.

The failed run also created a valid-looking `/data/coolify` platform without the managed marker. New first installs now create a transaction marker before further mutation so known interruptions can be recovery-verified without regenerating secrets. The current older unmarked partial state uses an explicit confirmation-gated `make coolify-recover` path. This is a narrow first-install recovery mechanism, not general Coolify adoption or upgrade support.

The next real `ops`-workspace run passed the complete fix10 source/QA gate, including yamllint, every Ansible syntax check, and ansible-lint with zero failures/warnings. Explicit recovery then reached the exact-footprint gate and failed only because it required the original `id.<admin.user>@host.docker.internal` file. Pinned Coolify v4.1.2 legitimately imports that bootstrap key during production seeding, clears/rebuilds the SSH-key directory, and materializes the database-backed key as `ssh_key@<uuid>`. Recovery now recognizes both the pre-seed and post-seed forms, requires exactly one candidate, and proves its public half is already authorized for `admin.user` instead of generating a replacement key.

The subsequent handoff run proves the new same-VPS transition on the real Ubuntu target: `/home/<admin.user>/solo-vps` is created, the pinned toolchain is rebuilt under `ops`, a distinct `/home/<admin.user>/.ssh/id_ed25519` controller key is prepared, same-VPS access is authorized, and `make doctor` passes as `ops`. The same run exposed one source-formatting defect in `ansible/roles/coolify/tasks/install.yml`; source QA now mirrors yamllint's no-trailing-blank-line policy even when the pinned QA virtualenv is unavailable, and future handoffs require `make validate` to pass in the destination workspace before the ready marker is written.

The same integration run proves the product should stop depending on the retained root checkout immediately after SSH hardening. The onboarding contract now includes a same-VPS admin workspace handoff that rebuilds the non-relocatable persistent virtualenv under `/home/<admin.user>/solo-vps`, requires `make validate` to pass there, prepares the admin-owned controller SSH identity, and proves `make doctor` before the root session is considered disposable.


## External state recovery and inventory transition regression

A real managed-VPS source replacement proved the external data-root layout through `make paths`, persistent `make setup`, `make init`, and config validation. The first `doctor` then exposed a lifecycle bug: recreating `hosts.yml` from the public example restored the bootstrap SSH identity even though the host had already transitioned to the managed administrator.

The regression contract now separates human configuration from technical connection state:

```bash
# fresh provider/bootstrap path after editing config.yml
make use-bootstrap SSH_USER=<provider-user>

# after bootstrap, or when reconstructing state for an already-managed VPS
make use-admin
```

Both commands synchronize `ansible_host` from `server.host`; `make use-admin` also derives `ansible_user` from `admin.user`. Unit coverage proves bootstrap/admin switching, idempotency, `0600` inventory mode, invalid-user rejection, and symlink fail-closed behavior. M14 host commands require the admin inventory gate so a stale bootstrap identity is rejected before backup mutation.

## M11 hosted GHCR and immutable Coolify handoff evidence

The first hosted M11 workflow run now proves the registry portion beyond static YAML validation. The sample repository completed the GitHub Actions pipeline and the fresh `verify-published` job pulled:

```text
ghcr.io/<github-user>/hello-app@sha256:<digest>
```

Docker reported the same digest and the runner smoke container passed the exact fixture health contract on attempt 2. Because the smoke command uses `--pull never`, that health result is evidence for the already-pulled immutable artifact rather than a second mutable lookup.

The separate M11 Docker Image handoff is now maintainer integration PASS. `scripts/validate_coolify_image_handoff.py` still validates only canonical GHCR `name@sha256:digest` references and reproduces the pinned v4.1.2 creation-UI double-`@sha256` defect, while `maintainer image-handoff proof` proves the corrected General-form pair deploys the exact digest with no Git/VPS build, returns a healthy container, keeps 8080 Docker-internal, and preserves a passing audit.

A maintainer API run closes the loopback API semantics proof: full `make validate` passes, read-only API state validation passes, exact-digest PATCH/start returns deployment UUID `<deployment-uuid>`, deployment reaches `finished`, application reaches `running:healthy`, Docker still reports the exact immutable digest, host 8080 remains absent, and both `make verify-coolify` and `make audit` pass.

A maintainer transport run closes the restricted SSH transport proof. `make validate` passed with the transport suite, the first explicit host apply installed only the dedicated `solo-vps-ci` identity/policy, `make verify-ci-deploy-transport` passed, and the second managed apply converged with `changed=0`. Effective `sshd -T` shows local forwarding only, `PermitOpen 127.0.0.1:8000`, `PermitListen none`, `MaxSessions 0`, and the expected key-only/sessionless restrictions. Independent Windows checks prove the approved tunnel reaches `/api/health` with HTTP 200, while shell/session, remote `-R`, and an unapproved `6001` destination fail. `verify-ssh`, `verify-coolify`, and `audit` remain PASS after the change.

A maintainer hosted run proves that hosted boundary end to end. GitHub commit `<application-commit-sha>` published and independently verified `ghcr.io/<github-user>/hello-app@sha256:<digest>`. The `production` deploy job opened the restricted SSH tunnel, passed the loopback Coolify API check, deployed the same digest under deployment UUID `<deployment-uuid>`, and finished `running:healthy`. Maintainer integration `docker inspect` reports the same immutable image reference and healthy state; no host `8080` listener appeared; `verify-ci-deploy-transport`, `verify-coolify`, and `audit` remain PASS. A maintainer repeat run then used **Re-run all jobs** without changing the GitHub environment or host transport. That rebuild produced `ghcr.io/<github-user>/hello-app@sha256:<digest>`; Coolify started that exact digest, the real container reports the same `.Config.Image` and `healthy`, host `8080` is still absent, and transport/Coolify/audit checks remain PASS. M11 repeatability is therefore integration-proven at V3 even though the build output is not claimed to be bit-for-bit reproducible across reruns.

Maintainer integration Docker Image attempt #1 remains historical FAIL evidence, not a registry failure: Coolify created `docker_registry_image_name=<repository>@sha256` plus `docker_registry_image_tag=sha256-<digest>`, then deployment generated `<repository>@sha256@sha256:<digest>` and Docker rejected it as `invalid reference format`. The corrected retry is PASS and proves exact prebuilt-digest startup without Git import or Docker build steps. Direct API, restricted transport, hosted deployment, and unchanged hosted repeat-run are now separately integration-proven.

CRIT-002 adds the negative transaction contract to that successful M11 path. Source tests cover failed deployment, unhealthy-after-finished, deployment timeout, rollback failure, mutable previous-state refusal, and explicit known-good recovery. The deploy helper captures the previous immutable desired image before mutation, restores and starts it on any candidate failure after PATCH, requires `running:healthy`, returns `DEPLOY_FAILED_ROLLBACK_OK` with a non-zero deploy exit when recovery succeeds, and emits `DEPLOY_FAILED_ROLLBACK_FAILED` plus a token-free recovery command if the rollback itself fails. The real maintained-VPS proof is now V3 PASS: an intentionally absent digest failed, the exact previous immutable desired state was restored, the application returned to `running:healthy`, and follow-up Coolify verification/audit stayed green. Application-image rollback is not database/schema rollback.

A later standalone application-repository proof synchronized that same rollback-aware helper into the consumer repository. Its pull request ran both the application suite and 27 deployment/helper contract tests, then completed a Docker build without registry publish/deploy; the three main-only jobs were skipped on the PR. After merge, the main workflow published a new GHCR image, verified the immutable digest, opened only the restricted SSH tunnel to the loopback Coolify API, deployed the exact digest, and finished `running:healthy`. Fresh `/healthz` lines continued after the rollout. This is consumer CI/CD integration evidence; it does not replace CRIT-004 hosted CI for the Solo VPS repository itself.


## CRIT-015 external uptime / total-host outage detection

Source regression is:

```bash
make validate-external-uptime
make test-external-uptime
make uptime-plan UPTIME_HEALTH_URL='https://app.example.com/healthz'
```

The source contract is deliberately provider-neutral and performs no provider/network write. It requires a public HTTPS application health endpoint, normal port 443, HTTP 200, five-minute interval, ten-second timeout, two consecutive failures, an off-VPS notification destination, provider test notification, outage alert, and recovery notification. It explicitly rejects same-VPS monitoring and raw Coolify management ports as evidence for total-host loss.

V2 source evidence does **not** promote CRIT-015 to integration proof. V3 requires an external service to observe a controlled whole-target shutdown, deliver the outage notification inside the reviewed latency bound, observe recovery, and deliver a recovery notification. The preferred target is the later disposable/final-validation VPS rather than intentionally powering off a real maintained production host. `make uptime-evidence` stores only an operator-attested sanitized summary outside the checkout; provider UI/event artifacts still need maintainer review before the result is accepted as V3.

The maintained-controller CRIT-015 source checkpoint is V2 PASS: contract/tests, the real public application `/healthz` endpoint returning HTTP 200, full `ci-fast-source`, and pinned `qa-static` all passed. This still does not prove external notification delivery or total-host loss.

## CRIT-011 Docker/Coolify lifecycle

Source regression is:

```bash
make validate-platform-lifecycle
make test-platform-lifecycle
make validate-docker-contract
make test-docker-contract
make validate-upgrade-guide
make test-upgrade-guide
make platform-lifecycle-plan
make coolify-upgrade-preflight
```

The Docker contract accepts only major 29 for this alpha line, rejects an unsupported existing Engine before M7 repository/daemon/service mutation, and rejects an unsupported fresh APT candidate before package installation. `state: present` remains intentional, so M7 does not silently advance an already-installed Engine.

The Coolify source path supports only `4.1.1` → `4.1.2`: preflight must prove the exact managed version/image, Docker 29.x, M7 daemon ownership, disabled autoupdate, health, and loopback 8000/6001/6002. Mutation additionally requires `make backup-check` and independent confirmation of the off-site Coolify instance-database backup. A transaction marker is written before canonical runtime mutation. Failure recovery is explicit forward resume or M16 restore; no automatic downgrade is claimed after possible database migrations.

The current CRIT-011 source checkpoint is **V2 PASS** on the maintained controller: the lifecycle, Docker, and upgrade-guide regression suites pass; the bounded `ci-fast-source` gate passes; and pinned `qa-static` completes with zero ansible-lint failures/warnings. This proves the source/QA boundary, not the upgrade itself.

The maintained-host read-only checkpoint is now **V3 PASS for the installed/current no-op boundary**:

```bash
make verify-docker
make coolify-upgrade-preflight
make verify-coolify
make verify
make audit
```

The real run verifies an installed Docker Engine inside the supported 29.x window with `changed=0`, then recognizes already-current Coolify `4.1.2` with `upgrade_required: false` and `mutation: false`. M7 Docker ownership remains authoritative, automatic Coolify updates remain disabled, management ports remain loopback-only, Coolify health/readiness checks pass, aggregate host verification is unchanged, and the security audit reports no clear violations or warnings.

This V3 evidence is deliberately narrow: it proves that an already-supported current installation is accepted **without mutation** and remains healthy under all read-only lifecycle checks. It still does **not** satisfy the previous-supported → current-supported upgrade acceptance criterion. Do not run `make coolify-upgrade` or `make coolify-upgrade-resume` on the maintained production host solely to manufacture proof.

Real upgrade evidence remains pending until one disposable Ubuntu 24.04 target is established at previous-supported `4.1.1`, upgraded to current-supported `4.1.2`, verified, and subjected to a controlled interrupted-upgrade/recovery exercise.

## CRIT-003 workstation SSH onboarding/recovery

Source regression for the revised M4 identity boundary is:

```bash
make validate-onboarding-contract
make test-onboarding-contract
```

The contract distinguishes the repository/controller automation key from an explicit human workstation public key. Tests require the public-only configuration helper to be atomic and idempotent, reject private-key material, require bootstrap/verification to manage both keys, reject the same-VPS automation key as the human recovery identity, and require two independent SSH-hardening acknowledgements: provider recovery plus a real workstation-admin login.

V3 integration evidence must be stronger than source validation. On the maintained VPS, configure the workstation `.pub` through `human-admin-key-stdin` or `human-admin-key-file`, reconcile the additive users role, then open a **fresh external workstation session using the matching private key** and prove non-interactive sudo. The hardening confirmation gate must fail when only provider recovery is acknowledged and pass only when the separate workstation-login acknowledgement is also present. This proof does not require reapplying an already-active SSH hardening policy. V4 still requires the corrected flow from a clean VPS.

## M19 Docker publication regression

The security audit reads full `docker container inspect` JSON rather than the human-oriented `docker ps .Ports` column. This avoids false failures when Docker compresses consecutive Coolify realtime publications into a display range such as `6001-6002`, and it also avoids the fix12 evidence bug where an intermediate Go-template probe returned no normalized lines on the real Docker 29 target. Ansible consumes `NetworkSettings.Ports` from JSON with `dict2items`/`subelements`, validates every port key and host-binding object fail-closed, and must produce three independent Coolify loopback bindings for 8000, 6001, and 6002.

## Real M10 proxy-start permission regression

The first M10 maintainer-integration proxy start on the reboot-proven Coolify v4.1.2 host failed before any application deployment with:

```text
bash: line 2: cd: /data/coolify/proxy/: Permission denied
```

The failure exposed an M9/M10 integration mismatch rather than a Coolify UI mistake. Solo VPS intentionally seeds the localhost server with non-root `admin.user` and keeps root SSH closed, while the older M9 directory layout mirrored upstream `9999:root` + `0700` recursively. Pinned Coolify v4.1.2 starts the proxy through a remote shell sequence containing `cd /data/coolify/proxy` before Docker Compose startup, so the SSH identity needs path traversal even when passwordless sudo is available.

The first compatibility fix was disproved on the integration target: after the managed run, Coolify changed `/data/coolify/proxy` to `<admin.user>:<admin.group>`, while `cd /data/coolify/proxy` still failed. The corrected contract is deliberately narrow but complete: `/data` is `root:root` `0711`, `/data/coolify` is UID 9999 + `<admin-group>` `0710`, and `/data/coolify/proxy` is owned by `admin.user` with `0700`. No other Coolify directories or secret files are broadened. `make coolify` converges these three path objects, while read-only `make verify-coolify` performs the real `chdir` as `admin.user`.

The M22 terminal preflight extends that same read-only verifier rather than adding a second lifecycle path: `make verify-coolify` requires the `coolify-realtime` container healthcheck plus HTTP 200 from loopback `/ready` endpoints on both `6001` and `6002`, while controller-side reachability of raw `8000/6001/6002` remains forbidden. The V3 browser proof is now PASS through a normal HTTPS Coolify instance domain: the application terminal executes non-mutating commands without the former reconnect loop, fresh live logs continue through the same hostname, the following verifier returns `changed=0`, and `make audit` remains PASS.

The maintainer integration rerun now proves the corrected model: the first V2 `make coolify` reconciles the two drifted path objects, separate `make verify-coolify` passes, direct `ops` chdir succeeds, and a second managed `make coolify` returns `changed=0`. After manual removal of generated `443/udp` and host `8080`, `coolify-proxy` is healthy and publishes only TCP 80/443; management 8000/6001/6002 stay loopback-only and `make audit` remains PASS. On the tested Coolify `4.1.2` baseline, the then-optional Sentinel agent was disabled after its Docker bridge could not reach the loopback-only Coolify endpoint; the absent container and passing verify/audit are historical evidence for that exact baseline, not a requirement for later Coolify releases. Coolify also displayed a newer-minor Traefik notice while running v3.6.25. That notice is not a test failure and no proxy upgrade is included in M10; upgrade evidence belongs to the reviewed maintenance workflow.

The first real `hello-app` deployment then proved Git fetch and Dockerfile build success at commit `<application-commit-sha>`, but failed before container start when Coolify attempted to write `/data/coolify/applications/<uuid>/.env` and `docker-compose.yaml`: `tee: ... Permission denied`. This exposed the same non-root parent-traversal class beyond the proxy path. The corrected contract gives execute-only admin-group traversal (`0710`) to the exact Coolify lifecycle namespace roots `/data/coolify/applications`, `/data/coolify/databases`, and `/data/coolify/services`, keeps their owner at UID 9999, and leaves sensitive `source` and `ssh` roots outside the exception. `make verify-coolify` performs real admin-user chdir probes on each lifecycle namespace. The maintainer integration rerun now validates all three namespace roots as `9999:<admin.group> 0710`, validates the existing resource child as writable by `ops`, and proves managed idempotency with a second `make coolify` at `changed=0`. Retrying the same application succeeds end-to-end through container startup: Dockerfile build completes, the new container starts, the custom Dockerfile healthcheck is `healthy` on attempt 1, rolling update completes, and Coolify reports `Running (healthy)`. Final integration evidence then closes M10 at V3: the app container shows only internal `8080/tcp`, the host has no 8080 listener, an external direct 8080 probe fails, Cloudflare-proxied HTTP redirects to HTTPS, `/healthz` and root return the fixture success payloads, `/missing` returns the fixture 404 payload, TLS verification reports `ssl_verify=0`, and `make verify-coolify`, `make verify`, plus `make audit` all remain PASS. A single corrected-revision fresh-target replay remains separate V4 evidence.

A later real chapter-4 PostgreSQL exercise exposed the write side of the same non-root boundary: Coolify v4.1.2 successfully reached `pg_dump`, then the host shell failed to create `/data/coolify/backups/databases/.../pg-dump-*.dmp` with `Permission denied`. In this pinned release the backup command creates the destination directory and performs shell redirection through the configured server SSH identity, while the older Solo VPS layout kept `/data/coolify/backups` at UID 9999 + `root` `0700`. The corrected contract keeps UID 9999 as owner, assigns the admin primary group, and uses `0730`: the Coolify application owner keeps full access, `admin.user` gets only write+traverse at the known backup root, and unrelated host users get no access. The read-only verifier proves `admin.user` sees write+execute but not read/list permission before a database backup is retried.



## M13 simple workstation secrets gate

Maintainer integration evidence proves the exact pinned SOPS 3.13.3 + age 1.3.1 toolchain and disposable encrypt/decrypt roundtrip. `doctor-platform-local` reports `secrets_toolchain: READY`. The simplified one-workstation + one-VPS revision then passes a fresh maintainer-integration `make validate`: YAML 85 files, workstation secrets contract 3/3, and ansible-lint 0 failures/0 warnings in 102 processed files.

Integration evidence now covers the real Windows production-key, backup-copy, local SOPS smoke, and public-policy steps. There is no second server/controller gate and no generic secret-materialization test matrix; only the read-only single-VPS private-key absence proof remains.

Source regression is now:

```bash
make validate-secrets-policy
make test-sops-policy
make validate-secrets-toolchain
make test-secrets-toolchain
make validate-workstation-secrets
make test-workstation-secrets
```

`validate-workstation-secrets` enforces the product model: one Windows/Linux home workstation + one VPS, a repository-owned Windows installer for pinned age/SOPS binaries, Linux pinned-tool installation commands, public policy initialization, and absence of the retired dedicated-controller/materialization machinery.
The current workstation source suite is 9/9. It additionally checks the Windows download-unblock guidance, process-only execution-policy fallback, suppression of noisy native warning output, and the public-only/idempotent Windows policy initializer.

Maintainer integration evidence still required to close M13:

1. run `make verify-vps-secrets-boundary` on the single VPS as the managed non-root admin (or set `VPS_SECRETS_ADMIN_HOME=/home/<admin>` from an intentional root shell);
2. confirm the standard administrator/root age private-key locations are absent;
3. keep the generated workstation SOPS policy and recipient in persistent workstation state outside the checkout rather than copying operator-specific policy to the VPS or upstream product source.

### M13 Windows integration evidence

The Windows-first path has been exercised end to end with repository-owned tooling:

- Internet-marked PowerShell helpers are handled with `Unblock-File`; process-scoped execution-policy bypass is documented only as a fallback;
- the pinned Windows age/SOPS installer downloads official artifacts, verifies project-pinned SHA-256 values, and installs under `%LOCALAPPDATA%\solo-vps\bin`;
- one workstation age key can be created and backed up;
- the SOPS production-key smoke test encrypts/decrypts a disposable sentinel and removes temporary files;
- the policy helper derives only the public recipient and creates the SOPS policy plus recipient in persistent workstation state outside the checkout;
- no private age identity is copied into the project tree or VPS.

The Windows tool/key/smoke/local-policy gate and the later read-only VPS private-key absence proof are both integration-validated; M13 is complete.

## M14/M24 credential and observability boundaries

The source-only credential suite uses synthetic values only. It validates strict schema handling, atomic/idempotent runtime-file installation, `0700`/`0600` modes, symlink rejection, and the Windows/Linux workflow contract. Real S3 credentials and the production age key are never part of automated repository tests. Live proof is the explicit workstation `backup-secrets-*`/PowerShell flow followed by `make verify-backup-credentials` on the VPS.

The M14 operational runtime adds a second synthetic-only suite:

```bash
make validate-backup-runtime
make test-backup-runtime
```

It does not contact S3. A fake restic subprocess proves exact `/data/coolify` source/exclusion selection, host/tag grouping, init-versus-adopt separation, fresh/stale snapshot classification, repository-check ordering, retention dry-run versus `--prune`, temporary restore extraction/cleanup, and bounded failure output. It also verifies that the restic child process receives only paths to short-lived root-only password/AWS credential files rather than raw secrets in command arguments or its environment. The source contract separately verifies the installed runtime path, daily backup timer, weekly maintenance timer, explicit retention confirmation, and hidden secret boundary. Real V3 evidence still requires a managed off-site repository.

```bash
make validate-observability-tooling
make test-observability-tooling
make validate-observability-credentials
make test-observability-credentials
make validate-observability-log-drain
make test-observability-log-drain
```

The M24 credential tests use synthetic Grafana-style values only. They cover HTTPS Loki endpoint shape, strict key schema, external SOPS ciphertext, SSH-stdin delivery contract, atomic/idempotent root-only runtime installation, and symlink fail-closed behavior. They do not create a Grafana Cloud account, contact Grafana, start Alloy, or grant Docker socket access.

The M24 log-drain contract is retained as regression/diagnostic coverage for the **rejected Coolify-native experiment**: clipboard-only Custom FluentBit rendering, `service_name` labeling, generated compose state, Docker `HostConfig.PortBindings`, runtime `NetworkSettings.Ports`, host listener/TCP reachability, and clean managed stop/recreate evidence. It must never recommend hand-editing Coolify-generated files. The source also provides `make test-observability-loki`, an explicit external-write integration smoke that sends one non-secret synthetic line while suppressing credential-bearing task output. Automated tests never use the production token or contact Grafana.

## M24 Coolify log-drain runtime reconciliation

When direct Grafana Loki ingestion is already proven but the Coolify drain verifier reports a generated/HostConfig binding without a runtime listener, recovery is deliberately two-phase and UI-owned:

```text
Coolify Custom FluentBit Enabled OFF
→ make verify-observability-log-drain-disabled
→ Coolify Custom FluentBit Enabled ON
→ make verify-observability-log-drain
→ redeploy one opted-in application
→ verify retained application logs in Grafana
```

The disabled-state verifier is read-only. It requires the `coolify-log-drain` container to be absent, no host listener on `127.0.0.1:24224`, and a rejected TCP connect. It does not run `docker rm`, edit `/data/coolify/log-drains`, or change the application logging driver. In Coolify v4.1.2 the Enabled checkbox triggers the start/stop instant-save action; the separate Save button only persists editable configuration while the drain is disabled.

A clean managed recreate that immediately returns to `HostConfig=true` but `NetworkSettings/listener/TCP=false` is a reproducible runtime blocker, not stale state. At that point run `make diagnose-observability-log-drain` once. The diagnostic is read-only and records only sanitized Docker/Compose versions plus collector network counts and port-materialization booleans; network names/UUIDs and provider credentials must not be printed. That final diagnosis has now excluded the extra-network hypothesis on the reviewed runtime. Do not repeat the native-drain recovery cycle; the maintained path is the repository-managed collector below.



## Repository-managed retained-log runtime

After the Coolify-native drain is rejected on a real runtime, validate the replacement in two layers:

```bash
make observability-runtime
make verify-observability-runtime
```

The first run may pull/create the pinned Docker API proxy and create/start the dedicated Alloy systemd service. When upgrading from the proven V3 loopback transport, apply first classifies the existing proxy against the exact known legacy contract, refuses unknown state, and only then replaces it with the Unix-socket contract. The new proxy has no published TCP ports, uses Docker network mode `none`, and binds `/run/solo-vps-docker-api/docker-api.sock` through a `root:solo-vps-alloy 0750` runtime directory recreated by systemd-tmpfiles. Repeated `make observability-runtime` must converge with no changes. The verifier requires the intended Alloy identity to receive Docker API status codes through that Unix socket, requires `nobody` to fail before HTTP, rejects any remaining `:2375` TCP listener, and then performs the existing bounded Alloy readiness/current-invocation diagnostics. Do not rotate credentials, widen host ports, or grant broader Docker permissions from a bare readiness failure.

The completed V3 integration proof now covers both the retained-log function and its host-local confidentiality boundary. The original loopback proxy was negatively proven because unrelated `nobody` received HTTP 200 for ping/inspect/log probes. The corrected Unix-socket migration was then applied on the real VPS: normal verification passed with no TCP `:2375`, proxy `network=none`, intended Alloy access and unrelated identity denial; `make audit-observability-confidentiality` passed with unrelated ping/inspect/log probes failing before HTTP; fresh `hello-app` `/healthz` lines continued arriving afterward; and the repeated managed apply plus verification converged with `changed=0`. This closes CRIT-005 at V3 while V4 clean-VPS replay remains a separate release gate.

Run the next security proof only as a maintainer/release gate:

```bash
make audit-observability-confidentiality
```

The audit first re-runs the normal read-only runtime verifier, then compares Unix-socket reachability for the intended `solo-vps-alloy` identity and an unrelated host-local `nobody` identity. It retains **HTTP status codes only**. It must not read or print container inspect JSON, environment values, or container log response bodies. The required post-migration result is: Alloy ping `200`; unrelated directory traversal denied; unrelated ping/inspect/log probes `-1` (no HTTP response); Alloy direct access to `/var/run/docker.sock` denied; and explicitly disabled `/info`, `/images`, `/volumes`, `/secrets`, and `/exec` sections still `403` when probed through the allowed Alloy identity.

CRIT-005, M22, CRIT-002, and CRIT-003 are now V3 PASS on their maintained integration paths. The standalone consumer app also has positive PR/main delivery evidence plus an intentional failing-PR CI proof, but that does not satisfy Solo VPS self-repository CI. The actionable CRIT-004 evidence gap is controlled disposable/clean Ubuntu target automation; `fast-source` hosted/required-check proof remains pending until Solo VPS has its own upstream repository. Raw owner-specific logs stay outside upstream source.
## M15 database backup/restore source checks

The M15 source gate is fully offline. It does not contact Coolify, S3, or PostgreSQL:

```bash
make validate-database-backup-contract
make test-database-backup-contract
make validate-database-backup-runtime
make test-database-backup-runtime
```

The runtime suite covers loopback-only API transport, bearer-token handling/redaction, explicit schedule ownership/adoption, duplicate-schedule refusal, exact S3/schedule/retention drift detection, trigger/freshness behavior, external state permissions, archive inspection, escaped private PGPASS handling, disposable target naming, relation/function/type empty-target refusal, parser-level read-only SQL checks plus server-enforced read-only verification sessions, and password redaction. Synthetic subprocess/API fixtures are **V2 source evidence only**; they are not a real database backup or restore.

Later V3/V4 integration requires a real Coolify PostgreSQL backup to the actual off-site storage, independent object existence evidence, archive download/inspection, restore into a disposable empty PostgreSQL target, and a meaningful application-level query after restore.


## M16 source-side disaster-recovery contract

`make validate-disaster-recovery` plus `make test-disaster-recovery` keep the lost-VPS path source-testable without pretending a synthetic archive is real off-site recovery evidence. The tests cover recovery-kit allowlisting/checksums/private-key rejection, the explicit distinction between staged restic material and a Coolify instance database dump, preservation of fresh Coolify runtime credentials, `APP_PREVIOUS_KEYS` handling, replacement-target confirmation, M14 database-tree/local-backup exclusions, and the final verify/audit/application-data boundary.

A real V4 pass still requires a clean Ubuntu 24.04 replacement target, a real off-site restic snapshot, a real Coolify instance database backup, real application PostgreSQL backup/restore, immutable redeploy, and final health/verify/audit evidence.


## M16 lost-VPS recovery source contract

Source-only checks:

```bash
make validate-disaster-recovery
make test-disaster-recovery
```

These tests do not contact S3 or mutate Coolify. They verify that the recovery kit excludes private identities/plaintext runtime credentials, verifies member checksums, extracts without overwriting existing recovery inputs, and rejects unsafe archive members. They also verify the retained restic staging boundary (new private leaf, exact confirmation, reviewed exclusions), plus the Coolify instance restore plan: fresh runtime credentials remain authoritative, the previous `APP_KEY` becomes only `APP_PREVIOUS_KEYS`, and the old `.env` is never copied wholesale.

The final M16 proof remains external V4 evidence. It must use real off-site M14/M15/Coolify-instance backups and a clean replacement Ubuntu 24.04 target; synthetic archives or local temporary directories are source validation only.
