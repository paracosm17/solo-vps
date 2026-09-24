# Clean Ubuntu 24.04 test runbook

> **Maintainer evidence runbook:** this document intentionally exposes lower-level onboarding/bootstrap/handoff targets so release testing can prove each boundary independently. First-time users should follow the five-command README lifecycle (`setup -> apply -> secure -> platform -> verify`) instead.

This is the PRE-ALPHA operator runbook for the first real Solo VPS integration pass. Use a **fresh disposable Ubuntu 24.04 LTS VPS** with provider console/rescue access. The goal is evidence and bug discovery, not production rollout.

Do not reuse a VPS that already contains Docker/Coolify/application data for this first pass.

For the automated CRIT-004 host-core version of the clean test, use `docs/disposable-clean-target.md`. That provider-neutral harness automates the critical bootstrap/SSH-hardening/verify/audit/idempotency sequence and retains sanitized evidence; this longer document remains the manual release-candidate runbook for broader platform/Coolify validation.

## Evidence rules

Record the exact command that failed and its output, but do **not** collect or paste:

- persistent `~/.local/share/solo-vps/config/config.yml` if it contains local infrastructure metadata you do not want to share;
- private SSH keys;
- `/data/coolify/source/.env` or generated secret values;
- age private identities, S3 credentials, restic passwords, application secrets;
- full `docker inspect` output if a future container configuration contains secret environment values.

Useful non-secret evidence includes Ansible task names/errors, `make doctor` output, `make verify`/`make audit` summaries, `docker ps -a`, selected `docker logs <container>`, `ss -ltnp`, package/service versions, and checksums of non-secret managed files.

## Phase 0 — First-run setup from a fresh root shell

The default guided flow for this PRE-ALPHA test starts exactly where a typical VPS starts: you have a fresh Ubuntu 24.04 LTS server and an initial `root` shell. Running the Solo VPS checkout on that same VPS is supported for this test. A separate controller remains supported, but it is not required for the standard path below.

### 0.1. Put the source on the machine and install GNU Make

Solo VPS cannot install anything before its Makefile can run. Therefore **GNU Make is the one unavoidable OS prerequisite** after the source has been placed on the machine:

```bash
apt-get update
apt-get install -y make
cd ~/solo-vps
```

If you use `git clone` to obtain the repository, `git` is also necessarily required before Solo VPS exists; install `git` together with `make`. If you upload/unpack an archive, only `make` is required manually.

Do **not** manually install Ansible, ansible-lint, yamllint, pip packages, Docker, or Coolify.

### 0.2. Let Solo VPS install its remaining controller prerequisites

Run:

```bash
make setup
```

`make setup` is local and mutating. On Ubuntu 24.04 it performs these standard first-run actions:

1. `apt-get update`;
2. installs `python3`, `python3-yaml`, `python3-venv`, `openssh-client`, and `ca-certificates`;
3. creates `~/.ssh/id_ed25519` + `.pub` **only if the default identity does not already exist**;
4. never overwrites an existing SSH identity;
5. installs pinned `ansible-core` and `community.general` under `~/.local/share/solo-vps/toolchain/` by default; developer lint/test tooling is separate.

Expected final lines include a successful SSH-key setup and successful pinned runtime/collection installation. If this command fails, stop here and record the exact output.

The generated key lives under `~/.ssh/`, **outside the repository**, so deleting/replacing `~/solo-vps` does not delete it.

### 0.3. Run source/controller QA before target mutation

```bash
make qa-tools
make validate
```

This maintainer-only step explicitly installs the QA environment. `make validate` then includes the exact-version check, yamllint, real Ansible syntax checks and ansible-lint. Normal onboarding and SSH handoff require only the runtime. Expected: the complete validation finishes PASS.

These checks do not provision the VPS. If the embedded QA layer fails, stop before bootstrap and record the exact error. You can rerun only that layer with `make qa-static` while debugging.

### 0.4. Create persistent state and configure the target

Run:

```bash
make init
make paths
```

This creates, if missing, persistent operator state outside the Git checkout and prints its paths. It never overwrites existing operator files. Edit the installation config only:

```bash
nano ~/.local/share/solo-vps/config/config.yml
```

For the standard fresh-VPS/root flow, the persistent `config.yml` contains:

```yaml
server:
  host: <REAL_VPS_IP_OR_HOSTNAME>
  hostname: example-vps
  timezone: UTC

admin:
  user: ops
  ssh_public_key_file: ~/.ssh/id_ed25519.pub
  human_ssh_public_key: ""
```

Generate the technical inventory from that config and the provider's initial SSH account:

```bash
make use-bootstrap SSH_USER=root
```

If the provider uses another initial account, substitute it (for example `SSH_USER=ubuntu`). The command copies `server.host` into `ansible_host`, so the VPS address has one human-edited source of truth.

Required human decisions at this point are only:

- the real VPS address;
- the hostname you want;
- the non-root admin username;
- whether you want to override the default `UTC` timezone;
- optional public backup metadata;
- the provider/bootstrap SSH username.

The default key created by `make setup` is the **automation/controller** identity. It is not the human recovery key. Before bootstrap, from the real workstation you will use after hardening, send only its public `.pub` line through the bootstrap SSH session:

```bash
cat ~/.ssh/id_ed25519.pub | ssh <provider-user>@<server> 'cd ~/solo-vps && make human-admin-key-stdin'
```

PowerShell equivalent:

```powershell
Get-Content -Raw "$HOME\.ssh\id_ed25519.pub" | ssh <provider-user>@<server> "cd ~/solo-vps && make human-admin-key-stdin"
```

If the project controller is already the workstation, use `make human-admin-key-file HUMAN_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub`. Never copy the private key to the VPS.

### 0.5. Prepare the initial SSH path

Run:

```bash
make prepare-access
```

This command has two modes:

- **Solo VPS is running on the VPS itself:** it recognizes that `server.host` is a local address, then idempotently adds the configured controller public key to the initial root `authorized_keys` and records the local VPS Ed25519 host key in root's `known_hosts`. This enables Ansible to SSH from the controller process back into the same VPS without weakening sshd policy.
- **Solo VPS is running on a separate controller:** it does not change local `authorized_keys`/`known_hosts`; the provider/bootstrap SSH identity must already work from that controller.

It never disables root login, changes passwords, edits `sshd_config`, or opens firewall ports.

If same-VPS detection cannot prove the target is local, it fails/no-ops rather than silently modifying the wrong account. Record the output instead of improvising access changes.

### 0.6. Run the first read-only target diagnosis

```bash
make doctor
```

Expected:

```text
local config/key/inventory checks  PASS
platform capability report         PASS/INFO for optional unconfigured features
remote preflight                    PASS
Ubuntu                              24.04 LTS
initial remote identity             root
root privilege                      direct-root
```

Do not run `make bootstrap` until `make doctor` passes.

### Updating the source checkout during the bug-fix loop

The source checkout is now disposable; controller/operator state is external. Before and after a source update, use:

```bash
cd ~/solo-vps
make paths
make validate
make doctor
```

The default state survives deletion, replacement, or `git pull` of `~/solo-vps`:

```text
~/.local/share/solo-vps/config/      config + one-VPS inventory
~/.local/share/solo-vps/toolchain/   pinned Ansible/QA runtime
~/.ssh/                              controller SSH identity
```

After `make admin-handoff` succeeds, reconnect as `admin.user` and update `/home/<admin.user>/solo-vps` (`~/solo-vps` in the admin shell). The admin account has its own external `~/.local/share/solo-vps/` state.

For an older PRE-ALPHA checkout that still contains `config/config.yml` or `ansible/inventories/local/hosts.yml`, run `make init` once before deleting the old checkout. It copies those legacy files to the external data root when destinations are absent and does not delete the source copies. Verify the printed paths/content before manual cleanup.

If an archive overlay is used during development, remember that overlay extraction does not remove stale source files. A final clean-VPS/release evidence run must still use a fresh checkout/archive extraction. Unlike the older layout, replacing the whole source directory no longer requires preserving `.venv`, config, or inventory inside it.

After replacing source:

```bash
make validate
make doctor
```

Rerun `make setup` only when the external pinned toolchain is absent/incompatible or the new release explicitly changes its pins; source replacement by itself does not delete that toolchain. `make init` is safe and idempotent, but is only needed when persistent config/inventory are absent or when migrating legacy checkout-local state.

Do **not** restart the whole VPS sequence merely because source code changed. Continue from the last successful checkpoint after rerunning the local gates and relevant read-only verification. If the previous failure occurred in a mutating phase, use that phase's recovery/idempotency guidance before continuing.


For an M5 firewall-verification fix after UFW itself has already converged, use the
focused read-only checkpoint first:

```bash
make validate
make verify-firewall
```

A wildcard listener outside `22/80/443` is diagnostic evidence, not an automatic M5
failure when UFW remains active, incoming policy is default-deny, and the exact UFW
allow set is still the configured SSH/edge set. The verifier prints `ss -lntp` evidence
so the owning process is visible without requiring a separate manual discovery step.
Only after `make verify-firewall` passes should the aggregate `make bootstrap` resume.

If a focused verifier failure occurs before the enforcing assertion because Ansible cannot resolve a derived fact, overlay the corrected source, rerun `make validate`, and repeat the same read-only `make verify-firewall` checkpoint. Do not rerun `make setup`, `make init`, or `make prepare-access` when persistent config/inventory/toolchain and SSH state are already present outside the checkout.

## Phase 1 — First host bootstrap

Keep the provider console/rescue path available.

```bash
make bootstrap
make verify
make audit
```

Expected after bootstrap:

```text
base system       PASS
admin identity    PASS
UFW baseline      PASS
security updates  PASS
Docker host       PASS
SSH hardening     still staged / not silently activated
Coolify           not installed yet
```

### If `make bootstrap` stops after partially applying the host

Do not manually undo already-applied Solo VPS state just because a later task or read-only verifier failed. Preserve the same external config/inventory under the Solo VPS data root, update the source, then run:

```bash
make validate
make doctor
make bootstrap
```

The external toolchain survives source replacement, so `make setup` is not required merely because the checkout changed. The host roles are designed for repeat application: already-converged tasks should remain `ok`, while the corrected phase continues from the managed state. If the rerun fails earlier than the original checkpoint or unexpectedly changes unrelated state, stop and record the full output instead of manually forcing the next phase.

If the previous failure was specifically inside the read-only M5 firewall verifier after UFW apply/reconnect succeeded, test the corrected verifier first:

```bash
make verify-firewall
```

Only after that focused read-only check passes, rerun the idempotent aggregate bootstrap:

```bash
make bootstrap
```

This avoids repeating unrelated diagnostics while still proving the aggregate path can resume safely.

If bootstrap stops during the first M7 Docker package install after the official repository source was written, do not install Docker manually. Overlay the corrected project revision, run `make validate`, then rerun the idempotent `make bootstrap`. M3-M6 should converge; M7 will refresh APT metadata after the Docker source exists, verify an official `docker-ce` candidate, and continue package installation. If the candidate gate fails, capture its `apt-cache policy docker-ce` evidence and stop instead of adding another repository or convenience installer manually.

After the first complete `make bootstrap` PASS, continue with:

```bash
make verify
make audit
```

A later dedicated second bootstrap run is still required for full clean-VPS idempotency evidence.

Record Docker/Compose versions:

```bash
ssh <bootstrap-user>@<server> 'sudo docker version --format "{{.Server.Version}}"; sudo docker compose version'
```

Record the M7 daemon baseline checksum before Coolify:

```bash
ssh <bootstrap-user>@<server> 'sudo sha256sum /etc/docker/daemon.json'
```

## Phase 2 — Prove the managed administrator path

Switch the technical inventory to the managed administrator without editing YAML by hand:

```bash
make use-admin
```

First prove the Ansible/controller path:

```bash
make doctor
make verify
```

Expected: the project can reconnect and obtain non-interactive passwordless sudo through `admin.user`.

Then prove the **human recovery path from a different machine**. If the controller is your laptop/workstation, this is naturally the same key. If the controller is the VPS itself, the automation key created on the VPS is not sufficient evidence because its private half never left the server.

From the workstation you will normally administer from:

```bash
# Create a workstation key only if you do not already have one.
test -f ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
ssh <admin.user>@<server>
```

If that external admin login does not work, **do not run SSH hardening**. Re-run the canonical `human-admin-key-stdin` helper through the still-open bootstrap/admin session, then `make bootstrap` to reconcile the managed admin keys and retry. Do not edit `authorized_keys` ad hoc. The private key stays on the workstation.

## Phase 3 — Staged SSH hardening

This phase is required for full M4/M9 access evidence, but only run it after confirming provider console/rescue access.

Keep the existing working SSH session open, then run:

```bash
SSH_HARDENING_CONFIRM=I_HAVE_VERIFIED_PROVIDER_RECOVERY \
SSH_HARDENING_ADMIN_LOGIN_CONFIRM=I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN \
make ssh-harden
make verify-ssh
make verify
make audit
```

For the standard same-VPS/root-first flow, `make ssh-harden` first runs `make admin-handoff` **before any sshd mutation**. That handoff creates `/home/<admin.user>/solo-vps` as a source-only checkout, copies config/inventory between persistent per-user data roots, excludes checkout-local tool/cache/legacy operator state, rebuilds the pinned QA/Ansible environment in the admin data root, requires the full `make validate` gate to pass there, creates that account's own controller SSH identity, prepares same-VPS access, and proves `make doctor` from the admin-owned workspace. A handoff failure aborts the hardening target while the root access path is still unchanged.

If SSH hardening was completed with an older revision that did not yet include this hook, run once from the retained root checkout:

```bash
make admin-handoff
```

From another fresh terminal, confirm admin login still works and switch the operator shell permanently:

```bash
ssh <admin.user>@<server>
cd ~/solo-vps
make doctor
```

Also confirm the old root SSH path is denied after hardening. Once the fresh admin login and admin-workspace doctor both pass, the standard flow no longer depends on the retained root shell; close it and run all later Solo VPS commands as `admin.user`.

If access breaks, use the recovery procedure in [`ssh-hardening.md`](ssh-hardening.md) through the provider console/rescue path before doing anything else.

## Phase 4 — Coolify readiness

From the admin-owned `~/solo-vps` workspace, with inventory still using `admin.user`:

```bash
make coolify-readiness
```

Expected: PASS with no mutation. Readiness must reject an existing `/data/coolify`, an existing `coolify` container, occupied management ports, Docker-daemon drift, insufficient resources, or an unsupported Compose version.

Immediately before installation, record again:

```bash
ssh <admin.user>@<server> 'sudo sha256sum /etc/docker/daemon.json; sudo ss -ltnp | grep -E ":(8000|6001|6002)\\b" || true'
```

Expected: the daemon checksum matches Phase 1 and 8000/6001/6002 are unused.

## Phase 5 — First Coolify installation

> **MUTATING:** this creates `/data/coolify`, a localhost SSH key/authorized-key entry, Docker network/volumes/containers, and target-local generated secrets.

```bash
make coolify
make verify-coolify
make verify
make audit

After Coolify is running, `make audit` must classify its loopback Docker publications from full structured Docker inspect JSON. Docker may display realtime ports as a compressed `6001-6002` range in `docker ps`; that presentation form is not an audit input. The audit summary must report separate normalized loopback bindings for 8000, 6001, and 6002; an empty `docker_bindings` list while those ports are visibly published is not acceptable evidence.
```

Expected:

```text
Coolify image      ghcr.io/coollabsio/coolify:4.1.2
health             healthy
8000               127.0.0.1 only
6001               127.0.0.1 only
6002               127.0.0.1 only
controller probe   direct TCP unavailable
daemon.json        still the exact M7 baseline
managed marker     /data/coolify/.solo-vps-managed exists only after verification
```

Record non-secret runtime state:

```bash
ssh <admin.user>@<server> 'sudo docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
ssh <admin.user>@<server> 'sudo sha256sum /etc/docker/daemon.json'
ssh <admin.user>@<server> 'sudo ss -ltnp | grep -E ":(8000|6001|6002)\\b" || true'
```

Do not print `/data/coolify/source/.env`.

## Phase 6 — Private first-run UI

Do **not** open public firewall rules for 8000/6001/6002. From the controller, keep this tunnel open:

```bash
ssh \
  -L 8000:127.0.0.1:8000 \
  -L 6001:127.0.0.1:6001 \
  -L 6002:127.0.0.1:6002 \
  <admin.user>@<server>
```

Open `http://127.0.0.1:8000` locally and complete the first Coolify account registration.

Inside Coolify, confirm the seeded localhost server is usable. The initial `id.<admin.user>@host.docker.internal` filename is only the production-seeder bootstrap form; after seeding, Coolify normalizes the imported key to `ssh_key@<uuid>`. The human-visible requirement is that the seeded localhost server still manages the host as `admin.user` after that normalization, without reopening root SSH.

From a machine that is **not** using the SSH tunnel, ports 8000/6001/6002 must not be reachable through the server's public address. The Ansible verifier already performs a controller-side direct TCP check, but an independent external check is valuable evidence.

## Phase 7 — Managed second run

Run the same command again:

```bash
make coolify
make verify-coolify
```

Expected: the managed marker causes installation/upgrade/secret generation to be skipped. The run may reconcile the documented non-root lifecycle path state on `/data`, `/data/coolify`, `/data/coolify/{applications,databases,services}`, the private `/data/coolify/backups` boundary, and `/data/coolify/proxy`. Verification performs real `admin.user` chdir probes for resource namespaces and proxy plus write/execute-without-read probes for the backup root. On a revision where that access contract is already converged, the run should be `changed=0`; it must not recreate the platform or change pinned source artifacts.

Record any changes. A first run after adopting a filesystem-boundary correction may change only the documented managed path objects; repeat `make coolify` once more and require `changed=0` before treating the managed path as converged.

## Phase 8 — Reboot and post-reboot verification

A reboot is part of the M7/M9 clean-target evidence. From the VPS:

```bash
sudo reboot
```

After the host returns and the admin SSH path works:

```bash
make doctor
make verify
make audit
make verify-coolify
```

Expected: Docker and Coolify return healthy, the admin/SSH/UFW/update baselines remain valid, management ports remain loopback-only, and `/etc/docker/daemon.json` remains unchanged.

## Failure handling

### Failure before `/data/coolify/.solo-vps-managed` exists

Do **not** bypass readiness by deleting `/data/coolify` on a real server. First capture the failed task and non-secret diagnostics (`docker ps -a`, relevant container logs, `ss -ltnp`, and the daemon-config checksum).

New Solo VPS first installs create `/data/coolify/.solo-vps-installing` before secret/platform mutation. A later `make coolify` may automatically resume **verification only** when that exact transaction marker exists; it does not rerun secret generation.

For a known interrupted first install created by an older revision before the transaction marker existed, use the explicit recovery gate only after reviewing that this `/data/coolify` came from that Solo VPS attempt:

```bash
COOLIFY_RECOVERY_CONFIRM=I_HAVE_REVIEWED_THE_PARTIAL_SOLO_VPS_INSTALL make coolify-recover
make verify-coolify
```

`make coolify-recover` does not delete state, regenerate runtime secrets, or replace the localhost SSH key. It verifies pinned artifacts, private file permissions, the Coolify network, pinned image/autoupdate settings, current container health, loopback-only publishes, controller-side unreachability, and the unchanged M7 Docker daemon baseline. For the localhost SSH identity it accepts exactly one safe lifecycle state: the pre-seed `id.<admin.user>@host.docker.internal` key or one post-seed `ssh_key@<uuid>` key; the selected key must retain private permissions/ownership and its derived public half must already exist in `admin.user`'s `authorized_keys`. It writes the managed marker only after all checks pass. If recovery fails, stop and report the evidence; for a disposable test VPS, a clean rebuild remains the fallback.

### Access failure after SSH hardening

Use provider console/rescue and follow [`ssh-hardening.md`](ssh-hardening.md). Do not weaken unrelated firewall/Docker settings as a workaround.

## Bug report bundle

For each problem, send:

```text
Phase:
Command:
Exact failed Ansible task / error:
Expected behavior:
Actual behavior:
Fresh Ubuntu 24.04 image/provider:
Architecture (amd64/arm64):
Initial bootstrap SSH user:
Managed admin user:
Docker version:
Compose version:
Did provider console/rescue work?:
Did /data/coolify/.solo-vps-managed exist?:
Did /etc/docker/daemon.json checksum change?:
Relevant non-secret docker ps / logs / ss output:
Was this first run, second run, or post-reboot?:
```

Never include private keys or generated `.env` values in the report.

## PASS criteria for the first test cycle

The first integration cycle is successful when:

```text
fresh Ubuntu 24.04
→ doctor
→ bootstrap
→ verify/audit
→ admin.user fresh login + sudo
→ staged SSH hardening + fresh admin reconnect + root denial
→ Coolify readiness
→ pinned Coolify install
→ private tunnel registration
→ localhost server usable as admin.user
→ direct management ports unavailable publicly
→ managed Coolify run converges the bounded integration-access contract, then a repeat is changed=0
→ reboot
→ verify/audit/verify-coolify still PASS
```

This proves the core host-to-Coolify path. It does **not** yet prove M10 domain/TLS deployment, hosted GHCR delivery, off-site backups, database restore, or disaster recovery.
