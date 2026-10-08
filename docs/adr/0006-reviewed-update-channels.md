# ADR-0006: Separate update discovery, source preparation and platform upgrades

Status: Accepted
Date: 2026-10-07

## Context

Coolify publishes more frequently than Solo VPS. The 0.1.0 alpha used Coolify 4.3.21; 4.4.0 moves realtime into the main container and requires changes to the loopback override and runtime verification. Installing whichever version upstream advertises would bypass this compatibility work.

## Decision

Use the version-neutral release manifest in `config/coolify-release.yml` as the authoritative target, supported origin, image identity and artifact SHA256 source. The lifecycle policy is a checked contract summary. Evaluation playbooks reuse the role manifest instead of copying pins. Executable filenames and Make targets are version-neutral; historical evidence retains versioned names.

A compatible upstream release changes version/component identities and artifact hashes in this one manifest. Image references, download URLs, planners, restore expectations and current documentation derive from it. Integration changes still require code and tests. Evidence is bound to the exact manifest fingerprint; updating a version cannot inherit earlier qualification. Descriptive qualification metadata is excluded from execution identity. Sentinel is reconciled by Coolify and has explicit reviewed origin/target identities, including a deliberate allowance for the target agent to arrive before the platform update.

`updates-check` reads public release metadata and reports upstream separately from the reviewed target and its evidence. `updates-plan` is offline. Neither changes source, config or runtime. Upstream release availability is never installation approval.

`source-update-prepare` clones an explicitly selected, published exact Solo VPS tag into a new sibling checkout. Existing installation state stays outside Git; the old checkout remains available. New source does not apply Ansible implicitly. Compatibility-only changes may ship as patch releases; a Coolify patch does not force a Solo VPS minor release. We do not distribute an executable remote compatibility catalog independent of the source release.

Coolify runtime mutation continues through explicit preflight, a private local control-plane checkpoint, checksummed artifacts, a protected transaction marker, verification and forward resume. Resume binds exact marker lines and release artifact/override identity. Existing application secrets and instance credentials are preserved. A version rollback cannot undo database migrations. The local checkpoint is retained; successful dump/archive inspection is not a database restore exercise.

The Coolify Update button and floating upstream scripts are outside the qualified path. Keep `AUTOUPDATE=false`. An upstream update may overwrite the managed Compose policy and bypass our checkpoint and markers.

Coolify's explicit proxy Compose invocation does not load an implicit override. Ansible specifies the TCP edge policy through native Get/Save configuration actions; Coolify remains the proxy lifecycle owner. Only the ports field changes, with image/network preflight before a required native restart. A bounded host guard blocks upstream TCP 8080/UDP 443 on external ingress before Docker can start containers, covering the first-start reconciliation window and reboot. It preserves shared firewall rules and original-direction outbound replies; IPv4 and IPv6 are guarded independently.

## Consequences and qualification

Traefik updates are a separate explicit native lifecycle, also described by the
shared release manifest. The controller verifies reviewed source content and an
immutable target digest, changes only the image scalar, records a private checkpoint
before Save and retains a transaction for explicit resume. Rollback pins the saved
previous digest because native StartProxy pulls before recreation; registry access
is required. Saved proxy files are retained for manual recovery and current
certificates are not overwritten automatically. The ordinary ports-only reconciler
does not change the proxy image. Image IDs may expose a containerd index or classic
Docker platform-config identity; both reviewed representations are explicit.

Operators update Solo VPS source when a newer reviewed integration is needed, and update Coolify as a separate explicit action. The checkout cannot verify arbitrary future Coolify versions. This preserves one host owner and one application platform owner.

The disposable `4.3.21 → 4.4.0` transition passed V3 qualification: interruption/resume, checkpoint database restore, no-op rerun, private ports, working Reverb/terminal, Sentinel delivery, unchanged Docker/SSH identity, one-token immutable app delivery/rollback and reboot. See [the runtime record](https://github.com/paracosm17/solo-vps/blob/main/reviews/2026-10-07-coolify-440-runtime.md). Fresh installation, production migration and release publication remain separate gates and owner actions.
