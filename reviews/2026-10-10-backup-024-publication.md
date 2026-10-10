# v0.2.4 publication and bounded installed-tag evidence

Date: 2026-10-10. Published annotated tag: `v0.2.4`, commit `2748df373282ca77c191f9037b4b2da5837c7295`. [Release](https://github.com/paracosm17/solo-vps/releases/tag/v0.2.4); [PR #27](https://github.com/paracosm17/solo-vps/pull/27).

## Publication gates

The candidate passed focused backup tests, source checks, strict EN/RU documentation build, pinned real Ansible QA, clean release dry-run and independent security/recovery review. On the merged release commit, [required fast-source](https://github.com/paracosm17/solo-vps/actions/runs/38034071777) and [Pages publication](https://github.com/paracosm17/solo-vps/actions/runs/38034071759) passed. Exact merged-head `release-dry-run` with pinned QA passed; Gitleaks scanned all 88 locally reachable revisions with no leaks. The release tag was then published with the prepared notes, without changing platform pins.

## Installed source and backup

- Test and maintained production VPS checkouts now match the exact annotated tag. New clean sources were cloned beside the active checkout and checked against the release SHA before source replacement; previous source directories and external operator state were retained.
- One-time preparation preserved the test public policy and created the production public policy using the existing workstation identity's public recipient. Private identities remained off the VPS. No platform upgrade, restart, schedule, retention or data deletion was performed.
- Parameterless local backup passed on both exact-tag checkouts. All seven running test containers and all twenty running production containers retained their IDs, image identities, start times and health. No incomplete lifecycle marker or active deployment was present at inspection.
- The production encrypted backup was transferred to the owner's previously approved local backup directory. Ciphertext SHA256 matched the server output. Local age decryption completed with authenticated success and all manifest members verified; no plaintext archive/dump was saved on the workstation.
- During test handoff, a temporary operator script initially substituted part of the public argument name. The preparation target refused the missing argument. The source-only checkout had already changed; correcting the operator script resumed preparation successfully. No product code change or runtime restart was needed.

This establishes bounded V5 creation/transfer/verification evidence for the optional local backup feature, not production database restore or full disaster recovery. Isolated dump restore remains the separately recorded V3 test result. Current fresh-host installation and native Windows Make remain outside these claims. Release notes at the immutable tag describe prepublication V3 evidence; this later record adds the production result without modifying the tag.
