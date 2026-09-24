# ADR-0003: Use Coolify-native logical backups for Coolify-managed databases

Status: Accepted  
Date: 2026-08-11

## Context

The Passport assigns application and database lifecycle to Coolify, while restic is the host/off-site backup layer. M14 deliberately rejects raw backups of live PostgreSQL storage, so M15 needs an application-aware database strategy.

The legacy project created its own PostgreSQL platform and its own `pg_dump` staging scripts. That architecture is no longer the default: the current project intends Coolify to own application databases.

Current Coolify provides scheduled PostgreSQL backups itself. Its documented PostgreSQL backup uses custom-format `pg_dump` with `--no-acl` and `--no-owner`, and scheduled backups can be sent to S3-compatible storage. PostgreSQL custom-format archives can be inspected with `pg_restore --list` and restored with `pg_restore`.

This creates a responsibility question: should Solo VPS build a second Ansible/restic logical-dump scheduler, or integrate with the database backup capability already owned by the application platform?

## Decision drivers

- preserve the Passport boundary: Coolify owns application/database lifecycle;
- avoid two independent schedulers producing competing database backups;
- use logical PostgreSQL backups rather than live `PGDATA` copies;
- keep database credentials out of public host configuration;
- require off-site storage and explicit retention;
- keep restore verification as required evidence, not an assumption;
- avoid coupling host-level restic jobs to Coolify container names and internal layouts.

## Options considered

### 1. Build an Ansible-managed `pg_dump` + restic staging pipeline

This matches the legacy chapter closely, but duplicates Coolify's database-backup scheduler and forces the host layer to understand application database credentials, container identity, scheduling and retention.

### 2. Use Coolify-native scheduled PostgreSQL backups with S3-compatible storage

Coolify owns scheduling and database access. Solo VPS defines the safety contract, configures/integrates the capability through a supported interface after M9 is available, and verifies backup/restore evidence.

Host-level restic remains responsible for the reviewed host/control-plane filesystem scope rather than becoming a second database scheduler.

### 3. Require an external managed database/backup service

This can be appropriate for larger workloads but adds another mandatory provider and is outside the current single-VPS core scope.

## Decision

Use option 2 for PostgreSQL databases managed by Coolify.

Accepted responsibility boundary:

```text
Coolify-managed PostgreSQL
  -> Coolify scheduled logical pg_dump
  -> S3-compatible off-site database backup
  -> Coolify/API operational configuration

Solo VPS / Ansible
  -> host baseline
  -> database-backup safety policy and verification
  -> no second pg_dump scheduler
  -> no live PGDATA backup

restic
  -> host/control-plane filesystem recovery scope
  -> not the default PostgreSQL logical-backup scheduler
```

The operational source contract now carries explicit starter values together with the supported Coolify API integration: daily scheduling, two local copies, 30 days of S3 retention, and a 36-hour freshness threshold. They remain reviewable policy rather than proof; the external-validation window must still demonstrate real off-site behavior and may adjust the values if the recovery objective requires it.

## Consequences

### Positive

- avoids duplicate database backup orchestration;
- keeps database credentials inside the application-platform boundary;
- follows Coolify's supported database-backup workflow;
- keeps M14 restic policy smaller and independent from Coolify container internals;
- preserves custom-format PostgreSQL archives that can be inspected before restore.

### Negative

- database backup availability now depends on Coolify and its supported backup interface;
- M15 configuration depends on the supported Coolify backup API and its backup-execution model, so pinned Coolify upgrades must re-test this integration;
- host-level restic snapshots and database backups have separate schedules/retention and must both be represented in DR documentation;
- a Coolify instance backup alone does not protect application database/volume data.

## Migration / rollback impact

Acceptance of this ADR changes no host or database state by itself.

The accepted decision means the legacy custom `pg_dump`/restic runner is not migrated as the default. A future database that is not managed by Coolify may need a separate application-aware backup adapter, but that should be an explicit exception rather than expanding the host layer by default.

Rollback from the decision is possible by introducing a separate logical-backup implementation later, but that would add a second scheduler and secret boundary and should be treated as a new architecture decision.

## Validation

Evidence supporting acceptance:

1. Coolify's current documentation confirms scheduled PostgreSQL backups and S3-compatible storage;
2. the documented Coolify PostgreSQL command uses custom-format `pg_dump` with `--no-acl` and `--no-owner`;
3. PostgreSQL documents `pg_restore --list` for inspecting custom-format archive contents;
4. M14 already rejects live PostgreSQL data directories as raw restic sources;
5. local policy validation rejects an Ansible/restic PostgreSQL dump scheduler in the accepted contract.

Evidence required before M15 completion:

6. source tests prove loopback-only API configuration, explicit ownership/adoption, schedule/retention drift detection, trigger/freshness handling, disposable-target restore safety, and secret redaction;
7. configure the backup through the supported Coolify interface during external validation;
8. prove the target repository is off-site and credentials are not exposed through public config/logs;
9. create a real PostgreSQL backup and independently verify the S3 object exists;
10. inspect and restore the real archive into a disposable PostgreSQL database and verify application-relevant data;
11. feed schedule, retention, freshness and restore evidence into M16 recovery documentation.
