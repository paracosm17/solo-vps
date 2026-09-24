---
name: solo-vps-roadmap
description: Update Solo VPS ROADMAP.md after a real change in project state, blocker, validation level, release gate, or next action. Do not use for ordinary small edits.
---

# Solo VPS roadmap maintenance

Use `.agents/skills/solo-vps-project-engineer/ROADMAP_PROTOCOL.md` as the compact editing protocol.

Before editing, verify the state change from the relevant code, tests, review, or runtime evidence. Do not infer completion from intent.

Keep the Roadmap current and short. Update only the affected snapshot/gate/item and the single `Next action` when it changed. Do not add a development diary.

After editing, run `make validate-documentation-governance` and `make test-documentation-governance` when those checks are available and relevant to the change.
