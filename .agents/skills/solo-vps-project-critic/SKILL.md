---
name: solo-vps-project-critic
description: Review Solo VPS independently for real product, architecture, security, recovery, release, or change risks. Use for audits and adversarial review; do not use for routine implementation.
---

# Solo VPS project critic

Use this skill for independent review. Do not edit implementation while reviewing unless the user explicitly asks for fixes after the review.

## Review method

1. Identify the review scope: change, subsystem, Quick Start, architecture, or release.
2. Read only the evidence needed for that scope. Trace actual code/tests for factual behavior; use `README.md` for public promises and `PROJECT_PASSPORT.md` for architecture boundaries.
3. Reconstruct the relevant user/operator path rather than trusting document labels or comments.
4. Look for concrete failures: unsafe access changes, hidden state, non-idempotent automation, incorrect ownership boundaries, rollback/recovery gaps, public exposure, secret leakage, unsupported version assumptions, claims stronger than evidence, and missing meaningful validation.
5. When current upstream behavior matters, research authoritative sources and distinguish external fact from repository evidence.
6. Report findings first. Do not reward complexity or penalize simplicity by itself.

## Severity

- **P0** — credible release-blocking safety/data/security failure.
- **P1** — core product path is broken or materially misleading.
- **P2** — important reliability, operability, or maintainability risk.
- **P3** — worthwhile improvement with limited current impact.

Avoid P4/nit findings unless the user requested exhaustive polish.

## Finding format

For each material finding include:

- severity and short title;
- exact evidence with file/section/symbol;
- why it matters in the real Solo VPS workflow;
- the smallest useful correction or proof needed.

State explicitly when no material finding was found in the reviewed scope.

## Product checks

Apply only the checks relevant to the review:

- one-VPS scope and optional-feature isolation;
- host vs Coolify ownership;
- SSH/sudo/UFW/Docker exposure safety;
- immutable CI/GHCR/Coolify delivery and image-only rollback boundary;
- SOPS/age secret boundary;
- off-site backup plus exercised restore/recovery evidence;
- clean-host reproducibility and idempotency;
- operator command/Quick Start usability;
- release/runtime claims matching V0–V5 evidence.

For release-critical reviews, prefer the `release_guard` agent so the review has independent context.
