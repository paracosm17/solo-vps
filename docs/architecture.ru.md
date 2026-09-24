# Архитектура Solo VPS

<!-- Repository-level source documents intentionally remain outside the MkDocs site:
README.md, PROJECT_PASSPORT.md, ROADMAP.md and
.agents/skills/solo-vps-project-engineer/SKILL.md. -->

У Solo VPS одна архитектурная цель: сделать **владение хостом**, **владение application platform** и **владение recovery** достаточно явными, чтобы один VPS оставался понятным и управляемым.

`PROJECT_PASSPORT.md` задаёт **north-star product/architecture boundary**. `README.md` — **текущий user-facing supported contract**. `ROADMAP.md` отслеживает development/evidence state, а не определяет архитектуру.

## Иерархия source of truth

Если два документа кажутся противоречащими друг другу, используйте порядок:

```text
accepted ADR / explicit owner decision
-> PROJECT_PASSPORT.md
-> README.md
-> ROADMAP.md
-> current implementation
-> legacy research
```

Это не позволяет историческому эксперименту или незавершённому roadmap item незаметно превратиться в user contract.

## Принятая базовая модель

| Слой | Чем владеет | Чем не владеет |
| --- | --- | --- |
| **Ansible** | Ubuntu host, admin identity, SSH/sudo, firewall, security updates, Docker host baseline, verification, backup/recovery foundation | Application deployment state, domains/proxy lifecycle, app databases/services |
| **Coolify** | Applications/services, domains/TLS, deployments, live logs, runtime config/secrets, terminals, databases | Base OS hardening, host firewall, Ansible-owned Docker baseline |
| **GitHub Actions** | CI, tests, image build/publish, optional controlled deployment workflow | Интерактивное администрирование хоста по умолчанию |
| **GHCR** | Immutable container artifacts | Host configuration или application runtime configuration |
| **SOPS + age** | Infrastructure/recovery secrets в operator workflow | Online Vault-like brokering или обычный Coolify app-secret UX |
| **restic + off-site storage** | Filesystem/control-plane recovery material | Backup database экземпляра Coolify или владение application PostgreSQL |

Core profile оставляет management ports Coolify loopback-only. Public applications используют обычный web edge; CI обращается к Coolify API только через restricted deployment transport.

Optional retained historical application logs идут из non-root **Alloy** через **restricted Docker API proxy** по **Unix socket**. Collector не получает реальный Docker socket напрямую.

## Карта системы

```text
operator workstation
  |-- Git checkout (disposable source)
  |-- ~/.local/share/solo-vps (persistent controller state)
  |-- SOPS + age private identity
  |
  +-- Ansible ------------------------------+
  |                                         |
  +-- git push -> GitHub Actions -> GHCR     |
                                            v
                                  +----------------------+
                                  | Ubuntu 24.04 VPS     |
                                  |                      |
                                  | Ansible-owned host   |
                                  | - users / SSH / sudo |
                                  | - UFW / updates      |
                                  | - Docker host        |
                                  | - verify / audit     |
                                  | - backup foundation  |
                                  |                      |
                                  | Coolify platform     |
                                  | - apps / services    |
                                  | - proxy / TLS        |
                                  | - databases          |
                                  +----------+-----------+
                                             |
                                             +--> managed off-site storage
```

**Эта схема показывает ответственность**, а не доказывает, что каждый path уже получил end-to-end runtime validation.

## Основные flows

### Provision хоста

```text
make setup
-> make apply
-> make secure
-> make platform
-> make verify
```

`apply` владеет host baseline и admin handoff. SSH hardening остаётся отдельно safety-gated. Coolify устанавливается только на platform step.

### Доставка приложения

Manual first-app path:

```text
source repository -> Coolify -> Dockerfile build -> domain/TLS -> health check
```

Optional CI/CD path:

```text
git push -> GitHub Actions -> GHCR immutable digest
         -> restricted SSH local forward -> loopback Coolify API -> deploy
```

Application migrations остаются application-owned. Automated deployment rollback — только container-image rollback.

### Работа с secrets

```text
trusted workstation
  -> age private key stays on workstation
  -> SOPS ciphertext can be stored/transferred safely
  -> required plaintext is delivered over SSH stdin
  -> VPS receives root-only runtime files
```

Application runtime secrets обычно остаются в Coolify; infrastructure/recovery secrets используют SOPS + age.

### Backup и recovery

```text
/data/coolify recovery material -> restic -> external S3-compatible storage
Coolify instance database       -> logical Coolify backup
application PostgreSQL          -> Coolify-owned logical backup
```

Lost-VPS recovery объединяет эти inputs на свежем Ubuntu host. Копия на том же VPS не является off-site backup.

### Ежедневная эксплуатация

```text
GitHub Actions -> CI/build/deploy status
GHCR           -> artifact identity
Coolify        -> deployments, health, live logs, config/secrets, terminal
Grafana Cloud  -> optional retained historical application logs
```

`make ops-*` остаётся diagnostic fallback, а не вторым application control plane.

## Матрица владения

| Область | Authority |
| --- | --- |
| Ubuntu host baseline | Ansible |
| Human admin access / SSH hardening | Ansible + operator safety proof |
| Host firewall / updates | Ansible |
| Docker Engine host configuration | Ansible |
| Coolify installation integration | Solo VPS automation, при этом platform runtime принадлежит Coolify |
| Application lifecycle | Coolify |
| CI / build / image publication | GitHub Actions |
| Container artifacts | GHCR |
| Infrastructure/recovery secrets | SOPS + age |
| Host/Coolify filesystem backup | restic + managed off-site storage |
| Coolify-managed PostgreSQL backups | Coolify |
| Optional retained logs | Grafana Alloy -> restricted Docker API proxy -> Grafana Cloud |

Главное правило дизайна — не создавать двух конкурирующих owners одного и того же state.

## Принятые ADR

Владелец проекта принял ADR 0001–0004 ниже. **Acceptance устанавливает architecture boundary**, но само по себе не доказывает runtime behavior.

| ADR | Статус | Решение |
| --- | --- | --- |
| [`ADR-0001`](adr/0001-coolify-installation-boundary.md) | **Accepted** | Сохранить Ansible ownership host/Docker baseline и использовать pinned интеграцию Coolify |
| [`ADR-0002`](adr/0002-controller-side-sops-decryption.md) | **Accepted** | Оставить production age private key на workstation оператора; второй controller server не нужен |
| [`ADR-0003`](adr/0003-coolify-native-database-backups.md) | **Accepted** | Использовать Coolify-native logical backups для Coolify-managed PostgreSQL вместо конкурирующего dump scheduler |
| [`ADR-0004`](adr/0004-external-operator-state.md) | **Accepted** | Хранить per-installation controller state вне disposable Git checkout |

## Предложенные ADR

Предложенные записи не меняют поддерживаемую архитектуру до получения указанного evidence.

| ADR | Статус | Решение |
| --- | --- | --- |
| [`ADR-0005`](adr/0005-coolify-sentinel-trust-boundary.md) | **Proposed** | Принимать обязательный Sentinel только внутри проверенной high-trust границы Coolify после disposable runtime proof |

Долгоживущую boundary меняйте через update/supersede ADR, а затем согласованно обновляйте user docs и implementation.

## Trust и exposure boundaries

**Administrative access.** Изменения SSH/sudo/firewall критичны для доступа. Solo VPS сохраняет отдельно доказанный human workstation login до удаления fallback access.

**Docker.** Docker-published ports — отдельная exposure surface от UFW. Management interfaces не должны становиться public только потому, что container умеет их публиковать.

**Coolify.** Ports `8000/6001/6002` остаются private/loopback в core profile. Public traffic идёт через application edge. Предложенный ADR-0005 считает Sentinel частью этого high-trust control plane, потому что upstream container использует host PID namespace и read-write Docker socket; его API не должен публиковать host port.

**Observability.** Retained-log path использует restricted Docker API proxy через `/run/solo-vps-docker-api/docker-api.sock`. Proxy остаётся high-trust, потому что владеет реальным Docker daemon socket, а Alloy получает только narrowed Unix-socket interface. Host-local unprivileged identity не должна уметь пересечь эту границу. Профиль host metrics намеренно отделён: `solo-vps-metrics` читает только выбранные метрики Linux через Alloy Unix exporter, не имеет доступа к Docker, а HTTP-интерфейс Alloy слушает только loopback.

**Secrets.** Public source, examples и non-secret config не должны содержать private SSH keys, age identities, S3/restic credentials, API tokens или application secrets.

**Backup.** Установка restic не является recovery evidence. Recovery требует off-site storage, свежих snapshots, logical database backups там, где они нужны, и проверенной restore procedure.

## Текущая граница evidence

Solo VPS находится в статусе **PRE-ALPHA**. Архитектура описывает intended и source-supported responsibility model; её нельзя читать как production-readiness claim.

В частности, source validators и local checks слабее clean disposable VPS replay, реального off-site backup/restore, реального PostgreSQL restore или destroy-and-rebuild disaster-recovery exercise. Текущее evidence state находится в `ROADMAP.md`.

## Правило изменения архитектуры

Создавайте или обновляйте ADR, если изменение существенно влияет на ownership, core technology, supported platforms, security/trust boundaries, secrets, storage/database strategy, deployment strategy или migration burden.

Не создавайте ADR для маленьких обратимых implementation details.

Maintainer engineering rules находятся в `.agents/skills/solo-vps-project-engineer/SKILL.md`.
