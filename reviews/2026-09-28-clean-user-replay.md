# Independent clean-user core replay — 2026-09-28

## Scope and source

- Target class: clean Ubuntu 24.04 test VPS.
- The owner independently followed the rendered public Quick Start and first-application guide, without maintainer assistance.
- The owner supplied server `git log` identifying the checkout as `0fdba7fadac0522ae47e51a84ead9fdf9030a097`.
- The owner reported a working HTTPS demo, an application update and automatic GitHub Actions / GHCR / Coolify deployment.
- Raw operator transcripts remain outside the public repository. This record contains only the relevant outcomes.

## Logged results

The initial transcripts show host bootstrap and apply, administrator/SSH hardening, Coolify `4.3.21` installation, then `make verify-coolify`, `make verify` and `make audit`. Their Ansible recaps have `unreachable=0` and `failed=0`.

The owner then supplied the separate second `make platform` transcript. Its final result is:

```text
solo_vps : ok=80 changed=0 unreachable=0 failed=0 skipped=195 rescued=0 ignored=0
PASS Solo VPS Coolify bootstrap
```

This closes the required platform idempotency result. It does not claim that every task ran on the second invocation: an already completed installation correctly skips installation tasks.

## Candidate equivalence and validation level

The reviewed diff from `0fdba7f` through `659a5a7` changes only documentation, documentation CSS, release metadata and one documentation-validator test. Ansible, operational scripts, supported pins, Make targets and GitHub workflows are unchanged. The guide changes preserve the executed operational route.

The core public installation/application route therefore has **V4 clean-user evidence**. Optional off-site backup, recovery and observability capabilities retain their separate V3 evidence; this core replay does not promote them to V4 or provide a production guarantee.

Review every later candidate diff for operational equivalence. Operational changes require the relevant clean-host evidence to be repeated. Hosted checks, final history/archive scanning, the dated changelog, release dry-run and approval of the tag/Release remain separate publication gates.
