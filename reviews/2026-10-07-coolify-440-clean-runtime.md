# Coolify 4.4.0 controlled fresh-host replay — 2026-10-07

## Scope and revisions

Owner-authorized disposable Ubuntu 24.04.4 x86_64 VPS, reset by the owner before this run. Baseline inspection found no Docker, Coolify, Solo VPS state or managed administrator. Production was excluded. Operator credentials and full logs stay in private, access-restricted VPS state; this record contains no operator identifiers or secrets.

The replay began at `1d475c15d5042af942e883e92e485e051d15c13b`. Fresh bootstrap exposed a proxy-policy failure, corrected in `4877944`, standalone firewall facts in `0992301`, bounded forwarding/effective-systemd/timezone verification in `e416065`, and Docker boot-order coverage in `374dc31`. Final runtime checks used `374dc31`. The interrupted platform install resumed with its original pending marker and generated identities. This is **V3 controlled fresh-host integration with corrected-source resume**, not an uninterrupted exact-revision V4 user walkthrough or production V5 evidence.

## Results

| Check | Result |
| --- | --- |
| Clean host baseline | No Docker, Coolify, managed admin or existing installation state |
| Workstation administrator key | Public key supplied through the documented stdin command; private key stayed on the workstation |
| Host baseline and hardening | `make apply` and `make secure` passed; fresh admin SSH/sudo worked and fresh root key login was denied |
| Recovery access | Owner confirmed provider console/rescue before access hardening |
| Interrupted first install | Native main container became healthy; strict proxy verification refused unintended 8080/TCP and 443/UDP publications; pending marker retained |
| Corrected install resume | Passed at `0992301`: `ok=107 changed=8 failed=0`; original generated identities and transaction retained |
| First administrator and HTTPS onboarding | Native Fortify registration and native settings/actions used by a private test helper; not a browser-form walkthrough |
| Versions | Coolify 4.4.0 and native Sentinel 1.0.2; management endpoints private |
| Full platform verification | `make verify-coolify` passed after onboarding; final full post-reboot `make verify`: `ok=163 changed=0 failed=0` |
| Native proxy restart | Native `StartProxy` action passed; saved policy remained TCP 80/443 only and the policy helper was a read-only no-op afterwards |
| Ingress packet proof | Task-owned TCP 8080 and UDP 443 listeners responded locally; workstation probes were blocked and exact DROP counters increased by 4 and 3 respectively both before and after reboot; test containers removed |
| UFW reload | Guard remained valid in IPv4 and IPv6 rulesets; read-only check reported `changed=false` |
| Shared forwarding policy | Only the bounded guard hook is ordered first; pre-existing shared `DOCKER-USER` jumps are preserved |
| API token | One team-scoped read/write/deploy token, without root ability, created and used |
| Immutable application | Public CI-built GHCR digest deployed and public HTTPS `/healthz` returned success |
| Supported deployment helper | `--check` and `--apply` passed with the single token |
| Failed candidate | Deliberately nonexistent digest returned `DEPLOY_FAILED_ROLLBACK_OK`; known-good application restored |
| Reverb | Actual local websocket handshake returned HTTP 101 and `pusher:connection_established` |
| Host rerun | `make apply` passed, including its full verify/audit stages |
| Platform rerun | At `e416065`: `ok=81 changed=0 failed=0` |
| Audit | Passed before and after reboot; final `ok=96 changed=0 failed=0` |
| Reboot recovery | Passed twice; fresh admin SSH/sudo, root denial, origin HTTPS and Reverb recovered; effective Docker `ExecStartPre` ran with `ignore_errors=no`, exit 0; guard packet proof repeated after the corrected second boot |
| Credential cleanup | Task API token revoked and token-bearing credentials/log deleted; generated test administrator login retained only in a root-readable file |

## Failures and corrections

Coolify 4.4.0 starts its proxy with an explicit `-f docker-compose.yml`, so an implicit Compose override did not control first-start publications. Its native database-backed saved proxy configuration is now authoritative. The policy helper changes only port declarations, preserves the rest of the operator YAML byte-for-byte, and persists via native Save/Start actions. The firewall installs a bounded external-interface guard before Docker starts workloads, including on boot. Unknown ownership/configuration fails closed.

Standalone firewall commands did not gather default-route interface facts; they now gather only the needed network facts when absent. Independent review tightened effective systemd verification so the guard and `ignore_errors=no` must belong to the same command entry, and avoided moving shared forwarding rules.

The first reboot recovered SSH and HTTPS after a startup interval, but the guard verifier rejected Docker's normal prepended `FORWARD → DOCKER-USER` hook. That chain already entered the bounded guard first. The corrected verifier accepts this exact transitive path after checking the child guard, preserving unrelated forwarding rules; an independent reviewer and a second cold boot plus real packet proof passed. Boot journals were retained privately.

The host verifier compared the literal `UTC` symlink target against Ubuntu's resolved `Etc/UTC`. It now compares resolved zoneinfo targets while separately requiring the configured timezone name.

The disposable demo's first deployment used Coolify's generated HTTP healthcheck, requiring curl/wget absent from that image. Turning off the generated check retained its own Python Docker HEALTHCHECK; the next deploy was healthy. This was test setup correction, not a platform bypass. Native registration, HTTPS settings, API enablement and token creation were performed by a private helper rather than browser forms.

## Remaining boundary

IPv6 firewall state was checked, but external IPv6 packets were not tested. Optional backup/storage/monitoring workflows and an independent browser walkthrough retain separate evidence. Production still needs its own checkpoint/backup prerequisites and owner-authorized execution. No release or tag was created.

## Source validation

Local `ci-fast-source`, strict documentation build, focused proxy/firewall/verification tests and production-profile `qa-static` passed. Final boot-order coverage has targeted unit evidence and green hosted `fast-source`/documentation build at `374dc31`. Documentation/evidence-only follow-up retains the operational code.
