# Documentation authoring contract

This is the persistent writing policy for Solo VPS contributors and AI agents. It records the first-user requirements behind the basic setup runbook. Apply it together with the documentation boundaries in `PROJECT_PASSPORT.md`; use `ROADMAP.md` for current implementation and validation state.

## The reader's task

Help a developer configure a single VPS and return to application development. They know basic Git and terminal use, but should not need to learn the project's internal implementation before deployment.

Write as if guiding the reader through a working installation in a conversation: tell them where to act, what to enter, what happens and where to go next. A long sequence of simple actions is preferable to a short page with missing steps.

## One canonical basic setup

The basic runbook has two consecutive parts, adjacent in the navigation:

1. `docs/quick-start.md` and `.ru.md`: fresh Ubuntu, APT prerequisites, source/configuration, human administrator key, host setup, verified administrator login, SSH hardening, one Coolify installation, first account, Skip Setup, existing localhost and dashboard HTTPS.
2. `docs/operations/first-app.md` and `.ru.md`: separate demonstration repository, initial image publication, package visibility, application HTTPS and healthy first deployment, dedicated CI key/account, Coolify API token, GitHub environment, enabled CD, subsequent PR/main release, runtime variables/secrets handling and live logs.

All mandatory actions belong inside these pages. A required instruction such as “configure CI according to another chapter” is a broken handoff. The only required page transition is the explicit continuation from part one to part two.

End part two with the achieved basic result and permission to move on to the reader's own application. After that, offer additional tasks: application configuration, independent uptime alerts, off-site backups, PostgreSQL backup/restore and retained logs. Live logs and basic runtime ENV belong in the base; external storage and Grafana do not.

Reference and operations chapters may remain extensive. Their purpose is to explain a contract or complete a separate task, not supply missing pieces of the base runbook. Keep one canonical installation procedure; link to it from README and CI reference rather than maintaining alternative copies.

## Write each step completely

Each step needs:

- a task title with a concrete action;
- the execution location: workstation shell, VPS shell and account, GitHub page, Coolify page or DNS panel;
- required input and its exact source before use;
- a copyable command or specific UI action;
- a short purpose when it helps the reader understand the action;
- an observable expected result and a clear next action.

Group commands only when they are safe to run consecutively in the same shell and directory. Split at a required result, account change, terminal change or UI action. Do not hide a failed starter command beneath a following `cd`, `git init` or `git add .`.

Use ordinary Russian in Russian prose. Preserve actual English UI labels and machine-readable identifiers. Avoid sentences assembled from unnecessary English terms such as “подготовьте application-owned runtime config и проверьте hosted proof”. Prefer “задайте переменную в Coolify и проверьте ответ приложения”.

Explain a concept where it changes the reader's action. Internal milestone names, role paths, validation levels, architecture defenses and release history belong in maintainer material.

## Commands and UI must survive copy/paste

- Provide separate PowerShell and Linux blocks where syntax differs. Use `Join-Path` for Windows paths; a missing separator before `.ssh` must not silently select a different directory.
- Introduce a key's filename once and use it consistently for generation, `scp`, config, fingerprint and GitHub secret. Explain whether the command uses the public or private file.
- Never overwrite an existing key or application directory to make the walkthrough succeed. Put the conditional instruction before the command.
- Do not assume shell variables survive a new terminal. Recreate them when needed.
- Tell the reader whether a YAML fragment replaces fields or adds a section. Preserve the rest of the config and avoid duplicate top-level keys.
- Keep examples generic and semantically obvious. In guided user commands prefer named values such as `SERVER_IP` and `ADMIN_USER` over a concrete documentation IP or a hard-coded default username. If a block is meant to be copied, define shell/PowerShell variables first; do not put literal `<SERVER_IP>`-style angle-bracket placeholders into executable shell commands because the shell treats `<` and `>` as syntax. Reserved documentation IPs/domains are still acceptable in explanatory prose and non-copyable examples. Never copy operator values, private transcripts or runtime identifiers into public files.
- The configured administrator name is a product input, not a documentation constant. A default such as `ops` may be shown where the config field is introduced, but subsequent instructions should derive the login from the configured `admin.user` rather than assuming the default forever.
- UI instructions identify the sidebar entry, page and field. Dashboard URL belongs to sidebar Settings, not the server's SSH IP Address/Domain field.
- Verify the UI of the pinned version. Include consequential details such as Skip Setup, configuring image/hash fields after resource creation, runtime versus build-time ENV, API token permission selection order and GitHub environment versus repository variables.
- State the source of every GitHub value. Distinguish the CI key fingerprint, server host-key line and application UUID. A table of unexplained names is not an installation procedure.
- Keep values in the same order when generating and entering them. Say where to retain them and which later step uses them. Prefer commands that print the exact value to paste; explicitly preserve required prefixes such as `SHA256:`.
- Document token scope and expiry accurately. Do not claim a team token is restricted to one application.

## Remove friction without hiding essential checks

Keep the fresh administrator login and sudo check before SSH hardening. Keep meaningful first-image health and subsequent-version checks: they show whether the reader succeeded.

Where automation already verifies its mutation, do not ask the reader to repeat the same check. Run the aggregate host verification once where the current lifecycle requires it. Second-run idempotency, repeated audit chains, intentional failures and evidence collection belong in maintainer acceptance procedures.

Do not preserve the chronology of bugs discovered while writing the guide. If a development-time failure taught a general lesson, express the final safe rule once in the normal path or in a short troubleshooting entry; keep the debugging story in reviews/ROADMAP/Git history.

Do not invent an automated behavior to shorten the instructions. If an obligatory check is not included in a command, show it or fix the product in a separate authorized change. Move rare failure branches into troubleshooting after the normal path.

Do not promise production readiness, fixed installation time, recovery or full validation based on a Markdown rewrite. Distinguish source/UI checks, operator-observed stages and a full replay of the written instructions in the ROADMAP.

## Examples of changes this policy requires

| Incomplete instruction | Required replacement |
| --- | --- |
| “Connect CI; see the CI chapter” | Key generation and upload, config edit, account creation, token, every GitHub field and a successful automatic release on the same page |
| “Set the application UUID” | Explain the `/application/` segment of the application URL and exclude project/server IDs |
| “Add runtime ENV and see the docs” | Exact Name/Value, Runtime on, Buildtime off, Save, Redeploy and the changed HTTP response |
| “Install Coolify, then configure it” | Installation result, private access, registration, Skip Setup, existing localhost, precise Settings URL field and HTTPS login |
| “Everything passed; setup is done” | Observable application version, health response, log entries and honest boundaries for optional backup/history |

## Updating and validating documentation

After the two basic setup chapters, use a separate **After basic setup** section. Number only action guides that a reader can complete as a concrete setup task. Retained logs, database backup/restore, outage alerts, off-site recovery and host metrics fit that sequence. Incident response, planned maintenance and upgrade runbooks belong in the operations/maintenance reference tree rather than being numbered as another setup chapter. Add a visual daily-use explanation of the code-to-production path and common incidents near the guided route. Keep development plans, ADR identifiers and release evidence outside this user route. Do not present a renamed technical reference as a completed beginner walkthrough.

The rendered navigation should make the canonical guided path visually stronger than deep reference trees. Use typography/color sparingly: numbered tutorial pages may be emphasized, while deployment/host/reference catalogs should remain discoverable but visually quieter.

Update English and Russian together, with equivalent commands, settings, ordering and safety boundaries. Keep Markdown links language-neutral so MkDocs resolves the selected locale. The first two navigation pages and footer continuation must match the runbook sequence.

Before finishing a documentation change:

1. Walk the commands and UI steps against current source and the pinned upstream UI. Check account, working directory, inputs, outputs and the next step.
2. Run the strict EN/RU documentation build, link/anchor checks and applicable documentation/public-hygiene validators.
3. Inspect the rendered pages, tabs, tables, code blocks and next-page navigation.
4. Record what has actually been tested and the remaining operator replay in `ROADMAP.md`.

When user feedback exposes a missing command or ambiguous UI location, correct the canonical page before continuing to rely on chat-only instructions. Update this policy if the feedback changes the general writing contract.
