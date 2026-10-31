# v0.2.6 candidate status — publication not completed

As of 2026-10-25, runtime work is complete and [PR #32](https://github.com/paracosm17/solo-vps/pull/32) is prepared. No v0.2.6 tag or GitHub Release has been published. The immutable candidate installed on both controllers is `e665e2c52d6c08c489253eeb04b86b7144e62419`; subsequent status-only documentation does not alter its integration fingerprint or execution code.

## Passed evidence

- Controlled test and bounded production firmware/reboot and Traefik results are recorded separately. Production runs kernel 6.8.0-147-generic, Traefik 3.7.16, Coolify 4.5.0 and Sentinel 1.1.2. Native package discovery reports zero updates and no required reboot; Ubuntu security-update policy is retained.
- Candidate source CI, pinned real QA/release-dry-run and strict EN/RU documentation build passed locally. Independent Gitleaks scanned all 105 then-reachable revisions without leaks. Temporary operator scripts and private state were excluded from Git.
- Both standard source paths were updated to that exact verified candidate, preserving the v0.2.5 checkout separately. Candidate-installed Coolify verification passed on each with ok=56 changed=0 failed=0. These are candidate source installations, not published-tag installations.
- Fresh authenticated encrypted control-plane backups and complete proxy checkpoints are off-host. Private age identity stayed on the workstation; no plaintext recovery archive was saved there.

## External blocker

Hosted required fast-source passed its source tests but failed downloading the exact pinned community.general 13.0.1 artifact from Ansible Galaxy. [Run](https://github.com/paracosm17/solo-vps/actions/runs/40184442959) failed with HTTP 500 on its initial attempt and two bounded reruns. A direct request to the same official artifact URL also returned 500. The documentation build passed.

No dependency version was loosened, no artifact was substituted, and branch protection was not bypassed. Publishing remains conditional on a successful hosted check, protected merge, exact-main QA/dry-run, independent history scan and successful Pages deployment. Recheck the external artifact/CI before proceeding; local success does not establish hosted success.
