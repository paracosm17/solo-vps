# Clean Ubuntu host checkpoint — 2026-09-10

## Scope and evidence

An operator reimaged the test VPS with Ubuntu 24.04.4 LTS x86_64 and used the ZIP archive prepared from Solo VPS commit `e2bd1feec5258d4390c630fa6f1fc52ab4c12a46`. Revision attribution follows the archive handoff; the supplied target transcript does not contain an independent Git revision or archive checksum check.

Three operator-supplied transcripts cover package preparation/runtime setup, first host apply, and SSH hardening. Separate workstation output demonstrates managed-admin login after hardening, the transferred source workspace, and root SSH rejection. Raw logs and installation-specific identifiers remain outside the repository.

This is **V3 integration evidence for the completed host/admin/SSH stages of an ongoing clean-target replay**. It does not complete V4 or guarantee other providers, architectures, revisions, or unexecuted stages.

## Confirmed results

| Stage | Observed result |
| --- | --- |
| Prerequisites | APT index refresh followed by installation of Make, Git and unzip succeeded; archive extracted. Git clone was not exercised. |
| First `make setup` | Controller prerequisites, a new automation SSH identity, pinned Ansible runtime and persistent state initialized successfully. |
| Human admin key | Workstation public-key helper reported success and `private_key_received: false`; managed verification subsequently accepted the configured human key. |
| First `make apply` | Completed with `PASS Solo VPS host apply`; baseline recap: `ok=115 changed=19 unreachable=0 failed=0`. |
| Admin handoff | Created the managed administrator's workspace, persistent config/inventory and automation identity; installed runtime under that account. |
| Pre-platform verification | Aggregate verify: `ok=91 changed=0 failed=0`; audit: `ok=82 changed=0 failed=0`. SSH was correctly reported pending before activation. |
| Sudo through automation | Preflight reported passwordless sudo and the users verifier successfully executed its non-interactive root-privilege probe. |
| Missing hardening confirmations | A pasted command containing blank lines failed the confirmation gate before hardening; this attempt was not a successful secure run. |
| Corrected `make secure` | Completed with `PASS Solo VPS SSH security transition`; activation: `ok=47 changed=4 failed=0`; final SSH verification: `ok=41 changed=0 failed=0`. |
| Workstation reconnect | Operator output shows managed-admin login after hardening and root login rejected with `Permission denied (publickey)`. |

## Observations and limits

- Fresh-image package indexes must be refreshed before installing prerequisites. The canonical Git path already documents this; the temporary ZIP path also needs unzip.
- Blank lines introduced while copying/pasting a continued shell command prevent both confirmations from reaching Make. User-facing hardening examples now use one physical line; the existing copy button reads source text (`textContent`) instead of layout-derived `innerText`, which can introduce extra line breaks around highlighted line spans. The original operator clipboard/terminal path was not captured.
- The operator tried `sudo -t` without its argument, then `sudo -v`, which requested a password. Neither is the documented command-execution probe. Direct workstation-session `sudo -n id -u` output is still pending, despite the successful automated probes. The sudoers `verifypw` policy can require authentication for `sudo -v` even when a matching command rule permits passwordless execution.
- The human-key helper still suggests low-level `make bootstrap`; the supported next step in the Quick Start is `make apply`. This is an observed CLI guidance gap, not an additional required command.
- Login banners list pending security updates. Successful unattended-upgrades configuration is not evidence that all existing security updates have been installed.
- Earlier maintained-host reruns/reboot passed, but they do not establish idempotency or reboot behavior for this newly reimaged target.

## Next checkpoint

From a fresh managed-admin workstation SSH session, confirm `sudo -n id -u` prints `0`. Then run the first `make platform`, `make verify`, `make audit`, repeat `make platform`, and repeat verification/audit. Preserve the complete logs and stop before Coolify first-user registration/application setup. Stop at any unexpected failure rather than continuing the command sequence.

The next section supersedes this initial handoff. Upgrade/checkpoint recovery and optional off-site restore retain separate acceptance.

## First platform run and proxy audit defect

A subsequent operator transcript confirms direct workstation-session `sudo -n id -u` returned `0`. First `make platform` completed with installation recap `ok=120 changed=19 failed=0`, followed by Coolify verification `ok=48 changed=0 failed=0`. The transient application health retry resolved successfully. Aggregate `make verify` completed with `ok=145 changed=0 failed=0`.

`make audit` then correctly failed (`ok=88 changed=0 failed=1`) on public TCP 8080 and UDP 443 publications for IPv4 and IPv6. Docker Engine reported 29.8.0. The previous runtime verifier checked the main/realtime containers but omitted the separate proxy edge, so its PASS did not establish the full public-port policy.

The publications match [Coolify v4.1.2's default Traefik generator](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php). Its [proxy start action](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Actions/Proxy/StartProxy.php) runs Compose in the proxy directory without explicit file selection. Solo VPS now installs `docker-compose.override.yml` before first startup, using `ports: !override` to retain only TCP 80/443. Base routing/command settings remain Coolify-owned. HTTP/3 transport is not published in this profile.

`make platform` reconciles an already-running proxy only when ports drift, without pulling an image or restarting application containers. It refuses recreation if the saved Compose model changes the image or omits attached application networks. An unrecognized operator override is preserved and requires review. Read-only Coolify verification now checks the persistent override and an activated proxy's identity, health and configured/actual ports. The audit allowlist is unchanged.

**Local validation:** unit/source tests and an official checksum-verified Docker Compose v2.39.4 configuration test cover default-file discovery, base-file regeneration, removal of extra ports and retention of unrelated settings. YAML lint and existing Coolify/lifecycle source validators pass. Docker container recreation, Linux Ansible execution and real corrected-VPS acceptance remain pending.

The following successful retest supersedes this failed-audit checkpoint.

## Proxy repair and unchanged second pass — confirmed

Two later operator transcripts show execution of the corrected proxy tasks after replacing the source archive (the target ZIP was renamed; no target checksum was captured).

| Run | Platform installation/reconciliation | Separate Coolify verification | Aggregate verify | Audit |
| --- | --- | --- | --- | --- |
| Apply correction | `ok=75 changed=2 failed=0` | `ok=52 changed=0 failed=0` | `ok=149 changed=0 failed=0` | `ok=87 changed=0 failed=0` |
| Repeat unchanged | `ok=72 changed=0 failed=0` | `ok=52 changed=0 failed=0` | `ok=149 changed=0 failed=0` | `ok=87 changed=0 failed=0` |

Every recap reports `unreachable=0`. The two mutations are the persistent proxy override installation and recreation of the existing proxy. The image/network preservation guard passed before recreation. The repeated run skipped recreation. Both audits report `docker_published_ports: PASS` and an empty warnings list; only TCP 80/443 are publicly published by Docker, with management/realtime ports remaining on loopback. Proxy health and persistent-policy checks also pass.

This establishes **V3 real Linux Ansible execution of the proxy repair, healthy runtime, strict audit and unchanged platform rerun** on the reimaged target. It does not prove a fresh installation with the override already present, a later Coolify UI proxy restart, external port scanning, reboot, recovery or end-to-end V4. The operator has not opened Coolify yet.

**Next:** open the private workstation tunnel on local TCP 18000 (leaving 8000 for documentation), register the first Coolify administrator and inspect the existing localhost server/proxy. Stop before creating an application. Then exercise the revised first-app/CI flow; host rerun/reboot, interruption/resume, negative health checks and upgrade/recovery retain separate acceptance.

## First account and server UI — confirmed

A subsequent operator transcript contains successful `make verify-coolify` (`ok=52 changed=0 failed=0`), `make audit` (`ok=87 changed=0 failed=0`) and `make platform` (installation/reconciliation `ok=72 changed=0 failed=0`, verification `ok=52 changed=0 failed=0`). All recaps report `unreachable=0`; the audit has an empty warnings list. Audit limitations such as off-site restore and external scanning remain explicitly unavailable, not newly validated.

The operator reports registering the first Coolify administrator through the local tunnel. The supplied Coolify 4.1.2 screenshot shows the existing localhost server as reachable and validated, with the configured non-root user and **Proxy Running**. No additional server or Docker installation is needed at this point; **Skip Setup** is the intended handoff for this already-provisioned state. The screenshot also shows **Sentinel Out Of Sync**. The supplied evidence does not identify its cause or demonstrate working Sentinel metrics/heartbeat.

This extends partial V3 through registration and the server UI. It does not establish dashboard HTTPS, live application logs, application deployment or full V4. The operator's feedback identifies missing onboarding instructions and an interrupted Quick Start journey; the EN/RU rewrite is explicitly queued in ROADMAP, with the product requirement in PROJECT_PASSPORT.

**Next:** configure the dashboard HTTPS domain and confirm browser login, then proceed with the revised reference application, Actions/GHCR, initial deployment, subsequent automatic deployment, runtime ENV and live logs. Maintainer reruns and release-evidence checks stay separate from this normal user handoff.

## Dashboard HTTPS — operator-confirmed

The operator confirms the dashboard works through its HTTPS hostname after setting the instance URL. This is operator-reported browser evidence; no independent certificate inspection or authenticated browser replay was performed by the reviewer. Application deployment, realtime logs and Sentinel sync remain unverified for this target.

The UI handoff exposed a documentation ambiguity: **Settings** in the main sidebar configures the dashboard URL, while **Servers → localhost → Configuration → General → IP Address/Domain** configures the SSH destination. The operator did not save the proposed server-address change. Guidance clarified preserving the existing SSH target and entering the HTTPS URL under instance Settings. This distinction is included in the queued Quick Start acceptance criteria.

**Next:** publish the reference app's first GHCR image with deployment disabled, then create its Coolify Docker Image resource and continue through automatic delivery, runtime ENV and logs.

## Initial application CI and image publication — confirmed

The workstation transcript ends with a successful initial `main` push of the generated standalone app to a new demonstration repository. An earlier attempt against an older repository was rejected by its required-PR/status-check rules. Intermediate directory changes and a pre-existing destination caused local setup errors; the final starter generation, commit and push succeeded. The transcript does not explain every intermediate filesystem change, so no starter data-loss defect is inferred from it.

The supplied GitHub Actions screenshot shows green application tests, application migration preflight, main-image publication and published-image digest verification. PR image building and Coolify deployment are skipped, as expected for the initial main push with CD disabled. The operator reports the package is already public. The supplied immutable reference passes the offline Coolify 4.1.2 image-field handoff validator; this local check does not independently pull the image.

This establishes partial V3 for the revised application's initial hosted CI/publication path. It does not prove first application deployment, PR delivery, automatic CD, runtime ENV, live logs or full V4, and does not close the separate Solo VPS repository hosted-CI gate. Repository identifiers and the actual image digest stay outside public evidence.

**Next:** create a Coolify Docker Image resource on localhost, use the validated image/hash fields, expose internal port 8080 without host port mappings, configure application HTTPS and deploy. Confirm `/healthz` and the initial application response before enabling CD.

## First immutable application deployment and live logs — confirmed

Operator-supplied deployment output starts with the same immutable image reference previously published by Actions and completes the rolling update successfully. The Coolify screenshot shows **Running (healthy)**, the intended repository/hash fields, internal port 8080 and empty host port mappings. The generic message about pulling latest images does not change the explicit digest reference in the deployment log.

The operator reports the HTTPS application response with the expected service, version 1, OK status and default message, and an OK response from `/healthz`. Supplied runtime logs show the process listening on port 8080, periodic internal health checks returning HTTP 200, and proxied application/health requests also returning HTTP 200. This demonstrates initial runtime health, browser HTTPS access and visible live request logs; no separate external port scan or reviewer-operated browser replay is claimed.

This extends partial V3 through the revised app's first manual deployment. Automatic CI deployment, PR/version update, runtime ENV modification, failed-candidate recovery and full V4 remain pending. Actual resource identifiers, domain and image digest stay outside public evidence.

**Next:** configure and verify the dedicated restricted CI SSH transport, populate the GitHub production environment and Coolify API credentials, then enable CD and prove a subsequent PR/main deployment followed by runtime ENV changes.

## Dedicated CI transport — confirmed

The next supplied operator transcript confirms creation of a dedicated Ed25519 CI key on the workstation and upload of its public part. Applying the CI transport completes with `failed=0`, `unreachable=0`; the included verification confirms key-only, sessionless local forwarding to `127.0.0.1:8000`. A subsequent administrator SSH login succeeds.

The workstation key path differs from the intended `.ssh` directory because the pasted command omitted a separator. This does not invalidate the key; the rewritten PowerShell instructions use `Join-Path`. No private key or operator path is recorded here.

This adds bounded V3 transport evidence. Coolify API credentials, GitHub environment population, subsequent automatic delivery and runtime ENV changes are not yet confirmed. The operator paused the replay to request a complete two-part runbook; resume at those remaining application settings without recreating the already installed key/account.
