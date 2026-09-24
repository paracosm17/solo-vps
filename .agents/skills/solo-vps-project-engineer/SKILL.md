---
name: solo-vps-project-engineer
description: Implement or fix a bounded Solo VPS repository change. Use for Ansible, scripts, Make targets, CI/CD, Coolify integration, security, backup/recovery, observability, or related tests.
---

# Solo VPS project engineer

Use this skill when the user asks to change implementation in this repository.

## Workflow

1. Define the requested outcome and inspect only the relevant code, tests, and source-of-truth docs.
2. If the change crosses architecture/ownership boundaries or has multiple plausible designs, ask the `architect` agent for a compact design packet before editing.
3. Implement the smallest coherent change. Keep unrelated files untouched.
4. Run the narrowest meaningful validation for the behavior changed. Escalate to broader checks only when failures, cross-cutting impact, or release scope justify it.
5. Update user or architecture documentation only when the supported behavior or contract changed.
6. Update `ROADMAP.md` only when development state, a blocker, validation level, or the next action materially changed. Use the `solo-vps-roadmap` skill for that update.
7. For nontrivial or high-risk diffs, ask the `reviewer` agent for an independent read-only review and fix material findings.
8. Report changed behavior, validation run, and any runtime evidence still missing.

## Project boundaries

Load `PROJECT_PASSPORT.md` when changing product/architecture boundaries. Load `README.md` when changing supported public behavior. Load the relevant ADR or operations document when changing that subsystem.

Preserve these defaults unless the task explicitly changes them:

- one maintained Ubuntu 24.04 application VPS;
- Ansible owns host configuration; Coolify owns applications/services/reverse proxy/TLS/runtime app secrets;
- GitHub Actions builds/tests, GHCR stores immutable images, Coolify deploys them;
- SOPS + age own infrastructure/recovery secret files; the age private identity stays off the VPS by default;
- restic/off-site storage and logical database recovery are separate recovery layers;
- optional observability/networking/UI modules do not gate the core Quick Start.

## Safety

Repository edits and local tests are authorized by a normal implementation request. External writes are not implied.

Do not run mutating VPS, Coolify, storage, GitHub, registry, release, retention/prune, or recovery commands unless the user explicitly asked for that external action. For such work, use `solo-vps-runtime-evidence` first.

Never place real operator identifiers, credentials, private keys, tokens, or secret values into tracked files.

## Validation

Prefer existing deterministic targets over ad-hoc checks. Examples:

- lifecycle: `make validate-platform-lifecycle` and `make test-platform-lifecycle`;
- docs governance: `make validate-documentation-governance` and its test target;
- recovery: `make validate-disaster-recovery` and `make test-disaster-recovery`;
- release process: `make validate-release-process` and `make test-release-process`;
- cross-cutting source work: `make ci-fast-source` when warranted.

Do not treat a passing source check as runtime proof. State the achieved evidence level honestly.
