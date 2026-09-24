# ADR-0001: Сохранить владение хостом при установке Coolify

Статус: Принято  
Дата: 2026-08-11

## Контекст

Solo VPS уже считает Ansible источником истины для уровня хоста: административного доступа, firewall-политики, Docker Engine и `/etc/docker/daemon.json`. Coolify выбран как платформа приложений, и его установка входит в Ansible-backed подготовку хоста, но runtime-состояние и состояние приложений Coolify не должны становиться второй копией автоматизации хоста.

Официальный quick installer Coolify удобен на обычном сервере, но он также вносит привилегированные изменения в хост. На момент принятия этого решения он устанавливает/настраивает Docker, управляет настройками Docker daemon, создаёт SSH-материалы Coolify и подготавливает `/data/coolify`. Это пересекается с состоянием, которым Solo VPS уже управляет явно.

Coolify также документирует ручной путь установки. Управление сервером без root существует upstream, но всё ещё обозначено как experimental. Текущий администратор Solo VPS из M4 уже имеет SSH-ключ и passwordless sudo, поэтому повторно открывать root SSH только ради Coolify означало бы ослабить существующую границу без доказанной необходимости.

## Факторы решения

- сохранить одного понятного владельца конфигурации хоста;
- не откатывать незаметно security baseline M4/M5/M7;
- сделать установку воспроизводимой и пригодной для review;
- намеренно pin-ить инфраструктурные зависимости и зависимости application platform;
- по умолчанию не выставлять first-run management наружу;
- не хранить runtime-состояние и секреты Coolify в plaintext Git;
- сделать будущие обновления явной и тестируемой операцией.

## Рассмотренные варианты

### 1. Запускать upstream quick installer без изменений

Просто и официально рекомендуется для generic installation, но пересекается с Docker- и SSH-состоянием, которым владеет Ansible. Как непрозрачный backend для текущего host contract этот вариант неприемлем.

### 2. Временно отдать quick installer владение хостом, затем выполнить reconcile

Технически возможно, но создаёт ненужный промежуточный drift и более широкую поверхность отказа/восстановления. Reconciliation также пришлось бы доказывать, что изменения Docker со стороны installer не ломают Coolify после возврата Ansible baseline.

### 3. Использовать upstream manual installation flow с pinned release artifacts

Сохраняет upstream deployment model Coolify и при этом оставляет владение хостом явным за Solo VPS. Candidate artifacts, secrets, exposure и запуск сервисов можно готовить и проверять независимо.

## Решение

Использовать вариант 3 как backend установки Coolify в Solo VPS.

Принятая граница владения:

```text
Ansible / Solo VPS
  /etc/ssh/*
  /etc/ufw/* и firewall-политика хоста
  пакеты/сервисы Docker
  /etc/docker/daemon.json
  автоматизация установки/readiness/recovery

Coolify runtime
  /data/coolify/*
  контейнеры/networks/volumes Coolify
  состояние приложений/proxy/runtime
```

Для первоначальной реализации:

- pin-ить release Coolify в коде проекта, а не в пользовательской конфигурации;
- явно задавать tag application image Coolify той же точной версии, не используя fallback Compose `LATEST_IMAGE:-latest`;
- брать installation artifacts из точного upstream Git tag и проверять SHA-256 checksums;
- не использовать плавающий `latest` как identity установки;
- не открывать root SSH повторно;
- перед операциями M9 требовать, чтобы inventory использовал `admin.user` из M4;
- сохранять точный Docker daemon baseline из M7 и fail-ить при ownership drift;
- хранить `/data/coolify/source/.env` и сгенерированные секреты на target, вне Git;
- не включать unattended Coolify upgrades, пока отдельно не проверен upgrade artifact/version contract;
- для first-run management использовать SSH tunnel, а не публичные management-порты.

Механизм loopback exposure уже определён для pinned release: Solo VPS добавляет финальный project-owned Compose override с Docker Compose `!override`, который заменяет upstream port lists для `coolify` и `soketi` на bindings `127.0.0.1` для 8000, 6001 и 6002. Это требует Docker Compose 2.24.4 или новее и проверяется M9 readiness.

Override статически проверяется против pinned port contract v4.1.2, но ещё не был прогнан на чистом target. Владелец проекта принял эту границу 2026-08-11; принятие — архитектурное решение, а не evidence интеграции на clean target.

### Уточнение M10: runtime-доступ без root

Реальное тестирование M10 выявило одну интеграционную деталь внутри принятой границы. В pinned Coolify v4.1.2 путь запуска proxy выполняет `cd /data/coolify/proxy` через SSH identity localhost-сервера перед запуском Docker Compose. Поскольку Solo VPS намеренно использует существующий non-root `admin.user` и держит root SSH закрытым, каждый родительский каталог этого пути должен быть traversable для SSH identity.

Первое исправление исходников предполагало, что UID-9999/group-traverse adjustment нужен только для `/data/coolify` и `/data/coolify/proxy`. Реальный target опроверг модель: после `make coolify` Coolify корректно сменил владельца каталога proxy на `admin.user`, но последующий `make verify-coolify` всё равно не мог войти в каталог. Review исходников объясняет оба наблюдения. Ansible может создать отсутствующий промежуточный `/data` с правами, переданными при создании `/data/coolify`, а pinned Coolify v4.1.2 намеренно выполняет chown путей `/data/coolify...`, создаваемых его non-root командой `mkdir -p`, на настроенного server user.

Поэтому Solo VPS владеет **ограниченным access envelope**, а не runtime-содержимым: `/data` — `root:root` mode `0711`; `/data/coolify` остаётся UID 9999 с `<admin-group>` mode `0710`; `/data/coolify/{applications,databases,services}` — UID 9999 с `<admin-group>` mode `0710`; `/data/coolify/backups` — UID 9999 с `<admin-group>` mode `0730`, чтобы non-root SSH identity могла создавать известные backup paths, но не листить namespace; `/data/coolify/proxy` намеренно принадлежит `admin.user` с mode `0700`. Sensitive source/SSH-каталоги и secret files сохраняют строгие режимы Coolify/Solo VPS. Read-only verification выполняет реальные access probes от имени `admin.user`, поэтому metadata-only проверка не пропустит restrictive ancestor или недоступный для записи backup root. Coolify по-прежнему владеет приложениями, конфигурацией proxy, базами данных, backup-файлами и runtime-содержимым под `/data/coolify`; Ansible reconciles только минимальный filesystem access, необходимый для принятой owner-ом non-root localhost control model.

## Последствия

### Плюсы

- политика хоста остаётся детерминированной и reviewable;
- quick installer не может незаметно перезаписать Docker-конфигурацию, которой владеет Ansible;
- первая установка может быть воспроизводимой из immutable release inputs;
- SSH hardening M4 остаётся целым;
- после установки Coolify остаётся владельцем application platform.

### Минусы

- Solo VPS должен поддерживать больше installation logic, чем при one-line installer;
- каждое намеренное обновление Coolify требует review release artifacts и upgrade behavior;
- manual backend может разойтись с будущими assumptions upstream installer и должен повторно тестироваться;
- non-root compatibility остаётся upstream experimental boundary и требует pinned-version integration tests; M10 уже обнаружил одно предположение о доступе к пути запуска proxy, которое Solo VPS обязан reconcile.

## Влияние на миграцию / rollback

Сам ADR не изменяет состояние хоста.

Будущий installation backend не должен автоматически усыновлять существующий `/data/coolify`. Если каталог или контейнер Coolify уже существует, процесс должен остановиться и использовать отдельный reconciliation/upgrade path.

Перед изменением установленного Coolify recovery-план должен учитывать `/data/coolify`, generated secrets, persistent application data и Docker host baseline M7. Дизайн backup/restore пока не завершён и остаётся более поздним milestone проекта.

## Проверка

Принятие ADR и завершение M9 — разные gates. Принятие ADR утверждает направление ownership/install backend; оно **не** утверждает, что backend прошёл integration testing. Это устраняет циклическую зависимость, при которой установка требовала бы принятой границы, а принятие границы — уже выполненной установки.

Evidence в поддержку принятого архитектурного решения:

1. **V1 завершено:** проверить точные pinned release artifacts/checksums;
2. **V1 завершено:** определить и статически проверить loopback-only стратегию `!override` для pinned Compose port contract.

Evidence, необходимое до статуса M9 `DONE`:

3. доказать merged Compose model и реальную reachability management ports на clean target;
4. установить на чистый поддерживаемый Ubuntu 24.04 target через `admin.user` + sudo;
5. доказать, что `/etc/docker/daemon.json` сохраняет значение M7 до и после установки;
6. доказать, что root SSH остаётся отключён после hardening M4;
7. доказать, что management ports по умолчанию не доступны публично;
8. проверить health Coolify и first-run registration flow;
9. выполнить второй installation/verification run без destructive reinitialization;
10. задокументировать и проверить recovery после failed install до признания backend зрелым.
