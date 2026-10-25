# v0.2.5 publication and installed tag

Date: 2026-10-25. Annotated tag v0.2.5 resolves to `3f8cef4c20fb1c7d5846dc15ec1717003f2d9d53`. [Release](https://github.com/paracosm17/solo-vps/releases/tag/v0.2.5); [PR #30](https://github.com/paracosm17/solo-vps/pull/30).

## Publication gates

Independent upstream/source/release review found no unresolved defect. The release candidate passed source tests and strict EN/RU docs build. On the merged release commit, [required fast-source](https://github.com/paracosm17/solo-vps/actions/runs/40179496646) and [Pages deployment](https://github.com/paracosm17/solo-vps/actions/runs/40179496634) passed. Clean exact-main release-dry-run with pinned real QA passed. Gitleaks scanned all 100 locally reachable revisions with redaction and no leaks before tagging. The annotated tag and prepared GitHub Release were then published.

## Installed source and recovery inputs

On both the test and maintained production VPS, the normal source-update-prepare command created a clean exact-tag checkout. Its revision was checked against the release SHA before moving it into the standard source path. Previous checkouts and external config/inventory/toolchains were retained. Exact-tag verify-coolify passed on each: ok=56 changed=0 failed=0. This source-only step performed no additional platform upgrade or restart.

Fresh encrypted off-host exports were collected before the upgrade and after exact-tag installation on both hosts. All passed authenticated decryption and member manifest checks. Private age identities stayed on the workstation. No plaintext recovery archive was saved there; application data remains a separate backup layer.

The [controlled V3 record](2026-10-24-coolify-450-runtime.md) and [bounded production V5 record](2026-10-24-coolify-450-production.md) describe actual runtime changes and their limits. This publication record does not promote them to fresh-install V4 or full recovery evidence. The release tag is immutable; this later documentation records the completed publication state.
