# Persistent state and source checkout

Solo VPS deliberately separates **replaceable source code** from **operator-owned installation state**. Updating or recloning the repository should not destroy your config, inventory, encrypted secret bundles, or recovery metadata.

## Default Linux layout

```text
~/solo-vps/                              Git checkout
~/.local/share/solo-vps/
├── config/
│   ├── config.yml
│   └── hosts.yml
├── toolchain/
├── sops/
├── secrets/
│   ├── backup.enc.yaml
│   └── observability.enc.yaml
├── evidence/
│   └── disposable-clean-target/
└── state/
    └── database-backups/
```

Use:

```bash
make paths
```

to print the active paths rather than assuming defaults.

## What belongs in the source checkout

The Git checkout contains public/reviewable product source: Ansible, scripts, templates, example config, docs, tests, and contracts.

Do not create mutable installation config or plaintext credentials inside the checkout.

## What stays outside Git

Persistent Solo VPS data includes:

- active `config.yml` and inventory;
- pinned controller toolchain state;
- SOPS policy/public recipient metadata;
- encrypted backup/observability secret bundles;
- local validation evidence, including `evidence/disposable-clean-target/` when that maintainer harness is used;
- small operator ownership/state records.

The `state/database-backups/` directory stores small ownership records for Solo VPS-managed Coolify backup schedules. It **does not store database or S3 credentials there**.


## VPS runtime state is separate again

Some runtime state belongs neither in Git nor in the controller data directory:

```text
/data/coolify/                 Coolify runtime/application state
/etc/solo-vps/backup/         root-only backup runtime credentials/config
/run/solo-vps-docker-api/     optional observability runtime socket/state
/etc/tmpfiles.d/solo-vps-observability.conf
```

## Source updates

A source update must not silently replace persistent config. The normal pattern is:

```text
review new Solo VPS source
→ run source validation
→ inspect upgrade/release notes
→ use existing persistent state
→ run doctor/verify before mutation
```

Deleting `~/solo-vps` does not delete `~/.local/share/solo-vps/`, `/data/coolify/`, or root-only runtime credentials.

## Moving to a replacement checkout

Before deleting an old checkout:

1. run `make paths`;
2. confirm the external data directory is backed up as required;
3. clone/extract the reviewed replacement source;
4. run `make setup` / controller checks against the existing state;
5. run `make doctor` before target mutation.

A previous checkout is not a generic runtime rollback mechanism. See [Upgrade guide](upgrades.md).
