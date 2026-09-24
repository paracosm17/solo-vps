# First public release preparation review — 2026-09-13

## Purpose

This note captures the owner's final pre-release review after the maintained-VPS walkthrough of chapters 1–8. It is a planning/evidence document, not public user documentation.

The main conclusion is that Solo VPS should **stop adding broad core features before `v0.1.0`**. The remaining work is release evidence, documentation/product polish, a current lifecycle decision, and GitHub publication setup. Larger team-management and shell-UX ideas belong in the post-alpha backlog unless they expose a blocker in the final clean-user replay.

## Release blockers before `v0.1.0`

### 1. Owner-only clean rehearsal from the exact candidate

Run the whole public route again from a clean Ubuntu 24.04 VPS **without ChatGPT or maintainer-only notes**. Use only the exact candidate revision and the rendered public documentation.

Record:

- every command copied from the docs;
- every browser/account step;
- hands-on time and wait time;
- every place where the reader has to guess a value, user, path, page or next action;
- every manual action that should become automation;
- final `make verify`, `make audit`, application health, backup freshness and idempotency evidence.

Any chat-only knowledge required to finish the run is a release defect.

### 2. Finish the remaining real-environment gates

Before publication, complete the gates already tracked by ROADMAP/release policy:

- the real three-day retained-log lookup from chapter 3;
- complete lost-VPS reconstruction on a clean replacement target;
- whole-target external outage + recovery alert on the disposable target;
- supported Coolify upgrade/recovery on the disposable target;
- exact-candidate clean install + rerun/idempotency proof;
- the Solo VPS repository's own hosted `fast-source` required status check;
- GitHub private vulnerability reporting;
- final release dry-run, changelog entry and immutable `v0.1.0` release identity.

### 3. Revisit the Coolify support pin before freezing the release

The current source contract pins Coolify `4.1.2` and models only `4.1.1 -> 4.1.2`. The maintained instance now advertises a much newer upgrade (`4.3.19` observed by the owner on 2026-09-13).

Do **not** update the maintained production-like VPS merely because a newer version exists. Before the release candidate is frozen:

1. review upstream release/upgrade notes and changes since `4.1.2`;
2. choose an intentional release target (current stable or a deliberately retained older supported pin);
3. update checksums/contracts/fixtures together;
4. prove install + upgrade + backup/recovery + application delivery on a disposable VPS;
5. only then make the new version the public supported baseline.

Shipping a first public release with a visibly stale pin is acceptable only if the README/upgrades page clearly explains why and what is supported; otherwise the pin should move before `v0.1.0`.

### 4. Define the Solo VPS source-update story

`make update` currently shows lifecycle planning; it is **not** a source self-updater. Before `v0.1.0`, document a supported update path for Solo VPS itself.

Preferred first-release model:

```text
installed release tag / exact commit
-> fetch/download a newer reviewed release into a new checkout
-> reuse persistent controller state outside the checkout
-> make setup
-> make doctor / make verify / make audit
-> run only the explicit subsystem migrations required by that release
-> keep the previous checkout until verification succeeds
```

Avoid teaching users to run an unreviewed `git pull` on the active checkout and hope that runtime state follows source state. A future `make source-upgrade`/`solo-vps upgrade` helper can automate this after the manual tagged-release contract is proven.

### 5. Reconcile the “small team” product claim

The Passport/README include very small teams in the target audience, but the public route currently proves only the single-owner/operator workflow. Before `v0.1.0`, choose one honest boundary:

- narrow the first release wording to **solo developer / single operator**, and keep team onboarding as post-alpha work; or
- add a minimal, non-duplicative team access guide that composes GitHub/Coolify native permissions and clearly separates dev from production access.

Do not leave “small team” as a marketing claim that has no documented safe onboarding/offboarding path. Full team automation can still remain post-alpha.

### 6. Align GitHub publication details

Before the public repository is announced:

- choose the default branch (`main` is preferred for the existing docs deployment workflow) and make workflows/docs consistent with it;
- configure branch protection/rulesets so the Solo VPS `fast-source` check is required;
- enable private vulnerability reporting;
- set `site_url`, `repo_url` and `edit_uri` in `mkdocs.yml` when the real repository/docs URLs exist;
- run a source/history secret and operator-data scan on the exact public history, not only the current tracked tree;
- render the documentation from the exact tag candidate and visually inspect desktop + mobile + both languages.

The current source branch is `master`, while documentation deployment is restricted to pushes on `main`; this must be resolved intentionally rather than discovered after publication.

## Documentation cleanup before release

### Replace confusing sample identity/address values

The public walkthrough currently uses the reserved documentation IP `203.0.113.10` and often hard-codes the administrator name `ops`. These values are safe examples, but they look like values the reader might be expected to use.

Before release:

- standardize on semantic names such as `SERVER_IP` and `ADMIN_USER` throughout the guided route;
- distinguish the default config value from the reader's actual configured value;
- do not put literal `<SERVER_IP>` / `<ADMIN_USER>` into a code block advertised as directly copyable, because `<...>` is shell syntax; either define variables first or clearly mark the block as a template;
- apply the same convention in EN/RU pages and command tables.

At the time of this review, `203.0.113.10` still appears across 12 public documentation files and `ops` across many user/reference pages, so this should be a deliberate repository-wide edit with validators rather than ad-hoc replacements.

### Rebuild the visual hierarchy of the left navigation

The first-user route should be visually dominant:

- make **Basic setup** use a stronger, clearer icon than the current subdued arrow;
- keep chapters 1–2 visually prominent;
- make the numbered **After basic setup** action chapters 3–7 bold/prominent too;
- move the current chapter 8 out of the numbered tutorial sequence because it is a runbook/reference page, not a short setup task;
- keep `What to add next` and `Daily operations` near the tutorial but not numbered as setup chapters;
- de-emphasize the deeper Deploy/Operations/Backup/Host/Reference trees so they read as reference material rather than the main path.

A sensible destination for the current **Failures & maintenance** page is the existing **Maintenance** group next to upgrades, without the `8.` prefix.

### Decide which maintainer artifacts belong in the public repository

The repository currently tracks `reviews/critic/` and `.agents/` maintainer/AI-engineering material. They are not in the MkDocs user navigation, but they will still be visible in a public GitHub repository and in a normal source checkout. Before the initial public push, decide intentionally whether they are part of the open-source maintainer surface.

If not, move durable contributor rules into `CONTRIBUTING.md` / `DOCUMENTATION_GUIDE.md`, keep only concise release evidence that benefits contributors, and create the public repository from a clean reviewed tree/history. Do not publish internal process material merely because it happened to be present during development.

Also normalize language in root maintainer contracts: the English `PROJECT_PASSPORT.md` still contains a few Russian sentences/headings.

### Remove process residue and troubleshooting chronology from user pages

Perform an editorial pass over the whole rendered site, not only grep-based cleanup.

Keep only information that helps a new user make a decision or complete an action. Remove or relocate:

- chronology of bugs discovered during this development walkthrough;
- internal evidence language, milestone IDs and maintainer terminology;
- repeated warnings already enforced by automation;
- explanations that exist only because an earlier draft was wrong;
- duplicate procedures where one canonical path now exists;
- long implementation essays in the numbered tutorial.

Retain a troubleshooting branch only when the failure is reasonably common, recognizable by the reader and has a safe concrete recovery step. Historical engineering context belongs in reviews/ROADMAP/ADR/Git history.

### Soften the documentation appearance

The current dark palette uses a bright blue accent and relatively high contrast. Before release, do a small visual pass rather than a redesign:

- reduce saturation/brightness of the active blue state;
- soften the selected navigation background;
- preserve strong contrast for code, warnings and focus states;
- check the hierarchy at the viewport size shown in the owner's screenshot;
- check light theme too;
- keep system fonts and avoid decorative dependencies.

The goal is calmer long-form reading, not a branded landing-page redesign.

## Post-`v0.1.0` product backlog

### Safe developer onboarding and production access control

Design a small-team workflow that lets a new developer contribute without receiving production access by default.

Questions/capabilities to cover:

- GitHub organization/repository roles and rulesets;
- developers can push feature branches and open PRs, but protected `main` merge/release remains owner/reviewer-controlled;
- separate GitHub environments and secrets for development versus production;
- Coolify team/project/environment permissions where the supported Coolify version can enforce them;
- development application/database credentials separated from production credentials;
- no VPS shell, Docker group, production database or production Coolify token unless explicitly granted;
- documented grant/revoke/offboarding procedure;
- optional `make` helpers only where they can safely automate a stable provider/platform contract.

Do not invent a Solo VPS RBAC system that duplicates GitHub/Coolify. Prefer composing their native permission models and documenting the boundary.

### Better update ergonomics

After the first tagged-release update contract is proven, consider a bounded helper that can:

- show installed/source revision and newest reviewed Solo VPS release;
- download/fetch the target release without overwriting the active checkout;
- run preflight against persistent state;
- show required migrations and recovery prerequisites;
- switch only after verification;
- preserve the previous source checkout for source-level rollback.

Coolify updates stay a separate lifecycle operation because they can include database migrations and control-plane state changes.

### Optional terminal / shell UX

Do not make shell customization part of the security/platform baseline. Keep it opt-in.

A useful split:

**Small safe CLI convenience pack** (potential `make shell-tools`):

- `ripgrep`;
- `fd`/`fdfind`;
- `bat`/`batcat`;
- `fzf`;
- a process/disk viewer where the Ubuntu package source is acceptable.

`jq` is already part of the core base package set and should not be duplicated as a shell-UX feature.

**Personal shell profile** (separate opt-in):

- zsh configuration;
- completion/history/search plugins;
- prompt/theme choices;
- optional Oh My Zsh or another framework only with a reviewed installation/update/removal story;
- a small catalog of profiles/themes rather than silently replacing the user's shell.

The core installation should continue to work with stock Bash and should not execute a remote `curl | sh` shell-framework installer as part of host provisioning.

## Priorities after this review

### Must finish before `v0.1.0`

1. Documentation cleanup/navigation/placeholder pass.
2. Decide and prove the supported Coolify release/lifecycle target.
3. Document the Solo VPS tagged-source update contract.
4. Complete the remaining disposable-VPS and three-day retention evidence.
5. Run the exact-candidate owner-only walkthrough without ChatGPT.
6. Configure the real GitHub repository gates/security/docs URLs and run release dry-run.

### Explicitly defer unless the clean replay proves otherwise

1. Developer/team access-control productization.
2. Optional shell/theme catalog.
3. More observability features.
4. More infrastructure components.

These are valuable, but adding them before the first release increases the surface that must be tested again.
