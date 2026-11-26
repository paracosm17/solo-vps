# Coolify 4.7.8 — bounded production V5 (2026-11-26)

## Source and environment

- Exact tested Solo VPS runtime source: `e159635615d106645c23744c112ae6f79d96b046`, clean detached checkout, PR [#41](https://github.com/paracosm17/solo-vps/pull/41). Existing maintained production VPS, not a fresh or disposable target.
- Exact managed transition **4.7.3 → 4.7.8**; Docker Engine 29.9.3, Compose 5.7.1, Ubuntu 24.04 x86_64.
- Integration fingerprint `sha256:2c5181882e4b541ed8827a0f7db3fa502018fccf6356204387d74b1b1cdd89ad`; unchanged Sentinel 1.1.5 and Traefik 3.7.16. See [source review](2026-11-26-coolify-478-source.md) for artifact provenance and migration risks.
- The exact tested runtime source passed hosted [fast-source](https://github.com/paracosm17/solo-vps/actions/runs/45744682711) and [strict docs build](https://github.com/paracosm17/solo-vps/actions/runs/45744682800). The evidence-only follow-up must pass its own checks.

## Preparation and guarded upgrade

- Operator updated the existing clean checkout; `make setup` preserved external persistent config, inventory and existing identity. `make validate`, `make doctor` and `make updates-plan` passed. Firewall verification: `ok=20 changed=0 failed=0`.
- Read-only `make coolify-upgrade-preflight` passed: `ok=41 changed=0 failed=0`, observed 4.7.3, target 4.7.8, mutation=false, HTTPS Sentinel trust checks passed.
- An early `make verify-coolify` before runtime mutation correctly refused the old managed 4.7.3 marker against the new source pin. The Docker inventory still showed the healthy origin; no code or marker changes were required. The operator then invoked the explicitly confirmed upgrade.
- The mandatory local control-plane checkpoint was created and validated before mutation. The operator chose not to create additional backup copies for this update; no fresh off-site or application recovery evidence is claimed.
- All three exact tagged artifacts downloaded and matched their committed checksums. Only the production Compose artifact changed; retained identities and `AUTOUPDATE=false` preserved. Staged and promoted Compose validation passed.
- Two initial readiness retries were transient; the upgrade continued and completed successfully. The new dependency health gate passed for both PostgreSQL and Redis before committing the target marker.
- Exact Coolify 4.7.8 image healthy; loopback health, Reverb and terminal endpoints each returned HTTP 200. The managed marker was updated, and staging and transaction marker removed only after verification.

## Observed results

| Check | Result |
| --- | --- |
| Guarded upgrade | PASS: ok=141 changed=10 failed=0 skipped=5 |
| make verify-coolify | PASS: ok=57 changed=0 failed=0 |
| make verify | PASS: ok=164 changed=0 failed=0 |
| make audit | PASS: ok=96 changed=0 failed=0 |
| Coolify / PostgreSQL / Redis | 4.7.8 / 15-alpine / 7-alpine, all healthy |
| Sentinel / Traefik | 1.1.5 / 3.7.16, healthy |
| Containers | 17/17 running; application containers retained their pre-upgrade uptime and displayed image references |
| Management ports | 8000/6001/6002 loopback-only; configured controller probes not reachable |
| Public edge | TCP 22/80/443, no unexpected publications or public database ports |
| Audit | No clear violations, warnings=[] |
| Failed systemd units | None |
| Root filesystem | 49% used |
| Managed marker / pending transaction | coolify_version=4.7.8 / absent |
| OS maintenance | reboot_required=true; automatic reboot disabled |

## Evidence boundaries

This is **bounded V5 for the observed managed platform upgrade and read-only host/control-plane checks**. Running containers and healthy control-plane checks do not establish application-level functionality, persistent-volume data integrity on redeploy, or a successful new API/CI deployment. Public dashboard login, Sentinel UI In Sync, actual application HTTPS/business transactions, provider rescue access and isolated recovery/forward-resume exercise are not demonstrated by these logs. The optional off-site repository is NOT_CONFIGURED and neither backup freshness nor application database restore was checked. The retained checkpoint is local to the VPS and is not an independent restore test. No new disposable V3 or clean-install V4 is claimed. Plan the pending OS reboot separately; do not conflate it with the Coolify update.

The PR stays unmerged until the owner confirms application checks and release approval; exact-candidate release QA, clean dry run, history/secret scans and protected-main/Pages checks still apply. Raw logs, server/user identifiers, addresses, checkpoint names and credentials are excluded from public evidence.
