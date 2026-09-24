---
name: solo-vps-release
description: Prepare or review a Solo VPS release candidate. Use for release readiness, changelog/tag preparation, hosted-CI gates, public-tree hygiene, and v0.1.0 evidence; not for normal feature work.
---

# Solo VPS release

Use this skill only for release-scoped work.

## Workflow

1. Read `README.md`, the current release gates in `ROADMAP.md`, `docs/release-process.md`, `CHANGELOG.md`, and only the implementation/evidence needed for unresolved gates.
2. Ask `release_guard` for an independent read-only audit when the candidate affects lifecycle, security, recovery, or public production claims.
3. Resolve source defects before broad release validation.
4. Run targeted checks for changed areas, then `make release-dry-run` when the local release prerequisites are available and the task is actually release-candidate preparation.
5. Treat hosted required-check status, branch policy, Pages URLs, private vulnerability reporting, exact-history secret scanning, clean-VPS replay, and other external gates as external evidence. Do not mark them complete from source inspection alone.
6. Prepare release notes/changelog/tag commands, but do not commit, push, tag, publish, or create a release unless the user explicitly authorizes those external actions.
7. Update `ROADMAP.md` only for real gate/evidence changes.

## Completion report

Separate:

- source checks passed;
- runtime/clean-host evidence passed;
- hosted/publication evidence passed;
- remaining blockers;
- external actions still awaiting authorization.
