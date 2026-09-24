# Contributing to Solo VPS

Solo VPS is a **PRE-ALPHA** infrastructure project. Contributions should make the fresh-VPS-to-recovery path simpler, safer, more reproducible, or easier to verify without adding unnecessary platform complexity.

## License

Solo VPS is distributed under the **Apache License 2.0**. See [`LICENSE`](LICENSE) and [`docs/license-choice.md`](docs/license-choice.md).

Code or documentation submitted for inclusion must be compatible with distribution under Apache-2.0. Do not submit material you do not have the right to contribute, and do not add a custom/dual license to a subsystem without a separate owner decision.

## Before changing code

Read these sources in order:

1. [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md) — product and accepted architecture boundaries;
2. [`.agents/skills/solo-vps-project-engineer/ROADMAP_PROTOCOL.md`](.agents/skills/solo-vps-project-engineer/ROADMAP_PROTOCOL.md) — ROADMAP rules;
3. [`ROADMAP.md`](ROADMAP.md) — current state, evidence, blockers, and next action;
4. [`docs/architecture.md`](docs/architecture.md) — concise responsibility map and accepted ADRs;
5. the implementation/tests/docs for the subsystem you are changing.

Legacy files under `legacy/` are research inputs, not executable instructions to copy mechanically.

For documentation changes, read [`DOCUMENTATION_GUIDE.md`](DOCUMENTATION_GUIDE.md). It defines the two-part runbook, writing style, complete command/UI handoffs and EN/RU validation requirements.

## Scope discipline

Prefer one coherent change set with one primary engineering concern.

Good contributions normally include the feature/fix, proportional validation, related documentation, and a ROADMAP update when project state changes. Avoid unrelated refactors, mass formatting, dependency upgrades, or architecture changes in the same change set.

Do not silently change these baseline ownership boundaries:

```text
Ansible            -> host layer
Coolify            -> application platform
GitHub Actions      -> CI / tests / image build
GHCR                -> container artifacts
SOPS + age          -> infrastructure/recovery secrets
restic + off-site   -> backup layer
```

Long-lived cross-layer changes belong in an ADR. Accepted ADRs are architecture baseline until explicitly superseded/rejected by a later decision.

## Local validation

Minimum source-level checks:

```bash
make validate
```

The root README explains the minimum local prerequisites. If the pinned M20 controller QA environment is available, use:

```bash
make qa-check
make qa-static
```

Do not report a command as PASS unless it was actually executed. Distinguish static/local evidence from disposable-target, clean-VPS, hosted-CI, or production evidence.

For mutating infrastructure changes, include the applicable recovery/rollback discussion and validate candidate configuration before service reload/restart where the underlying service supports it.

## Public product hygiene

Solo VPS upstream is a reusable public product, not a maintainer machine backup. Keep **operator-specific state** outside tracked source.

Use placeholders and documentation-safe examples in README/ROADMAP/docs/tests. In particular, do not commit:

- real public VPS IP addresses; use RFC 5737 addresses such as `203.0.113.10` in examples;
- personal domains, GitHub usernames, repository names, or Coolify resource IDs;
- runtime image digests, application commit SHAs, deployment UUIDs, or raw maintainer test logs;
- a real public age recipient from a maintainer workstation;
- generated workstation SOPS policy/recipient files, local config/inventory, or other operator state.

Dependency integrity pins are different: reviewed upstream action commit SHAs and official artifact checksums are product source and should remain pinned where the dependency policy requires them.

`make validate-public-product-hygiene` enforces the main source-level boundaries.

## Security and production boundaries

Never commit or paste into issues/PRs:

- private SSH keys;
- age identities;
- S3/restic credentials or passwords;
- registry/API tokens;
- application secrets;
- production inventory/configuration;
- real production IPs or sensitive logs.

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability.

Contributions may develop and test critical automation in local/disposable environments. Do not perform production VPS mutations, destructive operations, DNS/provider writes, credential rotation, paid-resource creation, releases, or publishing as part of a contribution unless the project owner explicitly authorizes that external action.

## Dependencies

Prefer standard Ansible/Python/Linux capabilities before adding another dependency. New mandatory dependencies should have a clear maintenance, update, security, and removal story.

Pin or constrain dependencies according to the project policy documented in [`docs/dependency-hygiene.md`](docs/dependency-hygiene.md). Major dependency upgrades should be separate reviewable changes.

## Documentation

Documentation should explain the mechanism, trade-offs, verification, and recovery boundary. Automation should execute the workflow; avoid turning docs back into giant copy/paste shell installers.

Keep the root README concise. Detailed operational commands belong in [`docs/command-reference.md`](docs/command-reference.md) or the relevant subsystem document.

## Change / pull-request evidence

A useful change description should state:

- the problem and observable result;
- important boundaries or trade-offs;
- files/subsystems changed;
- exact validation that ran (`PASS`, `FAIL`, `NOT RUN`, or environment-blocked);
- security/recovery impact for service-affecting or access/data-critical changes;
- ROADMAP/ADR impact, when applicable.

Do not claim `production-ready`, clean-VPS support, successful restore, hosted CI, or external reachability unless that evidence actually exists.

Commit messages should normally use the project's Conventional-Commits-like style, for example:

```text
feat(ssh): add hardened SSH configuration
fix(backup): reject missing PostgreSQL dump
```

The project owner performs commits/releases unless explicitly delegating those actions.
