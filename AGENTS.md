# Solo VPS agent guide

Solo VPS turns one clean Ubuntu 24.04 VPS into a secured Docker/Coolify host with a small operator command surface. Keep the maintained topology to one application VPS unless the user explicitly changes the product contract.

## Sources of truth

Read only what the task needs.

- `README.md` — current public user contract and current status.
- `PROJECT_PASSPORT.md` — product and architecture boundaries.
- `ROADMAP.md` — current development state, blockers, validation level, and next action.
- `docs/architecture.md` and `docs/adr/` — current ownership/architecture decisions.
- `docs/` — user operations and reference behavior.
- repository code/tests/runtime evidence — factual implementation behavior.

When sources disagree, prefer actual code/tests/runtime evidence for factual behavior, then the current public contract for supported user behavior. Treat the Passport as a design boundary and the Roadmap as planning state, not as proof that code works.

## Default working behavior

Infer the intended scope from the task and carry authorized repository work through implementation, relevant validation, documentation updates, and a concise completion report. Do not stop after proposing a plan when the user asked for a change.

Use the smallest coherent change that satisfies the request. Do not opportunistically redesign unrelated areas.

Local repository edits, read-only inspection, and local source/unit/static tests are safe to perform without asking. Do not commit, push, tag, publish, deploy, mutate a real VPS, change external services, rotate credentials, delete remote data, or run destructive recovery/retention operations unless the user explicitly authorizes that external action.

Never print, commit, or copy private SSH keys, age identities, S3 credentials, restic passwords, Coolify API tokens, or application secrets into tracked files.

## Validation

Match verification to the change.

- Small docs/metadata edit: run the narrowest relevant docs/contract check.
- Bounded implementation change: run the matching `validate-*` / `test-*` targets or focused unit tests.
- Cross-cutting source change: use `make ci-fast-source` when justified.
- Release candidate: use the release skill and `make release-dry-run` when its prerequisites are appropriate.
- Do not run broad suites repeatedly after a narrow change if targeted checks already prove the changed behavior.

Runtime claims must state their evidence level. Local/static checks do not become clean-VPS or production proof.

## Agent delegation

Use subagents only for independent, bounded work that benefits from separate context. Keep short or sequential work in the primary agent. Avoid concurrent writers on the same files.

Preferred roles:

- `explorer` — fast read-only repository mapping and evidence gathering.
- `reviewer` — independent correctness/security/regression review of a diff.
- `architect` — cross-boundary or ambiguous architecture decisions; use sparingly.
- `release_guard` — release-critical, recovery, security, or lifecycle review.
- `runtime_planner` — plan and audit live/disposable-VPS operations before external mutation.

Default implementation stays with the primary GPT-6 Sol agent. Delegate exploration or independent review, then return compact findings rather than full conversation transcripts.

## Skills

Skills are workflow guidance. Explicit task scope from the user takes precedence over skill preferences when it remains compatible with repository safety and architecture constraints.

Use a skill only when its trigger matches the task. Do not load every skill or every project document before each edit.
