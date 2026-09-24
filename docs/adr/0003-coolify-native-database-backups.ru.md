# ADR-0003: Использовать нативные логические backup Coolify для баз данных под управлением Coolify

Статус: Принято  
Дата: 2026-08-11

## Контекст

Passport назначает lifecycle приложений и баз данных Coolify, тогда как restic отвечает за host/off-site backup layer. M14 намеренно запрещает raw backup живого PostgreSQL storage, поэтому M15 требует application-aware стратегии backup БД.

Старый проект создавал собственную PostgreSQL-платформу и собственные `pg_dump` staging scripts. Эта архитектура больше не является default: текущий проект ожидает, что базами данных приложений владеет Coolify.

Текущий Coolify сам предоставляет scheduled PostgreSQL backups. Его документированный PostgreSQL backup использует custom-format `pg_dump` с `--no-acl` и `--no-owner`, а scheduled backups могут отправляться в S3-compatible storage. PostgreSQL custom-format archives можно инспектировать через `pg_restore --list` и восстанавливать через `pg_restore`.

Отсюда возникает вопрос ответственности: должен ли Solo VPS строить второй Ansible/restic scheduler логических дампов или интегрироваться с database-backup capability, которой уже владеет application platform?

## Факторы решения

- сохранить границу Passport: Coolify владеет lifecycle приложений/БД;
- не иметь два независимых scheduler-а, создающих конкурирующие database backups;
- использовать логические PostgreSQL backups вместо копирования живого `PGDATA`;
- держать database credentials вне публичной host-конфигурации;
- требовать off-site storage и явную retention policy;
- считать restore verification обязательным evidence, а не предположением;
- не связывать host-level restic jobs с именами контейнеров и внутренним layout Coolify.

## Рассмотренные варианты

### 1. Построить Ansible-managed `pg_dump` + restic staging pipeline

Это близко к legacy chapter, но дублирует database-backup scheduler Coolify и заставляет host layer знать application database credentials, container identity, scheduling и retention.

### 2. Использовать Coolify-native scheduled PostgreSQL backups с S3-compatible storage

Coolify владеет scheduling и database access. Solo VPS определяет safety contract, настраивает/интегрирует capability через поддерживаемый интерфейс после появления M9 и проверяет backup/restore evidence.

Host-level restic продолжает отвечать за проверенный host/control-plane filesystem scope, а не становится вторым database scheduler.

### 3. Требовать внешний managed database/backup service

Это может быть уместно для крупных workloads, но добавляет ещё одного обязательного провайдера и находится вне текущего core scope «один VPS».

## Решение

Использовать вариант 2 для PostgreSQL databases под управлением Coolify.

Принятая граница ответственности:

```text
PostgreSQL под управлением Coolify
  -> Coolify scheduled logical pg_dump
  -> S3-compatible off-site database backup
  -> operational config через Coolify/API

Solo VPS / Ansible
  -> host baseline
  -> safety policy и verification для database backup
  -> без второго pg_dump scheduler
  -> без backup живого PGDATA

restic
  -> filesystem recovery scope хоста/control-plane
  -> не default PostgreSQL logical-backup scheduler
```

Operational source contract теперь содержит явные стартовые значения и поддерживаемую Coolify API integration: daily schedule, две локальные копии, 30 дней S3 retention и freshness threshold 36 часов. Это reviewable policy, а не proof; внешний validation window всё равно должен доказать реальное off-site поведение и при необходимости изменить значения под recovery objective.

## Последствия

### Плюсы

- нет дублирования database backup orchestration;
- database credentials остаются внутри границы application platform;
- используется поддерживаемый Coolify database-backup workflow;
- M14 restic policy остаётся меньше и не зависит от внутренних контейнеров Coolify;
- сохраняются PostgreSQL custom-format archives, которые можно проверить до restore.

### Минусы

- доступность database backup теперь зависит от Coolify и его поддерживаемого backup interface;
- конфигурация M15 зависит от поддерживаемого Coolify backup API и модели запуска backup, поэтому pinned Coolify upgrades должны повторно тестировать интеграцию;
- host-level restic snapshots и database backups имеют разные schedule/retention и оба должны быть отражены в DR-документации;
- backup самого экземпляра Coolify не защищает данные application database/volume сам по себе.

## Влияние на миграцию / rollback

Принятие ADR само по себе не меняет состояние хоста или базы данных.

Решение означает, что legacy custom `pg_dump`/restic runner не мигрируется как default. Для будущей БД, которой не управляет Coolify, может понадобиться отдельный application-aware backup adapter, но это должно быть явным исключением, а не автоматическим расширением host layer.

Откат от решения возможен через добавление отдельной logical-backup реализации позже, однако это создаст второй scheduler и secret boundary и должно рассматриваться как новое архитектурное решение.

## Проверка

Evidence в поддержку принятия:

1. текущая документация Coolify подтверждает scheduled PostgreSQL backups и S3-compatible storage;
2. документированная PostgreSQL-команда Coolify использует custom-format `pg_dump` с `--no-acl` и `--no-owner`;
3. PostgreSQL документирует `pg_restore --list` для инспекции custom-format archive;
4. M14 уже запрещает raw restic sources для живых PostgreSQL data directories;
5. локальная policy validation запрещает Ansible/restic PostgreSQL dump scheduler в принятом contract.

Evidence, необходимое до завершения M15:

6. source tests доказывают loopback-only API configuration, явное ownership/adoption, detection schedule/retention drift, trigger/freshness handling, safety disposable-target restore и secret redaction;
7. настроить backup через поддерживаемый Coolify interface во время external validation;
8. доказать, что target repository находится off-site и credentials не раскрываются через public config/logs;
9. создать реальный PostgreSQL backup и независимо доказать существование S3 object;
10. проинспектировать и восстановить реальный archive в disposable PostgreSQL database и проверить application-relevant data;
11. передать schedule, retention, freshness и restore evidence в recovery documentation M16.
