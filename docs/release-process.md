# Release process

Solo VPS is **PRE-ALPHA**. This document defines a release process; it does not claim that a release has happened or that the current source tree is production-ready.

Canonical state still lives in `ROADMAP.md`. A release must describe the evidence that exists at the tagged commit rather than converting `NOT RUN`, `BLOCKED`, `PENDING`, `WARN`, or `UNAVAILABLE` into PASS.

## Version policy

Solo VPS uses normal three-component Semantic Versioning tags with a `v` prefix.

```text
v0.MINOR.PATCH   PRE-ALPHA / initial development
v1.0.0           first stable supported baseline
```

For `v0.x.y`, compatibility is not guaranteed. Project convention is:

- increment `MINOR` for a coherent capability/release batch or a meaningful contract change;
- increment `PATCH` for fixes and documentation/refinement releases within that PRE-ALPHA line;
- do not infer a stable public API from either number while the major version is zero.

The first public release, when the project is actually ready to publish one, should start no lower than `v0.1.0`. Pre-release suffixes are intentionally not part of the first release contract; add them only if a concrete release workflow needs them.

`v1.0.0` is not a calendar milestone. It requires the v1 release gate in `ROADMAP.md`, including clean-target, deployment, backup, restore, and other required evidence.

Reference: [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## Publication prerequisites

A public release is blocked unless all applicable checks below are true:

1. the owner has selected and published the root `LICENSE`;
2. the repository is an initialized Git worktree and the release commit is clean;
3. `CHANGELOG.md` contains an entry for the exact release version and keeps an `Unreleased` section;
4. `make validate` passes;
5. the real M20 pinned QA layer has been installed and `make qa-static` passes;
6. the **latest disposable clean-target core evidence** for the candidate source proves Ubuntu 24.04 bootstrap, SSH hardening, audit, and an idempotency rerun with `changed=0`; this host proof does not replace the self-repository `fast-source` prerequisite;
7. Solo VPS has been published to its own upstream repository, and that repository's `fast-source` **required status check** exists for the default branch and **must be green** for the release commit; consumer-application checks never satisfy this prerequisite;
8. the latest CRIT-015 external-uptime evidence proves a whole-target outage was detected from outside the VPS, an off-VPS alert arrived inside the reviewed interval, and a recovery notification arrived after the endpoint returned;
9. **CRIT-011 Coolify lifecycle evidence** proves the reviewed previous-supported `4.1.1` → current-supported `4.1.2` transition on a disposable Ubuntu 24.04 VPS, including fresh backup prerequisites, preflight, exact target artifacts, post-upgrade `verify-coolify`/`verify`/`audit`, and one documented forward-resume-or-M16 recovery exercise;
10. the release notes preserve current PRE-ALPHA limitations and ROADMAP blockers;
11. the exact set of Git refs/history intended for publication has been scanned for local state and private-key material, followed by an independent secret scanner such as Gitleaks before the first push;
12. the requested tag does not already exist;
13. `make release-dry-run RELEASE_VERSION=v0.x.y` passes;
14. the owner explicitly approves the actual tag/release/publish action.

The v0.1.0 candidate also needs the ROADMAP gates that a source dry run cannot prove: full lost-VPS reconstruction, exact-candidate replay from the rendered public docs without maintainer assistance, a successful GitHub Pages deployment with correct EN/RU links, and an enabled/tested private vulnerability-reporting channel. Validate the accepted Coolify target on a disposable host before changing supported pins; the current `4.1.1` → `4.1.2` source policy and the `4.3.21` evaluation candidate are distinct.

The dry-run does not weaken these gates merely to make PRE-ALPHA publishing easier.

## Prepare the changelog

Keep ongoing work under:

```markdown
## [Unreleased]
```

Before a release, move the relevant items into a dated heading whose version does **not** include the `v` prefix:

```markdown
## [0.1.0] - 2026-08-11
```

Leave a new `Unreleased` section above it for subsequent work.

Release notes should summarize observable capabilities, important security/recovery boundaries, validation actually executed, and known blockers. Do not publish internal private reasoning or pretend source validation is integration evidence.

## No-publish dry run

After preparing the dated changelog entry in a clean initialized Git worktree, run:

```bash
make release-dry-run RELEASE_VERSION=v0.1.0
```

This command is intentionally read-only with respect to Git history and external systems. It:

- validates the release version;
- requires the root license and exact changelog entry;
- requires an initialized, clean Git worktree;
- requires important release files to be tracked;
- scans all locally reachable refs for forbidden local paths, private-key-shaped filenames and private-key material, including files deleted before `HEAD`;
- rejects an already-existing tag;
- creates a temporary `git archive` of `HEAD` only for inspection;
- rejects local config/inventory, plaintext secret paths, local virtualenv, private-key-shaped files, and other forbidden release paths from that tracked snapshot;
- deletes the temporary archive automatically.

The built-in history check is intentionally narrow and deterministic. Before the first public push, run an independent maintained secret scanner against the same complete ref set and review every finding. If only a curated subset of local refs will be published, scan the exact rewritten/exported repository that will be pushed, not a different working copy.

`release-dry-run` depends on `make validate`. It does **not** run network requests, query GitHub branch protection/status APIs, create a tag, push Git state, create a GitHub Release, or upload an asset. The required remote Solo VPS `fast-source` status therefore remains an explicit GitHub release prerequisite rather than something an offline dry run can fabricate. Until Solo VPS has its own upstream repository this prerequisite is intentionally unsatisfied; a green consumer-application workflow cannot substitute for it.

The current Git checkout contains the selected Apache-2.0 root `LICENSE`. Before v0.1.0, a dated changelog entry, a clean release commit, and available pinned QA tooling are still required; hosted and runtime evidence remain separate prerequisites.

## Actual release — explicit owner action only

After the dry run passes, actual publication remains a separate maintainer action. A future release can use an annotated Git tag and a GitHub Release associated with that tag.

Example commands are intentionally shown only as a manual procedure; project automation must not execute them without explicit approval:

```text
git tag -a v0.1.0 -m "Solo VPS v0.1.0"
git push origin v0.1.0
# create the GitHub Release from tag v0.1.0 and paste reviewed release notes
```

GitHub Releases are based on Git tags and GitHub automatically exposes source ZIP/tarball downloads for the tagged repository state. The initial Solo VPS release contract therefore does **not** add a custom binary/source-bundle publishing system. If the project later ships standalone binaries or other custom assets, add checksums/signatures as a separate reviewed release change.

Reference: [GitHub Docs — About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## After publication

After an explicitly approved release:

1. verify that the GitHub Release points at the intended tag/commit;
2. verify the release notes still match the committed `CHANGELOG.md` and ROADMAP evidence;
3. verify the automatically generated source archives are visible;
4. never replace the contents of an already published version — publish a new version for subsequent changes;
5. keep `Unreleased` ready for the next change set.

A source release does not automatically prove the host/bootstrap/Coolify/backup/restore path. Those evidence levels remain recorded separately in ROADMAP.

## v1.0 boundary

Do not publish `v1.0.0` until the ROADMAP v1 release gate is satisfied at the required evidence levels. In particular, written automation alone is not sufficient: the clean-VPS bootstrap, access/recovery behavior, Docker/Coolify path, application deployment, off-site backup, restore/DR, CI, license, and operational verification must be demonstrated rather than inferred.
