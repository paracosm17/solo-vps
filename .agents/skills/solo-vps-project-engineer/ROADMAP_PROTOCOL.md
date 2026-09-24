# Solo VPS ROADMAP protocol

Use this file only when `ROADMAP.md` needs an update. It is not a specification and it is not required reading for ordinary edits.

## Purpose

`ROADMAP.md` records current development state: what is true now, what blocks the next release, what evidence exists, and what should happen next. Historical detail belongs in Git history, `CHANGELOG.md`, or bounded review/evidence files.

## Source roles

- `README.md`: current public user contract.
- `PROJECT_PASSPORT.md`: architecture/product north star.
- `ROADMAP.md`: current planning state and evidence summary.
- code/tests/runtime evidence: factual implementation behavior.

Do not copy large sections between these documents.

## Update rules

Change the Roadmap when at least one is true:

- a tracked blocker or release gate changed;
- a meaningful work item moved state;
- validation/evidence level changed;
- a design decision changes the next work;
- the single next action changed.

Do not update it for every small refactor, wording fix, or test-only cleanup.

## State and evidence

Use plain states such as `PLANNED`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `DEFERRED`, or `CANCELLED` only when they clarify current work.

Use the project evidence levels consistently:

- `V0` — not validated;
- `V1` — static/lint/syntax;
- `V2` — local/unit/source behavior;
- `V3` — integration/controlled real environment;
- `V4` — complete clean Ubuntu VPS replay;
- `V5` — real production-use evidence.

`DONE` must not imply a higher validation level than the evidence supports.

## Editing style

Keep the file short and current. Prefer one concise statement with a link to detailed evidence over an implementation diary.

Maintain one unambiguous `Next action` in the header. If several tasks are possible, choose the one that blocks the highest-priority release outcome; leave alternatives in the relevant section rather than presenting multiple next actions.

When a completed item no longer helps explain current release state, move its history to `CHANGELOG.md`/Git or remove the detail from the Roadmap.
