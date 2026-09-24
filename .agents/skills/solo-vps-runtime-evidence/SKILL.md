---
name: solo-vps-runtime-evidence
description: Plan, execute, or record Solo VPS disposable/real VPS evidence. Use for live SSH/firewall/Coolify/upgrades/backups/recovery/monitoring actions or any task that mutates external infrastructure.
---

# Solo VPS runtime evidence

Use this skill whenever the task crosses from repository work into a VPS or external service.

## Before mutation

1. Classify the target: disposable evaluation VPS, replacement/recovery VPS, or maintained VPS.
2. Read the exact runbook/Make target that owns the operation. Prefer repository automation over improvised shell commands.
3. Separate read-only preflight from external writes and destructive actions.
4. Confirm the required recovery path for access-critical or stateful work: provider console/rescue for SSH/UFW/sudo changes; fresh backup/restore evidence for destructive state changes; explicit interruption/resume path for upgrades.
5. If the user did not explicitly authorize the external mutation, prepare the plan and stop before the mutating command.

Use the `runtime_planner` agent for upgrade, recovery, firewall/SSH, backup-retention, or other high-impact operations.

## During execution

Keep the operation bounded to the authorized target and action. Do not broaden a disposable evaluation into support-policy changes until the runtime evidence passes.

Never print secret values. Capture only sanitized evidence needed to prove the claim.

## Evidence

Record what actually happened, including exact version/revision, target class, checks performed, failures/recovery, and resulting V0–V5 level. A local/source success does not substitute for runtime proof.

Update public docs or support pins only after the required evidence exists. Update `ROADMAP.md` through the roadmap skill when the evidence changes project state.
