---
name: solo-vps-documentation-writer
description: Write or revise Solo VPS user documentation. Use for README, Quick Start, operations, recovery, troubleshooting, reference, MkDocs navigation, and English/Russian documentation changes.
---

# Solo VPS documentation writer

Use this skill when the requested deliverable is documentation or when an implementation change requires user-facing docs to stay accurate.

## Source and audience

Write for a solo developer or small team operating one VPS. Prefer task-oriented instructions over internal implementation detail.

Use actual repository behavior as factual evidence. Use `README.md` as the current public contract, `PROJECT_PASSPORT.md` for architecture boundaries, and the relevant scripts/Make targets/runbooks for exact commands.

Do not document planned behavior as implemented. State runtime evidence limits when they matter.

## Writing workflow

1. Identify the user task and the exact page(s) that own it.
2. Read those pages plus only the implementation sources needed to verify commands, paths, inputs, and outcomes.
3. Keep one clear happy path. Put optional/background material after the main task or link to a dedicated page.
4. Tell the user where each command runs: workstation, VPS, browser UI, GitHub, Coolify, or another external service when ambiguity is possible.
5. Prefer project automation to copy-pasted manual mutation commands when automation already exists.
6. Include verification and recovery/troubleshooting steps when the task can fail materially.
7. Preserve the public/private boundary: examples use placeholders and never owner-specific infrastructure values or secrets.
8. When editing a public English page with a maintained `.ru.md` counterpart, update the pair consistently unless the task explicitly limits language scope.
9. Run the narrowest relevant docs/contract checks; use `make docs-build` only when a full documentation-site build is justified.

## Document roles

- README: product promise, status, entry points, supported happy path.
- Quick Start/tutorial: sequential first success with minimal branching.
- How-to/operations: one operational goal with prerequisites, action, verify, troubleshoot.
- Reference: exact commands/options/contracts without tutorial narration.
- Architecture/ADR: ownership, constraints, decisions, and consequences.
- Roadmap: current development state; do not move implementation detail there.

## Style

Be concise, explicit, and scannable. Use semantic headings, short paragraphs, numbered procedures for ordered work, tables only when they improve comparison, and code blocks only for commands/config the user should actually use.

Do not invent time estimates, capabilities, version support, or production guarantees.
