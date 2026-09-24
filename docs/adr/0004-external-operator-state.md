# ADR-0004: Keep operator/controller state outside the Git checkout

Status: Accepted  
Date: 2026-08-14

## Context

Early PRE-ALPHA builds stored ignored `config.yml`, inventory, the controller virtualenv, generated public SOPS policy, and handoff markers inside the Solo VPS checkout. This made source replacement fragile: an archive/reclone could silently remove required local files, while a future Git update could be complicated by generated checkout-local state.

The public product is intended to be easy to update and safe to re-clone. Per-installation state should also survive deletion of the source tree.

## Decision

Treat the Git checkout as disposable product source.

On Linux, mutable per-user Solo VPS controller/operator state defaults to:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/solo-vps
```

This root owns persistent config/inventory and the pinned controller QA/runtime toolchain. Generated public SOPS workstation policy also defaults outside the checkout. Windows workstation helpers use `%LOCALAPPDATA%\solo-vps\state` for that generated public policy/recipient state. The private age key remains in the workstation's protected key path rather than being moved into the public/operator data set.

System/runtime state continues to use the correct service-owned locations, including `/data/coolify` and Ansible-managed `/etc` files.

Legacy checkout-local config/inventory may be copied forward by `make init`, but automated migration does not delete the originals.

## Consequences

Positive:

- `git pull`, source replacement, and re-clone no longer depend on ignored config/inventory surviving inside the repository;
- controller toolchain state survives source replacement;
- public repository hygiene is simpler;
- backup/recovery can treat product source and installation state as separate concerns.

Trade-offs:

- users need one documented persistent data root in addition to the source checkout;
- old PRE-ALPHA installations need a one-time migration via `make init`;
- paths in documentation and contract tests must not drift back to checkout-local defaults.

This does not add a second controller, VPS, service, or configuration database.
