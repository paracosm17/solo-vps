# AI coding workflow for Solo VPS

This repository is configured for Codex with a capable primary agent, cheap bounded subagents, narrow skills, and explicit escalation for high-risk infrastructure work.

## Recommended default

Open the repository root in Codex. The project `.codex/config.toml` selects:

- primary: `gpt-6-sol`, medium reasoning;
- default subagents: `gpt-6-luna`, high reasoning;
- at most three concurrent subagent threads;
- workspace-write sandbox with shell network access disabled by default.

Use the primary agent for normal end-to-end implementation. Do not start every task with Astra or multiple agents.

## Prompt shape

For normal work, a short task is enough when the repository already contains the context:

```text
Implement <outcome>.

Acceptance:
- <observable behavior>
- <observable behavior>

Non-goals:
- <important boundary, if any>

Run the relevant targeted checks and update docs only if supported behavior changes.
```

For risky work, add the boundary rather than a long procedure:

```text
Prepare the Coolify 4.3.21 disposable-VPS evaluation.
Use the runtime planner first. Do all repository-side preparation and read-only checks,
but do not mutate a VPS until I explicitly authorize execution.
```

For parallel review:

```text
Review this branch against main. Use explorer to map the affected paths and reviewer
to find correctness/security/regression risks. Keep implementation in the primary agent.
```

## Model escalation

Use the configured Sol/Medium primary by default.

- Luna/High: search, mapping, repetitive bounded checks, narrow supporting work.
- Sol/High: difficult debugging or independent code/security review.
- Astra/Low: ambiguous cross-layer architecture or release-critical design.
- Astra/Medium: difficult runtime/recovery/security planning where Low is insufficient.
- xHigh/Max: exceptional escalation after lower effort failed; do not use by default.

Astra is a consulting/escalation role, not a permanent project manager.

## When to use subagents

Delegate only independent work with a clear expected result. Good uses include separate repository exploration, independent review, comparing upstream options, or checking distinct failure hypotheses.

Keep dependent steps in one agent. Do not have multiple agents edit the same files concurrently. If parallel implementation is genuinely useful, use separate Git worktrees and merge after independent validation.

## Human approval boundary

A normal coding request authorizes local reads, edits, and local tests. It does not authorize real infrastructure or publication changes.

Require explicit user intent before:

- mutating a VPS or external service;
- SSH/UFW/sudo changes on a real target;
- Coolify upgrades/deployments outside a disposable authorized test;
- backup retention/prune or restore into real state;
- commit/push/tag/release/publication.

The agent may prepare the complete plan, patch, tests, and dry-run evidence before asking for that final external action.

## Keep prompts and context small

Do not paste the whole project into prompts and do not ask the model to read every design document before every edit. `AGENTS.md` maps each source of truth; skills load only when their trigger matches.

Pass compact task packets between agents: objective, acceptance criteria, non-goals, relevant files, risks, required validation. For review, pass the task plus diff/test results instead of replaying the entire conversation.

## Useful explicit skill invocations

In Codex, use `$` to select a repository skill when you want deterministic routing, for example:

- `$solo-vps-project-engineer` for implementation;
- `$solo-vps-project-critic` for an independent audit;
- `$solo-vps-documentation-writer` for user docs;
- `$solo-vps-runtime-evidence` for live/disposable infrastructure work;
- `$solo-vps-release` for release preparation;
- `$solo-vps-roadmap` only when project state actually changed.
