# v0.2.8 publication and installed tag

Date: 2026-11-26. [Release v0.2.8](https://github.com/paracosm17/solo-vps/releases/tag/v0.2.8), published by the owner at 04:20:14 UTC, is Latest, not a draft or prerelease. The GitHub-created lightweight tag resolves directly to `777da8cbba93644cac5d541cddf1fde53db50e35`; do not replace it with an annotated tag. [PR #41](https://github.com/paracosm17/solo-vps/pull/41) merged by squash; the resulting Git tree matches the tested release candidate exactly.

## Publication gates

- The merged commit passed [Repository CI / fast-source](https://github.com/paracosm17/solo-vps/actions/runs/45753066461) and [strict documentation build / Pages deployment](https://github.com/paracosm17/solo-vps/actions/runs/45753065609).
- Operator-run `make qa-tools` and `make release-dry-run RELEASE_VERSION=v0.2.8` completed on a clean checkout of the exact merged commit: built-in inspection of 60 locally reachable revisions and 681 archive entries, pinned QA, syntax tests and ansible-lint production profile (183 processed files, zero lint failures/warnings). No release mutation occurred during the dry run.
- Independent Gitleaks 8.30.1, archive SHA-256 verified, scanned local reachable history (`--all`, 58 commits reported) and the exact Git archive with redaction; no leaks found in either scan. This describes the operator's local ref set and snapshot, not an independent scan of every remote branch.
- GitHub confirms the published tag/commit and Latest release; release body matches the committed notes (normalized line endings), and the API exposes source ZIP and tarball URLs. Source archives were not independently downloaded.

## Installed release verification

The maintained production VPS uses the original source directory with external persistent config/inventory and toolchain. The operator corrected the stale single-branch origin fetch configuration to main, fetched the official tag, checked the exact commit identity, and checked out detached at v0.2.8. Working tree clean. No additional runtime upgrade or restart was required.

| Command | Result |
| --- | --- |
| make verify-coolify | PASS: ok=57 changed=0 failed=0 |
| make verify | PASS: ok=164 changed=0 failed=0 |
| make audit | PASS: ok=96 changed=0 failed=0 |

All 17 containers running; Coolify 4.7.8, PostgreSQL, Redis and Sentinel 1.1.5 healthy; main/realtime/terminal HTTP 200. Native proxy health and expected bindings passed, management ports loopback-only, no unexpected public database publications, no failed systemd units, audit warnings empty. Root filesystem 49% used. OS reboot remains required; automatic reboot is disabled.

The [bounded V5 upgrade record](2026-11-26-coolify-478-production.md) remains the runtime evidence, not a fresh-install V4, new disposable V3, application-specific smoke, independent restore, or off-site backup freshness proof. The optional backup repository remains NOT_CONFIGURED. Separate backup copies were not taken during this transition at operator request; the mandatory local checkpoint succeeded. The tag is immutable; this documentation is a post-publication follow-up only. No private host details or raw logs are included.
