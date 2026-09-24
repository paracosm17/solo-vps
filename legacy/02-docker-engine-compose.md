# Глава 2. Docker Engine и Docker Compose

> **Цель:** установить официальный Docker Engine и Compose plugin, ограничить рост логов, подготовить постоянные сети и безопасную структуру Docker Compose.

> **Результат:** Docker запускается после перезагрузки, новые неопределённые публикации портов по умолчанию привязаны к `127.0.0.1`, а сети `edge` и `observability` создаются идемпотентным скриптом.

---

## 1. Принятые правила

```text
/opt/ops       Compose, конфигурация, скрипты и документация — Git
/opt/apps      исходники и deploy-каталоги приложений
/opt/data      постоянные данные контейнеров — не Git
/opt/backups   локальный staging резервных копий — не Git
```

Основные ограничения:

- один логический стек хранится в одном каталоге с `compose.yaml`;
- секреты не записываются в Compose-файлы и Git;
- host IP указывается в `ports` явно;
- базы данных и Redis не подключаются к публичной сети `edge`;
- Docker socket не монтируется без отдельного анализа рисков;
- не используются буквальные каталоги с именами вроде `<STACK_NAME>` — имя стека задаётся конкретным значением или shell-переменной.

Конфигурация автоматически загружается из `/etc/vps-guide/config.env`. Служебные скрипты дополнительно загружают этот файл самостоятельно.

---

## 2. Установить Docker из официального репозитория

Удалить конфликтующие пакеты:

```bash
sudo apt remove -y \
  docker.io \
  docker-doc \
  docker-compose \
  docker-compose-v2 \
  podman-docker \
  containerd \
  runc
```

Установить зависимости и официальный signing key:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL \
  https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Добавить deb822 repository:

```bash
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF_DOCKER_REPO
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER_REPO

sudo apt update
```

Установить Engine и плагины:

```bash
sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

sudo systemctl enable --now docker.service containerd.service
```

---

## 3. Разрешить администратору управлять Docker

Группа `docker` предоставляет практически root-доступ. Добавляйте в неё только доверенного администратора:

```bash
sudo usermod -aG docker "$ADMIN_USER"
```

Завершите SSH-сеанс и подключитесь заново:

```bash
exit
```

На Windows:

```powershell
ssh $VpsConfig.SshAlias
```

После нового входа:

```bash
id -nG
docker version
docker compose version
```

---

## 4. Настроить Docker daemon

Создать конфигурацию внутри изолированного Bash-блока. Перед записью проверяются все значения, поэтому пустые переменные не попадут в `daemon.json`:

```bash
bash <<'BASH'
set -Eeuo pipefail

source /etc/vps-guide/config.env

: "${DOCKER_LOG_MAX_SIZE:?}"
: "${DOCKER_LOG_MAX_FILE:?}"
: "${DOCKER_DEFAULT_BIND_IP:?}"

[[ "$DOCKER_LOG_MAX_SIZE" =~ ^[1-9][0-9]*[kKmMgG]$ ]]
[[ "$DOCKER_LOG_MAX_FILE" =~ ^[1-9][0-9]*$ ]]

python3 - "$DOCKER_DEFAULT_BIND_IP" <<'PY'
import ipaddress
import sys
ip = ipaddress.ip_address(sys.argv[1])
if not ip.is_loopback:
    raise SystemExit(f"Docker bind IP must be loopback, got {ip}")
PY

sudo install -d -m 0755 /etc/docker

if sudo test -s /etc/docker/daemon.json; then
  sudo cp -a \
    /etc/docker/daemon.json \
    "/etc/docker/daemon.json.backup.$(date +%F-%H%M%S)"
fi

current="$(mktemp)"
new="$(mktemp)"
trap 'rm -f "$current" "$new"' EXIT

if sudo test -s /etc/docker/daemon.json; then
  sudo cat /etc/docker/daemon.json > "$current"
else
  printf '{}\n' > "$current"
fi

jq \
  --arg log_size "$DOCKER_LOG_MAX_SIZE" \
  --arg log_files "$DOCKER_LOG_MAX_FILE" \
  --arg bind_ip "$DOCKER_DEFAULT_BIND_IP" \
  '."log-driver" = "local"
   | ."log-opts" = {
       "max-size": $log_size,
       "max-file": $log_files
     }
   | ."live-restore" = true
   | ."default-network-opts".bridge[
       "com.docker.network.bridge.host_binding_ipv4"
     ] = $bind_ip' \
  "$current" > "$new"

jq -e \
  --arg log_size "$DOCKER_LOG_MAX_SIZE" \
  --arg log_files "$DOCKER_LOG_MAX_FILE" \
  --arg bind_ip "$DOCKER_DEFAULT_BIND_IP" \
  '."log-driver" == "local"
   and ."log-opts"["max-size"] == $log_size
   and ."log-opts"["max-file"] == $log_files
   and ."default-network-opts".bridge[
         "com.docker.network.bridge.host_binding_ipv4"
       ] == $bind_ip' \
  "$new" >/dev/null

sudo dockerd --validate --config-file="$new"
sudo install -o root -g root -m 0644 "$new" /etc/docker/daemon.json
sudo systemctl restart docker.service
BASH
```

`local` logging driver ограничивает рост container stdout/stderr. `live-restore` позволяет работающим контейнерам пережить часть перезапусков daemon. Значение `127.0.0.1` используется как защитный default для новых bridge-сетей, но production Compose всё равно указывает host IP явно.

---

## 5. Создать постоянные Docker-сети

Создать идемпотентный скрипт. Он безопасно запускается повторно и явно задаёт bind IP каждой сети:

```bash
cat > "$OPS_ROOT/scripts/docker-ensure-networks.sh" <<'EOF_NETWORKS'
#!/usr/bin/env bash
set -Eeuo pipefail

source /etc/vps-guide/config.env

: "${EDGE_NETWORK:?}"
: "${OBSERVABILITY_NETWORK:?}"
: "${DOCKER_DEFAULT_BIND_IP:?}"

ensure_network() {
  local network_name="$1"
  local scope_label="$2"

  if docker network inspect "$network_name" >/dev/null 2>&1; then
    local current_bind
    current_bind="$(
      docker network inspect "$network_name" \
        --format '{{index .Options "com.docker.network.bridge.host_binding_ipv4"}}'
    )"

    if [[ "$current_bind" != "$DOCKER_DEFAULT_BIND_IP" ]]; then
      printf 'Network %s has unexpected bind IP: %s\n' \
        "$network_name" "${current_bind:-<empty>}" >&2
      return 1
    fi

    printf 'Exists:  %s\n' "$network_name"
    return 0
  fi

  docker network create \
    --driver bridge \
    --opt "com.docker.network.bridge.host_binding_ipv4=$DOCKER_DEFAULT_BIND_IP" \
    --label 'ops.managed-by=manual' \
    --label 'ops.persistent=true' \
    --label "ops.scope=$scope_label" \
    "$network_name" >/dev/null

  printf 'Created: %s\n' "$network_name"
}

ensure_network "$EDGE_NETWORK" edge
ensure_network "$OBSERVABILITY_NETWORK" observability
EOF_NETWORKS

chmod 0750 "$OPS_ROOT/scripts/docker-ensure-networks.sh"
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

Не выполняйте `docker network prune` на production-сервере без ручной проверки: неиспользуемые external-сети считаются удаляемыми. При случайном удалении повторный запуск скрипта восстановит их.

---

## 6. Подготовить структуру Compose

```bash
install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT/compose/_templates/app" \
  "$OPS_ROOT/compose/_smoke" \
  "$OPS_ROOT/config/docker" \
  "$OPS_ROOT/scripts" \
  "$OPS_ROOT/docs"

sudo cp /etc/docker/daemon.json "$OPS_ROOT/config/docker/daemon.json"
sudo chown "$ADMIN_USER:$OPS_GROUP" "$OPS_ROOT/config/docker/daemon.json"
chmod 0664 "$OPS_ROOT/config/docker/daemon.json"
```

Создать базовый шаблон приложения:

```bash
cat > "$OPS_ROOT/compose/_templates/app/compose.yaml" <<'EOF_APP_TEMPLATE'
name: ${COMPOSE_PROJECT_NAME:?Set COMPOSE_PROJECT_NAME}

services:
  app:
    image: ${APP_IMAGE:?Set APP_IMAGE}
    restart: unless-stopped
    init: true
    stop_grace_period: 30s

    security_opt:
      - no-new-privileges=true

    pids_limit: ${APP_PIDS_LIMIT:-256}
    mem_limit: ${APP_MEMORY_LIMIT:-512m}
    cpus: ${APP_CPU_LIMIT:-0.50}

    networks:
      - internal

    labels:
      ops.managed-by: docker-compose
      ops.host-published: "false"

networks:
  internal:
    internal: true
EOF_APP_TEMPLATE

cat > "$OPS_ROOT/compose/_templates/app/.env.example" <<'EOF_APP_ENV'
COMPOSE_PROJECT_NAME=myapp
APP_IMAGE=ghcr.io/owner/myapp:1.0.0
APP_PIDS_LIMIT=256
APP_MEMORY_LIMIT=512m
APP_CPU_LIMIT=0.50
EOF_APP_ENV

chmod 0664 \
  "$OPS_ROOT/compose/_templates/app/compose.yaml" \
  "$OPS_ROOT/compose/_templates/app/.env.example"
```

Используется синтаксис `no-new-privileges=true`. Вариант с двоеточием (`no-new-privileges:true`) не применяется.

---

## 7. Основные Compose-конвенции

### Внутренний сервис без host port

```yaml
services:
  db:
    image: postgres:17.5
    networks:
      - internal
```

Другие контейнеры обращаются к нему по имени `db:5432`.

### Сервис только для VPS

```yaml
ports:
  - "127.0.0.1:18080:80"
```

### Публичный сервис

Публичные `80/443` в главе 4 публикует только Caddy:

```yaml
ports:
  - "0.0.0.0:80:80/tcp"
  - "0.0.0.0:443:443/tcp"
  - "0.0.0.0:443:443/udp"
```

Не используйте сокращённую запись без host IP:

```yaml
# Не использовать в production
ports:
  - "3000:3000"
```

### Persistent data и конфигурация

```yaml
volumes:
  - type: bind
    source: /opt/data/myapp/data
    target: /var/lib/myapp

  - type: bind
    source: /opt/ops/config/myapp/config.yaml
    target: /etc/myapp/config.yaml
    read_only: true
```

### Права для bind mount

UID/GID процесса внутри контейнера должен иметь нужный доступ к host-каталогу. Для read-only web-конфигурации обычно используются каталоги `0755` и файлы `0644`. Для приватных данных права назначаются под фактический UID/GID image.

---

## 8. Запустить smoke test

Создать тестовый стек. Порт явно привязан к loopback:

```bash
cat > "$OPS_ROOT/compose/_smoke/compose.yaml" <<'EOF_SMOKE'
name: ${COMPOSE_PROJECT_NAME:-docker-smoke}

services:
  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:${SMOKE_PORT:-18080}:80"
    security_opt:
      - no-new-privileges=true
    pids_limit: 128
    mem_limit: 128m
    cpus: "0.25"
    labels:
      ops.managed-by: docker-compose
      ops.purpose: smoke-test
EOF_SMOKE

cat > "$OPS_ROOT/compose/_smoke/.env" <<EOF_SMOKE_ENV
COMPOSE_PROJECT_NAME=${SMOKE_STACK}
SMOKE_PORT=${SMOKE_PORT}
EOF_SMOKE_ENV

chmod 0600 "$OPS_ROOT/compose/_smoke/.env"

cd "$OPS_ROOT/compose/_smoke"
docker compose config --quiet
docker compose pull
docker compose up -d --remove-orphans
```

Проверить ответ:

```bash
curl --fail --silent --show-error \
  "http://127.0.0.1:${SMOKE_PORT}" \
  | head
```

---

## 9. Git-фиксация

```bash
git -C "$OPS_ROOT" add \
  .gitignore \
  README.md \
  compose/_templates/app \
  compose/_smoke/compose.yaml \
  config/docker/daemon.json \
  scripts/docker-ensure-networks.sh

git -C "$OPS_ROOT" commit -m 'Install Docker and Compose conventions'
```

Файл `compose/_smoke/.env` игнорируется общим правилом `*.env`.

---

## 10. Финальная проверка

```bash
sudo systemctl is-active docker.service containerd.service
sudo systemctl --failed

docker info --format 'Logging={{.LoggingDriver}} LiveRestore={{.LiveRestoreEnabled}}'
docker network inspect "$EDGE_NETWORK" "$OBSERVABILITY_NETWORK" >/dev/null

docker compose -f "$OPS_ROOT/compose/_smoke/compose.yaml" \
  --env-file "$OPS_ROOT/compose/_smoke/.env" \
  ps

sudo ss -lntp | grep -E ":${SMOKE_PORT}\b"
```

Ожидается публикация только на `127.0.0.1`.

---

# Диагностика и типичные проблемы

## A. `invalid value for max-size: : invalid size: ''`

Причина — пустые `log-opts` в `/etc/docker/daemon.json`. Такое не произойдёт при выполнении основного блока, поскольку он загружает постоянную конфигурацию и проверяет значения перед записью.

Проверить:

```bash
sudo jq '."log-driver", ."log-opts"' /etc/docker/daemon.json
```

Исправить повторным выполнением раздела 4, затем пересоздать контейнер:

```bash
cd "$OPS_ROOT/compose/_smoke"
docker compose down --remove-orphans || true
docker compose up -d --force-recreate --remove-orphans
```

Настройки logging driver применяются только к новым контейнерам.

## B. `failed to parse ... host_binding_ipv4 value: (nil ip)`

```bash
sudo jq -er \
  '."default-network-opts".bridge["com.docker.network.bridge.host_binding_ipv4"]' \
  /etc/docker/daemon.json
```

Если значение отсутствует или пусто, повторно выполнить раздел 4, затем:

```bash
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

## C. Сети `edge` или `observability` отсутствуют

```bash
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
docker network ls --filter 'label=ops.persistent=true'
```

На production-сервере не включайте автоматический `docker network prune`.

## D. Существующая сеть имеет неправильный bind IP

Сначала убедиться, что сеть не используется:

```bash
docker network inspect "$EDGE_NETWORK" \
  | jq '.[0].Containers'
```

Если объект пустой, сеть можно пересоздать:

```bash
docker network rm "$EDGE_NETWORK"
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

Не удаляйте сеть с подключёнными production-контейнерами. Сначала остановите соответствующие Compose-стеки и запланируйте короткое окно обслуживания.

## E. Smoke-контейнер не запущен

Не передавайте пустой container ID в `docker inspect`:

```bash
cd "$OPS_ROOT/compose/_smoke"
container_id="$(docker compose ps -q web)"

if [[ -z "$container_id" ]]; then
  docker compose ps -a
  docker compose logs --tail=100
else
  docker inspect "$container_id" | jq '.[0] | {
    LogConfig: .HostConfig.LogConfig,
    Memory: .HostConfig.Memory,
    NanoCpus: .HostConfig.NanoCpus,
    PidsLimit: .HostConfig.PidsLimit,
    SecurityOpt: .HostConfig.SecurityOpt
  }'
fi
```

## F. `docker compose port` не показывает порт

Команда работает только для `ports`. Секция `expose` не публикует порт на host и предназначена для связи контейнеров по Docker-сети.

Проверить внутренний сервис следует из другого контейнера той же сети или через `docker compose exec`.

## G. Создан каталог с буквальным именем `<STACK_NAME>`

Проверить содержимое и удалить только после проверки:

```bash
find "$OPS_ROOT/compose/<STACK_NAME>" -maxdepth 3 -print 2>/dev/null || true
rm -rf -- "$OPS_ROOT/compose/<STACK_NAME>"
```

В основных командах этой редакции угловые placeholders не используются как пути.

## H. Docker-порт доступен несмотря на UFW

Docker управляет собственными NAT-правилами. Проверять необходимо фактические listeners и host bindings:

```bash
sudo ss -lntup
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Не полагайтесь только на `ufw status`.

## I. Права на `/var/run/docker.sock`

```bash
id -nG
stat -c '%A %U:%G %n' /var/run/docker.sock
```

Ожидается `root:docker` и доступ группы на чтение/запись. Не выполняйте `chmod 666 /var/run/docker.sock`.

## J. Мышь печатает escape-последовательности

Проблема относится к режиму мыши терминала или tmux, а не к Docker. Используйте `Shift` + выделение или команды восстановления из диагностики главы 1.

## K. Безопасная очистка

Перед удалением ресурсов всегда смотреть список:

```bash
docker system df
docker image ls
docker container ls -a
docker volume ls
docker network ls
```

Не запускайте `docker system prune --volumes` на production без отдельной проверки volumes и резервных копий.

---

## Официальная документация

- Install Docker Engine on Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Docker daemon configuration: https://docs.docker.com/reference/cli/dockerd/
- Local logging driver: https://docs.docker.com/engine/logging/drivers/local/
- Bridge networks: https://docs.docker.com/engine/network/drivers/bridge/
- Port publishing: https://docs.docker.com/engine/network/port-publishing/
- Compose specification: https://docs.docker.com/reference/compose-file/
