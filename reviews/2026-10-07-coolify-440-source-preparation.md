# Coolify 4.4.0 source preparation — 2026-10-07

## Scope and evidence

Prepare the published Solo VPS 0.1.0 installation for a reviewed `4.3.21 → 4.4.0` transition. No production access, VPS mutation, release tag or GitHub Release belongs to this source pass. The release remains a source candidate until test-VPS qualification.

The full upstream 4.4.0 release notes and tagged Compose/env files were read. Realtime is now Reverb inside the main Coolify container. The retained `coolify-realtime` network alias keeps existing proxy upstreams working; `soketi` is an inactive compatibility profile. Reverb uses `/up`, and terminal port 6002 still provides `/ready`. Sentinel remains a privileged Coolify component and must keep its HTTPS communication/private API boundary.

The source uses one read/write/deploy API token, version-neutral evaluation commands, a single authoritative release manifest in role defaults, separate read-only discovery/source preparation/runtime upgrade steps, atomic local-backend migration, and resume bound to exact marker lines plus artifact/port-override identity. Custom realtime backend host/port settings are rejected before mutation instead of being silently changed.

Local checks cover deployment and rollback helpers, the actual CI preflight, credential preservation, custom-backend rejection, source/policy consistency, update discovery and shell-safe command rendering. The EN/RU site builds. Browser checks confirm assignment substitution in Bash/PowerShell, YAML values, clipboard newlines, cross-page persistence, GitHub SSH URLs and reset to original prompts. Independent review found no remaining material issue after the backend/SSH-URL fixes.

Archive inspection in the upgrade checkpoint is not a restored-database proof. Old 4.3.21 runtime/clean-host evidence does not qualify 4.4.0. The feature branch must stay out of public main until the runtime gate is reviewed.

## Next test-VPS gate

Use only the owner-authorized non-production target. Check provider recovery access and retain a provider snapshot before intentional interruption. Preserve the old checkout and existing external controller state. Use a separate candidate checkout and verify the exact source commit and inventory host/user before every remote command. Do not copy test or production credentials into source/evidence.

1. Establish the 4.3.21 baseline: dashboard, Sentinel In Sync, app health/revision, Docker/SSH baseline and private management ports. Inspect only non-secret version/marker fields; never dump `.env`.
2. Run `make updates-plan`, `make platform-lifecycle-plan` and `make coolify-upgrade-preflight` with the test HTTPS `COOLIFY_SENTINEL_URL`. Confirm the local checkpoint procedure and ensure no deployments/UI changes are in progress.
3. For the deliberate interruption exercise, initialize isolated evaluation controller state and a non-secret `COOLIFY_EVALUATION_TARGET_ID`. Configure it for the existing test target, select the proven admin inventory, and run `coolify-evaluate-preflight`.
4. Run `coolify-evaluate-upgrade` with `COOLIFY_EVALUATION_CONFIRM=I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_TARGET` and `COOLIFY_EVALUATION_INTERRUPT_AFTER_MARKER=true`. Expected failure occurs after the protected checkpoint/marker and before target promotion. Preserve both.
5. Run `coolify-evaluate-resume` with the same evaluation identity and confirmation. Verify 4.4.0, Reverb `/up`, terminal `/ready`, the old realtime container's removal, loopback-only ports, dashboard websocket/terminal and Sentinel In Sync.
6. Re-run upgrade preflight/upgrade to prove the current-target no-op; then `make verify`, `make audit`, an immutable image deployment with the combined token, and existing app/data behavior. Check backup UI/API compatibility separately if that optional profile is enabled.
7. Record source commit, observed versions, command outcomes and recovery limits. Only then consider production migration; production remains a separate owner-authorized operation.

The evaluation commands intentionally require isolated controller state. For a non-interrupted ordinary test upgrade, the normal `coolify-upgrade` command accepts only the reviewed version pair and its explicit upgrade confirmation. The Coolify Update button is outside this qualified transaction path.
