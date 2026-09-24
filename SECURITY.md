# Security policy

Solo VPS is **PRE-ALPHA infrastructure automation**. A defect here can affect administrative access, network exposure, secrets, backups, or recovery, so security reports should not be handled like ordinary bug reports.

## Supported versions

| Source / release | Security support |
| --- | --- |
| Current PRE-ALPHA project source | Best-effort triage only |
| Tagged stable releases | None exist yet |
| Old snapshots / legacy documents | Not supported as executable production guidance |

There is no production-support SLA. Security fixes may require changing an unstable interface while the project is PRE-ALPHA.

## What to report privately

Examples include:

- a path that can lock out the administrator despite the documented safety gates;
- unintended public exposure of SSH, Docker, PostgreSQL, Redis, Coolify management ports, or other services;
- a way for secrets, private keys, SOPS/age identities, registry credentials, or backup credentials to enter Git, logs, command output, or public examples;
- privilege escalation caused by the Ansible roles, sudo policy, Docker access, CI workflow, or generated configuration;
- integrity problems in pinned release/checksum handling;
- backup or restore behavior that can silently lose or corrupt data;
- a CI/GHCR template flaw that grants broader credentials or write permissions than documented.

Application-specific vulnerabilities in software merely deployed through Coolify are normally owned by that application, not by Solo VPS, unless the vulnerability is caused by a Solo VPS template or platform contract.

## How to report

**Do not put exploit details, live IP addresses, tokens, private keys, credentials, or production configuration in a public issue.**

When the public GitHub repository has **Private vulnerability reporting** enabled, use GitHub's **Report a vulnerability** flow so the report reaches maintainers privately.

The current source archive does not define a maintainer email and cannot prove that GitHub private vulnerability reporting is enabled. Until the repository owner configures a private channel, open only a minimal public issue asking for a private security contact; do not include vulnerability details in that issue.

A useful private report should contain:

- affected file/workflow and project revision;
- expected versus observed behavior;
- minimal reproduction steps using disposable/non-production infrastructure where possible;
- security impact and preconditions;
- whether access, data, or recovery may already be affected;
- a suggested mitigation or rollback, if known.

## Disclosure and remediation

Please allow maintainers time to reproduce and mitigate the issue before public disclosure. Because the project is PRE-ALPHA, no fixed response or remediation timeline is promised.

For access/data-critical findings, remediation should preserve the project's safety model:

```text
current state
-> failure mode
-> recovery path
-> candidate fix
-> validation
-> disclosure
```

A security fix is not considered proven merely because source validation passes. Host/security changes should receive proportional disposable-target evidence before being described as operationally verified.

## Administrative SSH identity boundary

Solo VPS deliberately separates two SSH identities during onboarding:

- `admin.ssh_public_key_file` is the controller/automation public key used by the repository-managed Ansible path; on a same-VPS controller its matching private key may exist on that VPS;
- `admin.human_ssh_public_key` is the public key for the operator's normal external workstation; its matching private key must remain on that workstation.

Only public-key material is accepted by the canonical `human-admin-key-*` helpers. Same-VPS access preparation refuses to treat the VPS-created automation key as the human recovery identity. SSH hardening requires both a provider-recovery acknowledgement and an explicit fresh workstation-admin-login acknowledgement before root/password fallbacks may be restricted.

A successful same-VPS Ansible connection is therefore **not** evidence that external human recovery access works. Do not copy a human private key to the VPS, put it in SOPS, or repair this boundary with undocumented `authorized_keys` edits.

## Repository CI boundary

The public `Repository CI / fast-source` workflow is intentionally a **source/QA gate**, not a deployment workflow. It uses only `contents: read`, does not consume repository/environment deployment secrets, keeps generated controller state in the disposable runner temporary directory, and does not contact the maintained VPS or Coolify control plane.

The workflow also avoids third-party `uses:` actions in this first gate. The runner-provided read-only `github.token` exists only in the checkout step, is passed to one `git fetch` through a process-scoped HTTP extra-header, is not written into the Git remote configuration, and is unset before repository code runs. The job then checks that the detached checkout equals `GITHUB_SHA` and executes `make ci-fast`. Production GHCR/Coolify deployment remains a separate M11 application-delivery boundary with its own credentials and restrictions.

Do not add VPS SSH keys, Coolify API tokens, registry write credentials, age private identities, or backup credentials to the repository fast gate merely to make source CI more convenient. Runtime/disposable integration must use a separately reviewed boundary.

## Public hardening discussion

Non-sensitive hardening ideas, threat-model questions, documentation defects, and defense-in-depth suggestions may be discussed publicly when they do not disclose an exploitable vulnerability or real infrastructure details.
