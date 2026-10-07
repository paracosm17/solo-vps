# ADR-0006: Separate update discovery, source preparation and platform upgrades

Status: Accepted
Date: 2026-10-07

## Context

Coolify publishes more frequently than Solo VPS. The 0.1.0 alpha used Coolify 4.3.21; 4.4.0 moves realtime into the main container and requires changes to the loopback override and runtime verification. Installing whichever version upstream advertises would bypass this compatibility work.

## Decision

Use the version-neutral release manifest in `config/coolify-release.yml` as the authoritative target, supported origin, image identity and artifact SHA256 source. The lifecycle policy is a checked contract summary. Evaluation playbooks reuse the role manifest instead of copying pins. Executable filenames and Make targets are version-neutral; historical evidence retains versioned names.

`updates-check` reads public release metadata and reports upstream separately from the reviewed target and its evidence. `updates-plan` is offline. Neither changes source, config or runtime. Upstream release availability is never installation approval.

`source-update-prepare` clones an explicitly selected, published exact Solo VPS tag into a new sibling checkout. Existing installation state stays outside Git; the old checkout remains available. New source does not apply Ansible implicitly. Compatibility-only changes may ship as patch releases; a Coolify patch does not force a Solo VPS minor release. We do not distribute an executable remote compatibility catalog independent of the source release.

Coolify runtime mutation continues through explicit preflight, a private local control-plane checkpoint, checksummed artifacts, a protected transaction marker, verification and forward resume. Resume binds exact marker lines and release artifact/override identity. Existing application secrets and instance credentials are preserved. A version rollback cannot undo database migrations. The local checkpoint is retained; successful dump/archive inspection is not a database restore exercise.

The Coolify Update button and floating upstream scripts are outside the qualified path. Keep `AUTOUPDATE=false`. An upstream update may overwrite the managed Compose policy and bypass our checkpoint and markers.

## Consequences and qualification

Operators update Solo VPS source when a newer reviewed integration is needed, and update Coolify as a separate explicit action. The checkout cannot verify arbitrary future Coolify versions. This preserves one host owner and one application platform owner.

The 4.4.0 source candidate requires disposable `4.3.21 → 4.4.0` qualification: interruption/resume, a no-op rerun, private ports, healthy Reverb/terminal, Sentinel, unchanged Docker/SSH, dashboard access and one-token immutable app delivery. Production migration and release publication are separate owner actions. Prior 4.3.21 evidence is historical and does not qualify 4.4.0.
