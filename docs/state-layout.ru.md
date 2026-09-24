# Постоянное состояние и source checkout

Solo VPS намеренно разделяет **заменяемый source code** и **installation state, принадлежащий оператору**. Обновление или повторный clone репозитория не должны уничтожать config, inventory, encrypted secret bundles или recovery metadata.

## Структура Linux по умолчанию

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

Выполните:

```bash
make paths
```

чтобы увидеть реальные active paths, а не полагаться на defaults.

## Что хранится в source checkout

Git checkout содержит публичный/reviewable source продукта: Ansible, scripts, templates, example config, docs, tests и contracts.

Не создавайте mutable installation config или plaintext credentials внутри checkout.

## Что остаётся вне Git

Persistent Solo VPS data включает:

- активные `config.yml` и inventory;
- pinned controller toolchain state;
- SOPS policy/public recipient metadata;
- encrypted backup/observability secret bundles;
- local validation evidence, включая `evidence/disposable-clean-target/`, если используется этот maintainer harness;
- небольшие operator ownership/state records.

Directory `state/database-backups/` хранит небольшие ownership records для Solo VPS-managed Coolify backup schedules. **Database или S3 credentials там не хранятся**.


## Runtime state VPS — отдельный слой

Часть runtime state не относится ни к Git, ни к controller data directory:

```text
/data/coolify/                 Coolify runtime/application state
/etc/solo-vps/backup/         root-only backup runtime credentials/config
/run/solo-vps-docker-api/     optional observability runtime socket/state
/etc/tmpfiles.d/solo-vps-observability.conf
```

## Обновления source

Source update не должен молча заменять persistent config. Нормальный pattern:

```text
review new Solo VPS source
→ run source validation
→ inspect upgrade/release notes
→ use existing persistent state
→ run doctor/verify before mutation
```

Удаление `~/solo-vps` не удаляет `~/.local/share/solo-vps/`, `/data/coolify/` или root-only runtime credentials.

## Переезд в новый checkout

До удаления старого checkout:

1. выполните `make paths`;
2. убедитесь, что external data directory зарезервирован согласно вашей policy;
3. clone/extract проверенный replacement source;
4. выполните `make setup` / controller checks против существующего state;
5. выполните `make doctor` до target mutation.

Предыдущий checkout не является generic runtime rollback mechanism. См. [руководство по обновлению](upgrades.md).
