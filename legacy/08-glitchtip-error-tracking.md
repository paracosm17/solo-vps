# Глава 08. GlitchTip: self-hosted error tracking для production-приложений

Эта глава добавляет централизованный **application error tracking** поверх инфраструктуры, завершённой в главе 07.

После выполнения главы:

- GlitchTip принимает Sentry-compatible error events от приложений;
- GlitchTip работает в официально поддерживаемом single-node `all-in-one` режиме;
- PostgreSQL хранит события, пользователей, проекты и настройки;
- Valkey/Redis намеренно не используется — для небольшого VPS GlitchTip умеет использовать PostgreSQL для cache/task/session backend;
- открытая регистрация пользователей отключена до публикации сервиса;
- первый administrator создаётся автоматически до подключения публичного Caddy route;
- UI и ingest API доступны по `https://errors.<BASE_DOMAIN>`;
- GlitchTip container не публикует host port `8000`;
- PostgreSQL не публикует host port `5432`;
- Caddy остаётся единственной публичной точкой входа;
- GlitchTip подключён к существующей observability network;
- Prometheus получает `/metrics` GlitchTip;
- Blackbox Exporter проверяет публичный HTTPS endpoint GlitchTip;
- Alertmanager получает alerts при падении internal target или public endpoint;
- Docker logs GlitchTip/PostgreSQL автоматически попадают в Loki через уже настроенный Alloy;
- persistent data находятся в `/opt/data/error-tracking` и готовы к последующей backup-главе;
- Docker images фиксируются exact digest `@sha256:...`;
- secrets остаются вне Git;
- server-specific non-secret variables остаются в едином `$HOME/config.env`.

> Команды рассчитаны на Ubuntu 24.04 после успешно завершённой главы 07.
>
> В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, **не переходите к следующему номеру шага**, пока причина не устранена.
>
> Не публикуйте содержимое файлов из `$ERROR_TRACKING_SECRETS_ROOT` в issue, GitHub, chat или console log.

---

## 0. Что именно строим

```text
Production application / browser / mobile app
                |
                | Sentry-compatible SDK / HTTPS
                v
          errors.example.com
                |
                v
        Caddy :80 / :443
                |
                | Docker edge network
                v
        GlitchTip :8000
          all-in-one
       web + task worker
          /         \
         /           \
        v             v
 PostgreSQL       /code/uploads
  internal       persistent files
  network

GlitchTip :8000 ---- observability network ----> Prometheus
       |
       +------ Docker stdout/stderr -----------> Alloy -> Loki

Blackbox Exporter ---- HTTPS ----> errors.example.com
          |
          v
      Prometheus -> Alertmanager -> Telegram
```

Для VPS `2 vCPU / 4 GB RAM / ~60 GB disk` в этой главе используется минимальная production-схема:

- **1 GlitchTip container** в `all-in-one` режиме;
- **1 PostgreSQL container**;
- без отдельного Valkey/Redis;
- без отдельного GlitchTip worker container;
- без отдельного reverse proxy внутри stack;
- без host-published application/database ports.

Это соответствует текущей архитектуре GlitchTip для небольшого single-server deployment: PostgreSQL обязателен, а Valkey является optional; GlitchTip поддерживает single service/all-in-one режим.

В этой главе намеренно отключаем встроенные GlitchTip uptime checks и application log storage:

- uptime уже контролирует Prometheus + Blackbox Exporter;
- Docker/application runtime logs уже централизованы в Loki;
- GlitchTip используем прежде всего для exceptions, issues и low-sample performance events;
- это уменьшает расход PostgreSQL disk/RAM на небольшом VPS.

---

## 1. Проверить checkpoint главы 07

Загрузить единую конфигурацию:

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"
: "${SERVER_PUBLIC_IPV4:?SERVER_PUBLIC_IPV4 is not set}"
: "${EDGE_NETWORK:?EDGE_NETWORK is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"
: "${OBSERVABILITY_ROOT:?OBSERVABILITY_ROOT is not set}"
: "${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}"
: "${OBSERVABILITY_STACK:?OBSERVABILITY_STACK is not set}"
: "${PROMETHEUS_IMAGE:?PROMETHEUS_IMAGE is not set}"
: "${CADDY_STACK:?CADDY_STACK is not set}"
: "${DEPLOY_TEST_DOMAIN:?DEPLOY_TEST_DOMAIN is not set}"
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"
```

Проверить пользователя:

```bash
[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run this chapter as %s, not as %s\n' \
    "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}
```

Проверить Git working tree:

```bash
test -z "$(git -C "$OPS_ROOT" status --porcelain)" || {
  printf 'ERROR: %s has uncommitted changes\n' "$OPS_ROOT" >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

git -C "$OPS_ROOT" status --short
git -C "$OPS_ROOT" log -5 --oneline
```

Проверить local/remote main:

```bash
git -C "$OPS_ROOT" fetch --quiet origin main

LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"

[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ\n' >&2
  printf 'local:  %s\nremote: %s\n' \
    "$LOCAL_SHA" "$REMOTE_SHA" >&2
  exit 1
}

printf 'Git main is synchronized: %s\n' "$LOCAL_SHA"
```

Проверить Docker networks:

```bash
for network in \
  "$EDGE_NETWORK" \
  "$OBSERVABILITY_NETWORK"; do

  docker network inspect "$network" >/dev/null || {
    printf 'ERROR: Docker network does not exist: %s\n' \
      "$network" >&2
    exit 1
  }
done

printf 'Required Docker networks exist.\n'
```

Проверить observability stack:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
```

Последняя строка должна быть:

```text
Observability check passed.
```

Проверить, что ни один observability container не находится в restart loop:

```bash
BAD_CONTAINERS="$(
  docker ps -a \
    --filter "label=com.docker.compose.project=$OBSERVABILITY_STACK" \
    --format '{{.Names}} {{.Status}}' |
  grep -E 'Restarting|Exited|Dead' || true
)"

[[ -z "$BAD_CONTAINERS" ]] || {
  printf 'ERROR: observability has unhealthy container state:\n%s\n' \
    "$BAD_CONTAINERS" >&2
  exit 1
}

printf 'Observability containers are stable.\n'
```

Проверить Docker -> Alloy -> Loki pipeline на уже существующем stack:

```bash
NOW_NS="$(date +%s%N)"
START_NS="$(( NOW_NS - 3600000000000 ))"

LOG_COUNT="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode \
      "query={source=\"docker\",compose_project=\"${OBSERVABILITY_STACK}\"}" \
    --data-urlencode "start=$START_NS" \
    --data-urlencode "end=$NOW_NS" \
    --data-urlencode 'limit=1' \
    --data-urlencode 'direction=backward' \
    http://127.0.0.1:3100/loki/api/v1/query_range |
  jq '[.data.result[].values[]] | length'
)"

(( LOG_COUNT > 0 )) || {
  printf 'ERROR: Docker -> Alloy -> Loki pipeline is not producing logs\n' >&2
  exit 1
}

printf 'Docker -> Alloy -> Loki checkpoint passed.\n'
```

Проверить Caddy:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose ps

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Проверить host resources:

```bash
sudo systemctl --failed

df -h /
free -h
```

Перед установкой GlitchTip желательно иметь минимум `8 GiB` свободного места:

```bash
FREE_GIB="$(df -BG --output=avail / | tail -n 1 | tr -dc '0-9')"

(( FREE_GIB >= 8 )) || {
  printf 'ERROR: less than 8 GiB free on /: %s GiB\n' \
    "$FREE_GIB" >&2
  exit 1
}

printf 'Free disk: %s GiB\n' "$FREE_GIB"
```

Не продолжать, пока весь checkpoint не проходит.

---

## 2. Зафиксировать GlitchTip defaults и exact image digests

На момент подготовки главы используется:

- GlitchTip `6.2.2`;
- PostgreSQL `17.10-alpine`;
- GlitchTip `all-in-one`;
- PostgreSQL-only cache/task/session backend;
- application event retention `30d`;
- transaction retention `14d`;
- file retention `30d`.

Теги используются только как **контролируемая точка разрешения версии**. Сам Compose будет использовать exact image digest.

Создать versioned configure script:

````bash
cat > "$OPS_ROOT/scripts/chapter-08-configure.sh" <<'EOF_CH08_CONFIG'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"
: "${SERVER_PUBLIC_IPV4:?SERVER_PUBLIC_IPV4 is not set}"
: "${EDGE_NETWORK:?EDGE_NETWORK is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in \
  docker \
  getent \
  jq \
  openssl \
  python3; do

  command -v "$command" >/dev/null || {
    printf 'ERROR: required command not found: %s\n' \
      "$command" >&2
    exit 1
  }
done

docker network inspect "$EDGE_NETWORK" >/dev/null
docker network inspect "$OBSERVABILITY_NETWORK" >/dev/null

EDGE_SUBNET="$(
  docker network inspect "$EDGE_NETWORK" \
    --format '{{(index .IPAM.Config 0).Subnet}}'
)"

[[ "$EDGE_SUBNET" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] || {
  printf 'ERROR: unexpected edge subnet: %s\n' \
    "$EDGE_SUBNET" >&2
  exit 1
}

ERROR_TRACKING_STACK="error-tracking"
ERROR_TRACKING_ROOT="$OPS_ROOT/compose/$ERROR_TRACKING_STACK"
ERROR_TRACKING_CONFIG_ROOT="$OPS_ROOT/config/$ERROR_TRACKING_STACK"
ERROR_TRACKING_DATA_ROOT="$DATA_ROOT/$ERROR_TRACKING_STACK"
ERROR_TRACKING_SECRETS_ROOT="$ERROR_TRACKING_DATA_ROOT/secrets"

GLITCHTIP_HOST="errors.${BASE_DOMAIN}"
GLITCHTIP_URL="https://${GLITCHTIP_HOST}"
GLITCHTIP_UPSTREAM="glitchtip:8000"
GLITCHTIP_ADMIN_EMAIL="${ADMIN_USER}@${BASE_DOMAIN}"

GLITCHTIP_RETENTION_DAYS="30"
GLITCHTIP_TRANSACTION_RETENTION_DAYS="14"
GLITCHTIP_FILE_RETENTION_DAYS="30"
GLITCHTIP_RELEASE_RETENTION_DAYS="180"

GLITCHTIP_TAG="glitchtip/glitchtip:6.2.2"
GLITCHTIP_POSTGRES_TAG="postgres:17.10-alpine"

resolve_image() {
  local tag="$1"
  local image_ref

  printf 'Pulling %s\n' "$tag" >&2
  docker pull "$tag" >/dev/null

  image_ref="$(
    docker image inspect "$tag" \
      --format '{{index .RepoDigests 0}}'
  )"

  [[ "$image_ref" =~ ^[^[:space:]]+@sha256:[a-f0-9]{64}$ ]] || {
    printf 'ERROR: exact digest was not resolved for %s\n' \
      "$tag" >&2
    printf 'Resolved value: %s\n' "$image_ref" >&2
    exit 1
  }

  printf '%s\n' "$image_ref"
}

GLITCHTIP_IMAGE="$(resolve_image "$GLITCHTIP_TAG")"
GLITCHTIP_POSTGRES_IMAGE="$(resolve_image "$GLITCHTIP_POSTGRES_TAG")"

GLITCHTIP_UID="$(
  docker run \
    --rm \
    --entrypoint sh \
    "$GLITCHTIP_IMAGE" \
    -c 'id -u'
)"

GLITCHTIP_GID="$(
  docker run \
    --rm \
    --entrypoint sh \
    "$GLITCHTIP_IMAGE" \
    -c 'id -g'
)"

POSTGRES_UID="$(
  docker run \
    --rm \
    --entrypoint sh \
    "$GLITCHTIP_POSTGRES_IMAGE" \
    -c 'id -u postgres'
)"

POSTGRES_GID="$(
  docker run \
    --rm \
    --entrypoint sh \
    "$GLITCHTIP_POSTGRES_IMAGE" \
    -c 'id -g postgres'
)"

for value in \
  "$GLITCHTIP_UID" \
  "$GLITCHTIP_GID" \
  "$POSTGRES_UID" \
  "$POSTGRES_GID"; do

  [[ "$value" =~ ^[0-9]+$ ]] || {
    printf 'ERROR: unexpected container UID/GID: %s\n' \
      "$value" >&2
    exit 1
  }
done

docker run \
  --rm \
  --entrypoint sh \
  "$GLITCHTIP_IMAGE" \
  -eu -c '
    test -x /code/bin/start.sh
    test -f /code/manage.py
    test -d /code/uploads
    test -w /code/uploads
  '

python3 - \
  "$VPS_GUIDE_CONFIG" \
  "$SERVER_PUBLIC_IPV4" \
  "$EDGE_SUBNET" \
  "$ERROR_TRACKING_STACK" \
  "$ERROR_TRACKING_ROOT" \
  "$ERROR_TRACKING_CONFIG_ROOT" \
  "$ERROR_TRACKING_DATA_ROOT" \
  "$ERROR_TRACKING_SECRETS_ROOT" \
  "$GLITCHTIP_HOST" \
  "$GLITCHTIP_URL" \
  "$GLITCHTIP_UPSTREAM" \
  "$GLITCHTIP_ADMIN_EMAIL" \
  "$GLITCHTIP_RETENTION_DAYS" \
  "$GLITCHTIP_TRANSACTION_RETENTION_DAYS" \
  "$GLITCHTIP_FILE_RETENTION_DAYS" \
  "$GLITCHTIP_RELEASE_RETENTION_DAYS" \
  "$GLITCHTIP_TAG" \
  "$GLITCHTIP_POSTGRES_TAG" \
  "$GLITCHTIP_IMAGE" \
  "$GLITCHTIP_POSTGRES_IMAGE" \
  "$GLITCHTIP_UID" \
  "$GLITCHTIP_GID" \
  "$POSTGRES_UID" \
  "$POSTGRES_GID" <<'PY_CONFIG_ENV'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
keys = [
    "SERVER_PUBLIC_IPV4",
    "EDGE_SUBNET",
    "ERROR_TRACKING_STACK",
    "ERROR_TRACKING_ROOT",
    "ERROR_TRACKING_CONFIG_ROOT",
    "ERROR_TRACKING_DATA_ROOT",
    "ERROR_TRACKING_SECRETS_ROOT",
    "GLITCHTIP_HOST",
    "GLITCHTIP_URL",
    "GLITCHTIP_UPSTREAM",
    "GLITCHTIP_ADMIN_EMAIL",
    "GLITCHTIP_RETENTION_DAYS",
    "GLITCHTIP_TRANSACTION_RETENTION_DAYS",
    "GLITCHTIP_FILE_RETENTION_DAYS",
    "GLITCHTIP_RELEASE_RETENTION_DAYS",
    "GLITCHTIP_TAG",
    "GLITCHTIP_POSTGRES_TAG",
    "GLITCHTIP_IMAGE",
    "GLITCHTIP_POSTGRES_IMAGE",
    "GLITCHTIP_UID",
    "GLITCHTIP_GID",
    "POSTGRES_UID",
    "POSTGRES_GID",
]

values = dict(zip(keys, sys.argv[2:], strict=True))

text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
key_pattern = re.compile(
    r"^\s*export\s+(" + "|".join(map(re.escape, keys)) + r")="
)

seen = set()
out = []

for line in lines:
    match = key_pattern.match(line)
    if not match:
        out.append(line)
        continue

    key = match.group(1)
    if key in seen:
        continue

    out.append(f"export {key}={shlex.quote(values[key])}")
    seen.add(key)

missing = [key for key in keys if key not in seen]

if missing:
    if out and out[-1].strip():
        out.append("")

    out.extend([
        "# =============================================================================",
        "# ERROR TRACKING — GlitchTip",
        "# =============================================================================",
    ])

    for key in missing:
        out.append(f"export {key}={shlex.quote(values[key])}")

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY_CONFIG_ENV

chmod 0600 "$VPS_GUIDE_CONFIG"
bash -n "$VPS_GUIDE_CONFIG"

printf '\nGlitchTip configuration saved to %s\n' \
  "$VPS_GUIDE_CONFIG"
printf 'GlitchTip URL: %s\n' "$GLITCHTIP_URL"
printf 'Edge subnet:   %s\n' "$EDGE_SUBNET"
printf 'GlitchTip UID:GID: %s:%s\n' \
  "$GLITCHTIP_UID" "$GLITCHTIP_GID"
printf 'Postgres UID:GID: %s:%s\n' \
  "$POSTGRES_UID" "$POSTGRES_GID"
EOF_CH08_CONFIG

chmod 0750 "$OPS_ROOT/scripts/chapter-08-configure.sh"
````

Проверить script:

```bash
bash -n "$OPS_ROOT/scripts/chapter-08-configure.sh"
shellcheck -x "$OPS_ROOT/scripts/chapter-08-configure.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/chapter-08-configure.sh"
```

Заново загрузить config:

```bash
source "$HOME/config.env"
```

Проверить значения:

```bash
printf '%s\n' \
  "ERROR_TRACKING_ROOT=$ERROR_TRACKING_ROOT" \
  "ERROR_TRACKING_DATA_ROOT=$ERROR_TRACKING_DATA_ROOT" \
  "GLITCHTIP_URL=$GLITCHTIP_URL" \
  "GLITCHTIP_ADMIN_EMAIL=$GLITCHTIP_ADMIN_EMAIL" \
  "GLITCHTIP_UID=$GLITCHTIP_UID" \
  "GLITCHTIP_GID=$GLITCHTIP_GID" \
  "POSTGRES_UID=$POSTGRES_UID" \
  "POSTGRES_GID=$POSTGRES_GID"
```

Проверить exact image refs:

```bash
for variable in \
  GLITCHTIP_IMAGE \
  GLITCHTIP_POSTGRES_IMAGE; do

  value="$(printenv "$variable")"

  [[ "$value" =~ '@sha256:'[a-f0-9]{64}'$' ]] || {
    printf 'ERROR: %s is not digest-pinned: %s\n' \
      "$variable" "$value" >&2
    exit 1
  }
done

printf 'GlitchTip images are digest-pinned.\n'
```

---

## 3. Создать persistent directories с правильными UID/GID

Persistent GlitchTip data не хранятся в `/opt/ops`.

Используем:

```text
/opt/data/error-tracking/
├── postgres/      PostgreSQL data directory
├── uploads/       sourcemaps / debug files / uploaded files
└── secrets/       database/app/bootstrap credentials
```

Создать root directories:

```bash
source "$HOME/config.env"

sudo install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0750 \
  "$ERROR_TRACKING_DATA_ROOT" \
  "$ERROR_TRACKING_SECRETS_ROOT"

sudo install -d \
  -o "$POSTGRES_UID" \
  -g "$POSTGRES_GID" \
  -m 0700 \
  "$ERROR_TRACKING_DATA_ROOT/postgres"

sudo install -d \
  -o "$GLITCHTIP_UID" \
  -g "$GLITCHTIP_GID" \
  -m 0750 \
  "$ERROR_TRACKING_DATA_ROOT/uploads"
```

Если каталоги уже существовали после неудачной попытки, привести ownership рекурсивно:

```bash
sudo chown -R \
  "$POSTGRES_UID:$POSTGRES_GID" \
  "$ERROR_TRACKING_DATA_ROOT/postgres"

sudo chmod 0700 \
  "$ERROR_TRACKING_DATA_ROOT/postgres"

sudo chown -R \
  "$GLITCHTIP_UID:$GLITCHTIP_GID" \
  "$ERROR_TRACKING_DATA_ROOT/uploads"

sudo find "$ERROR_TRACKING_DATA_ROOT/uploads" \
  -type d -exec chmod 0750 {} +
```

Создать versioned directories:

```bash
install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2775 \
  "$ERROR_TRACKING_ROOT" \
  "$ERROR_TRACKING_CONFIG_ROOT"
```

Проверить ownership без попытки интерпретировать имена numeric container users:

```bash
sudo stat \
  -c '%a %u:%g %n' \
  "$ERROR_TRACKING_DATA_ROOT" \
  "$ERROR_TRACKING_DATA_ROOT/postgres" \
  "$ERROR_TRACKING_DATA_ROOT/uploads" \
  "$ERROR_TRACKING_SECRETS_ROOT"
```

Автоматическая проверка:

```bash
[[ "$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/postgres")" == "$POSTGRES_UID" ]] || {
  printf 'ERROR: wrong PostgreSQL data owner\n' >&2
  exit 1
}

[[ "$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/uploads")" == "$GLITCHTIP_UID" ]] || {
  printf 'ERROR: wrong GlitchTip uploads owner\n' >&2
  exit 1
}

printf 'Persistent directory ownership is correct.\n'
```

---

## 4. Сгенерировать GlitchTip/PostgreSQL secrets

Создать helper. Он **не перегенерирует** существующие credentials при повторном запуске.

````bash
cat > "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" <<'EOF_GLITCHTIP_SECRETS'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

command -v openssl >/dev/null
command -v python3 >/dev/null

install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0750 \
  "$ERROR_TRACKING_SECRETS_ROOT"

ensure_secret() {
  local path="$1"
  local kind="$2"

  if [[ -s "$path" ]]; then
    return
  fi

  umask 077

  case "$kind" in
    hex64)
      openssl rand -hex 64 > "$path"
      ;;
    hex32)
      openssl rand -hex 32 > "$path"
      ;;
    password)
      openssl rand -base64 48 |
        tr -d '\r\n' |
        tr '/+' '_-' > "$path"
      printf '\n' >> "$path"
      ;;
    *)
      printf 'ERROR: unknown secret type: %s\n' "$kind" >&2
      exit 1
      ;;
  esac
}

ensure_secret \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  hex64

ensure_secret \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  hex32

ensure_secret \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  password

for file in \
  secret_key \
  postgres_password \
  admin_password; do

  chown "$ADMIN_USER:$OPS_GROUP" \
    "$ERROR_TRACKING_SECRETS_ROOT/$file"

  chmod 0640 \
    "$ERROR_TRACKING_SECRETS_ROOT/$file"
done

SECRET_KEY="$(<"$ERROR_TRACKING_SECRETS_ROOT/secret_key")"
POSTGRES_PASSWORD="$(<"$ERROR_TRACKING_SECRETS_ROOT/postgres_password")"

[[ "$SECRET_KEY" =~ ^[a-f0-9]{128}$ ]] || {
  printf 'ERROR: invalid GlitchTip SECRET_KEY format\n' >&2
  exit 1
}

[[ "$POSTGRES_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || {
  printf 'ERROR: invalid PostgreSQL password format\n' >&2
  exit 1
}

umask 077

cat > "$ERROR_TRACKING_SECRETS_ROOT/postgres.env" <<EOF_POSTGRES_ENV
POSTGRES_DB=glitchtip
POSTGRES_USER=glitchtip
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
PGDATA=/var/lib/postgresql/data/pgdata
EOF_POSTGRES_ENV

cat > "$ERROR_TRACKING_SECRETS_ROOT/glitchtip.env" <<EOF_GLITCHTIP_ENV
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgresql://glitchtip:${POSTGRES_PASSWORD}@postgres:5432/glitchtip
EOF_GLITCHTIP_ENV

chown "$ADMIN_USER:$OPS_GROUP" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres.env" \
  "$ERROR_TRACKING_SECRETS_ROOT/glitchtip.env"

chmod 0640 \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres.env" \
  "$ERROR_TRACKING_SECRETS_ROOT/glitchtip.env"

unset SECRET_KEY POSTGRES_PASSWORD

printf 'GlitchTip secret files are ready.\n'
printf 'Secret values were not printed.\n'
EOF_GLITCHTIP_SECRETS

chmod 0750 "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh"
````

Проверить:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh"
```

Проверить только metadata, **не выводить содержимое**:

```bash
find "$ERROR_TRACKING_SECRETS_ROOT" \
  -maxdepth 1 \
  -type f \
  -printf '%m %u:%g %f\n' |
  sort
```

Проверить, что ожидаемые файлы существуют и непустые:

```bash
for file in \
  secret_key \
  postgres_password \
  admin_password \
  postgres.env \
  glitchtip.env; do

  [[ -s "$ERROR_TRACKING_SECRETS_ROOT/$file" ]] || {
    printf 'ERROR: secret file is empty or missing: %s\n' \
      "$file" >&2
    exit 1
  }
done

printf 'All required GlitchTip secret files exist.\n'
```

Проверить, что secrets находятся вне Git repository:

```bash
case "$ERROR_TRACKING_SECRETS_ROOT" in
  "$OPS_ROOT"/*)
    printf 'ERROR: secrets directory is inside Git repository\n' >&2
    exit 1
    ;;
  *)
    printf 'Secrets directory is outside Git repository.\n'
    ;;
esac
```

---

## 5. Создать production Compose stack

GlitchTip environment intentionally содержит:

- `ENABLE_USER_REGISTRATION=False`;
- `ENABLE_SOCIAL_APPS_USER_REGISTRATION=False`;
- `ENABLE_ORGANIZATION_CREATION=False`;
- `SERVER_ROLE=all_in_one` and `GLITCHTIP_EMBED_WORKER=true`;
- пустой `VALKEY_URL`;
- `ENABLE_OBSERVABILITY_API=True`;
- restricted `ALLOWED_HOSTS` for the public hostname plus the internal Docker alias used by Prometheus;
- explicit `CSRF_TRUSTED_ORIGINS`;
- HSTS внутри Django;
- ограниченную concurrency для VPS 4 GB.

GlitchTip logs и uptime monitoring здесь отключены, потому что эти задачи уже выполняются Loki и Blackbox Exporter. DuckDB cold storage также явно отключён: на этом VPS оставляем один предсказуемый hot-storage слой в PostgreSQL, а резервное копирование будет вынесено в отдельную главу.

Создать Compose:

````bash
cat > "$ERROR_TRACKING_ROOT/compose.yaml" <<'EOF_GLITCHTIP_COMPOSE'
services:
  postgres:
    image: ${GLITCHTIP_POSTGRES_IMAGE:?GLITCHTIP_POSTGRES_IMAGE is not set}
    restart: unless-stopped

    env_file:
      - ${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}/postgres.env

    command:
      - postgres
      - -c
      - shared_buffers=128MB
      - -c
      - effective_cache_size=512MB
      - -c
      - maintenance_work_mem=64MB
      - -c
      - work_mem=4MB
      - -c
      - max_connections=60

    volumes:
      - ${ERROR_TRACKING_DATA_ROOT:?ERROR_TRACKING_DATA_ROOT is not set}/postgres:/var/lib/postgresql/data

    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U glitchtip -d glitchtip -h 127.0.0.1
      interval: 5s
      timeout: 3s
      retries: 20
      start_period: 10s

    shm_size: 128m
    pids_limit: 256
    mem_limit: 640m
    cpus: "0.50"

    labels:
      ops.managed-by: docker-compose
      ops.role: error-tracking-database
      ops.host-published: "false"

    networks:
      - internal

  glitchtip:
    image: ${GLITCHTIP_IMAGE:?GLITCHTIP_IMAGE is not set}
    restart: unless-stopped

    env_file:
      - ${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}/glitchtip.env

    environment:
      GLITCHTIP_DOMAIN: ${GLITCHTIP_URL:?GLITCHTIP_URL is not set}
      GLITCHTIP_INSTANCE_NAME: ${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set} GlitchTip

      ALLOWED_HOSTS: ${GLITCHTIP_HOST:?GLITCHTIP_HOST is not set},glitchtip
      CSRF_TRUSTED_ORIGINS: ${GLITCHTIP_URL:?GLITCHTIP_URL is not set}
      PROXY_ENV: "False"

      ENABLE_USER_REGISTRATION: "False"
      ENABLE_SOCIAL_APPS_USER_REGISTRATION: "False"
      ENABLE_ORGANIZATION_CREATION: "False"

      SERVER_ROLE: all_in_one
      GLITCHTIP_EMBED_WORKER: "true"
      VALKEY_URL: ""

      GLITCHTIP_ENABLE_UPTIME: "False"
      GLITCHTIP_ENABLE_LOGS: "False"
      GLITCHTIP_ENABLE_MCP: "False"
      GLITCHTIP_ENABLE_DUCKDB: "False"

      ENABLE_OBSERVABILITY_API: "True"
      LOG_LEVEL: WARNING

      GLITCHTIP_RETENTION_DAYS: ${GLITCHTIP_RETENTION_DAYS:?GLITCHTIP_RETENTION_DAYS is not set}
      GLITCHTIP_EVENT_RETENTION_DAYS: ${GLITCHTIP_RETENTION_DAYS:?GLITCHTIP_RETENTION_DAYS is not set}
      GLITCHTIP_TRANSACTION_RETENTION_DAYS: ${GLITCHTIP_TRANSACTION_RETENTION_DAYS:?GLITCHTIP_TRANSACTION_RETENTION_DAYS is not set}
      GLITCHTIP_FILE_RETENTION_DAYS: ${GLITCHTIP_FILE_RETENTION_DAYS:?GLITCHTIP_FILE_RETENTION_DAYS is not set}
      GLITCHTIP_RELEASE_RETENTION_DAYS: ${GLITCHTIP_RELEASE_RETENTION_DAYS:?GLITCHTIP_RELEASE_RETENTION_DAYS is not set}

      DATABASE_POOL_MAX_SIZE: "8"
      VTASKS_CONCURRENCY: "4"
      GRANIAN_WORKERS: "1"

      SECURE_HSTS_SECONDS: "31536000"
      SECURE_HSTS_INCLUDE_SUBDOMAINS: "False"
      SECURE_HSTS_PRELOAD: "False"

    depends_on:
      postgres:
        condition: service_healthy

    volumes:
      - ${ERROR_TRACKING_DATA_ROOT:?ERROR_TRACKING_DATA_ROOT is not set}/uploads:/code/uploads

    expose:
      - "8000"

    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import socket;
          s=socket.create_connection(('127.0.0.1', 8000), timeout=3);
          s.close()
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 60s

    security_opt:
      - no-new-privileges:true

    cap_drop:
      - ALL

    tmpfs:
      - /tmp:size=128m,mode=1777

    pids_limit: 384
    mem_limit: 1024m
    cpus: "0.75"

    labels:
      ops.managed-by: docker-compose
      ops.role: error-tracking
      ops.host-published: "false"

    networks:
      internal:
      edge:
        aliases:
          - glitchtip
      observability:
        aliases:
          - glitchtip

networks:
  internal:
    internal: true

  edge:
    external: true
    name: ${EDGE_NETWORK:?EDGE_NETWORK is not set}

  observability:
    external: true
    name: ${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}
EOF_GLITCHTIP_COMPOSE
````

Права:

```bash
chmod 0644 "$ERROR_TRACKING_ROOT/compose.yaml"
```

Проверить, что Compose не содержит host `ports:`:

```bash
if grep -nE '^[[:space:]]+ports:' \
    "$ERROR_TRACKING_ROOT/compose.yaml"; then
  printf 'ERROR: error-tracking Compose unexpectedly publishes host ports\n' >&2
  exit 1
fi

printf 'GlitchTip Compose has no host-published ports.\n'
```

---

## 6. Создать Compose wrapper

````bash
cat > "$OPS_ROOT/scripts/glitchtip-compose.sh" <<'EOF_GLITCHTIP_COMPOSE_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${ERROR_TRACKING_ROOT:?ERROR_TRACKING_ROOT is not set}"
: "${ERROR_TRACKING_STACK:?ERROR_TRACKING_STACK is not set}"

exec docker compose \
  --project-name "$ERROR_TRACKING_STACK" \
  --project-directory "$ERROR_TRACKING_ROOT" \
  --file "$ERROR_TRACKING_ROOT/compose.yaml" \
  "$@"
EOF_GLITCHTIP_COMPOSE_WRAPPER

chmod 0750 "$OPS_ROOT/scripts/glitchtip-compose.sh"
````

Проверить:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-compose.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-compose.sh"
```

Пока stack ещё не запущен, проверить Compose schema без вывода expanded secrets:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" config --quiet
```

Проверить resolved images без вывода environment:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" config --images
```

Оба image ref должны содержать `@sha256:`.


---

## 7. Выполнить static validation до первого запуска

Проверить Bash scripts главы:

```bash
bash -n \
  "$OPS_ROOT/scripts/chapter-08-configure.sh" \
  "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-compose.sh"

shellcheck -x \
  "$OPS_ROOT/scripts/chapter-08-configure.sh" \
  "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-compose.sh"
```

Проверить Compose:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" config --quiet
```

Проверить, что все Compose images immutable:

```bash
BAD_IMAGES="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    config --images |
  grep -vE '@sha256:[a-f0-9]{64}$' || true
)"

[[ -z "$BAD_IMAGES" ]] || {
  printf 'ERROR: mutable image reference remains:\n%s\n' \
    "$BAD_IMAGES" >&2
  exit 1
}

printf 'All GlitchTip Compose images are immutable.\n'
```

Проверить required external networks через resolved Compose config:

```bash
for network in \
  "$EDGE_NETWORK" \
  "$OBSERVABILITY_NETWORK"; do

  docker network inspect "$network" >/dev/null || {
    printf 'ERROR: missing external Docker network: %s\n' \
      "$network" >&2
    exit 1
  }
done

printf 'External Docker networks are ready.\n'
```

Проверить secrets permissions:

```bash
BAD_SECRET_MODE="$(
  find "$ERROR_TRACKING_SECRETS_ROOT" \
    -maxdepth 1 \
    -type f \
    ! -perm 0640 \
    -printf '%m %p\n'
)"

[[ -z "$BAD_SECRET_MODE" ]] || {
  printf 'ERROR: unexpected GlitchTip secret permissions:\n%s\n' \
    "$BAD_SECRET_MODE" >&2
  exit 1
}

printf 'GlitchTip secret permissions are correct.\n'
```

Проверить, что secret values случайно не были записаны в Compose:

```bash
if grep -nE \
    '(SECRET_KEY=|POSTGRES_PASSWORD=|postgresql://glitchtip:[^$])' \
    "$ERROR_TRACKING_ROOT/compose.yaml"; then
  printf 'ERROR: plaintext secret found in versioned Compose\n' >&2
  exit 1
fi

printf 'No plaintext GlitchTip credentials found in Compose.\n'
```

Проверить, что repository не содержит GlitchTip secret files:

```bash
if git -C "$OPS_ROOT" ls-files |
  grep -E \
    '(^|/)(admin_password|postgres_password|prometheus_token|secret_key|postgres\.env|glitchtip\.env)$'; then
  printf 'ERROR: GlitchTip credential file is tracked by Git\n' >&2
  exit 1
fi

printf 'No GlitchTip credential file is tracked.\n'
```

---

## 8. Запустить GlitchTip и PostgreSQL без публичного route

На этом этапе DNS/Caddy ещё не нужны. Сначала поднимаем stack и создаём administrator.

Сначала скачать images и поднять только PostgreSQL:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" pull

"$OPS_ROOT/scripts/glitchtip-compose.sh" up -d postgres
```

Дождаться PostgreSQL readiness. Проверка выполняется в subshell, поэтому ошибка не закрывает текущую SSH-сессию:

```bash
(
  set -Eeuo pipefail

  for attempt in $(seq 1 24); do
    POSTGRES_ID="$(
      "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q postgres
    )"

    postgres_status=""

    if [[ -n "$POSTGRES_ID" ]]; then
      postgres_status="$(
        docker inspect \
          --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
          "$POSTGRES_ID"
      )"
    fi

    if [[ "$postgres_status" == "healthy" ]]; then
      printf 'PostgreSQL is healthy.\n'
      exit 0
    fi

    if (( attempt == 24 )); then
      printf 'ERROR: PostgreSQL did not become healthy.\n' >&2
      "$OPS_ROOT/scripts/glitchtip-compose.sh" ps postgres >&2
      "$OPS_ROOT/scripts/glitchtip-compose.sh" \
        logs --tail=120 postgres >&2
      exit 1
    fi

    sleep 5
  done
)
```

До запуска web/worker **явно применить Django migrations**. Это idempotent command: на уже инициализированной базе он ничего не изменит:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  run \
  --rm \
  --no-deps \
  glitchtip \
  python /code/manage.py migrate --noinput
```

GlitchTip без Valkey использует Django `DatabaseCache`. Таблица cache не создаётся обычными migrations, поэтому отдельно создать её штатной idempotent-командой Django:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  run \
  --rm \
  --no-deps \
  glitchtip \
  python /code/manage.py createcachetable
```

Не полагаться только на `migrate --check`: отдельно доказать, что основная таблица GlitchTip и database-cache table действительно созданы:

```bash
USERS_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.users_user')::text, '');"
)"

CACHE_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.django_cache')::text, '');"
)"

[[ "$USERS_TABLE" == "users_user" ]] || {
  printf 'ERROR: GlitchTip database schema was not initialized.\n' >&2
  exit 1
}

[[ "$CACHE_TABLE" == "django_cache" ]] || {
  printf 'ERROR: Django database cache table was not initialized.\n' >&2
  exit 1
}

printf 'GlitchTip database schema and cache table are initialized.\n'
```

Теперь запустить основной GlitchTip service:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" up -d glitchtip
```

Следить только за состоянием, не за бесконечным log stream:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" ps
```

Дождаться health обоих services. Проверка выполняется в subshell, поэтому диагностическая ошибка не закрывает текущую SSH-сессию:

```bash
(
  set -Eeuo pipefail

  for attempt in $(seq 1 36); do
    POSTGRES_ID="$(
      "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q postgres
    )"
    GLITCHTIP_ID="$(
      "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q glitchtip
    )"

    postgres_status=""
    glitchtip_status=""

    if [[ -n "$POSTGRES_ID" ]]; then
      postgres_status="$(
        docker inspect \
          --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
          "$POSTGRES_ID"
      )"
    fi

    if [[ -n "$GLITCHTIP_ID" ]]; then
      glitchtip_status="$(
        docker inspect \
          --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
          "$GLITCHTIP_ID"
      )"
    fi

    if [[ "$postgres_status" == "healthy" ]] && \
       [[ "$glitchtip_status" == "healthy" ]]; then
      printf 'GlitchTip and PostgreSQL are healthy.\n'
      exit 0
    fi

    if (( attempt == 36 )); then
      printf 'ERROR: GlitchTip stack did not become healthy\n' >&2
      printf 'postgres=%s glitchtip=%s\n' \
        "$postgres_status" "$glitchtip_status" >&2
      "$OPS_ROOT/scripts/glitchtip-compose.sh" ps >&2
      "$OPS_ROOT/scripts/glitchtip-compose.sh" \
        logs --tail=200 postgres glitchtip >&2
      exit 1
    fi

    sleep 5
  done
)
```

Проверить стабильность ещё раз через 20 секунд:

```bash
sleep 20

"$OPS_ROOT/scripts/glitchtip-compose.sh" ps
```

Автоматически исключить restart loop:

```bash
BAD_STATE="$(
  docker ps -a \
    --filter "label=com.docker.compose.project=$ERROR_TRACKING_STACK" \
    --format '{{.Names}} {{.Status}}' |
  grep -E 'Restarting|Exited|Dead' || true
)"

[[ -z "$BAD_STATE" ]] || {
  printf 'ERROR: GlitchTip stack has unstable container state:\n%s\n' \
    "$BAD_STATE" >&2
  exit 1
}

printf 'GlitchTip containers are stable.\n'
```

Посмотреть ограниченный startup log:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  logs \
  --tail=160 \
  postgres \
  glitchtip
```

Не должно быть повторяющихся traceback/restart messages.

---

## 9. Проверить PostgreSQL и Django до публикации

Проверить PostgreSQL readiness:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T postgres \
  pg_isready \
  -U glitchtip \
  -d glitchtip \
  -h 127.0.0.1
```

Проверить SQL:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T postgres \
  psql \
  -U glitchtip \
  -d glitchtip \
  -v ON_ERROR_STOP=1 \
  -Atqc \
  'SELECT current_database(), current_user, version();'
```

Проверить реальное наличие основной таблицы GlitchTip и Django database cache:

```bash
USERS_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.users_user')::text, '');"
)"

CACHE_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.django_cache')::text, '');"
)"

[[ "$USERS_TABLE" == "users_user" ]] || {
  printf 'ERROR: GlitchTip users_user table is missing.\n' >&2
  exit 1
}

[[ "$CACHE_TABLE" == "django_cache" ]] || {
  printf 'ERROR: Django database cache table is missing.\n' >&2
  exit 1
}

printf 'GlitchTip database schema and cache table exist.\n'
```

После этого убедиться, что Django не видит ожидающих migrations:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python /code/manage.py migrate --check
```

Проверить Django system checks:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python /code/manage.py check
```

Проверить internal HTTP endpoint внутри GlitchTip container:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python - <<'PY_GLITCHTIP_HTTP'
import http.client
import os
from urllib.parse import urlsplit

host = urlsplit(os.environ["GLITCHTIP_DOMAIN"]).hostname
if not host:
    raise SystemExit("ERROR: GLITCHTIP_DOMAIN has no hostname")

conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
conn.request(
    "GET",
    "/",
    headers={
        "Host": host,
        "X-Forwarded-Proto": "https",
    },
)
response = conn.getresponse()
response.read()
conn.close()

if not 200 <= response.status < 400:
    raise SystemExit(
        f"ERROR: unexpected HTTP status: {response.status}"
    )

print(
    f"GlitchTip internal HTTP endpoint is reachable: {response.status}."
)
PY_GLITCHTIP_HTTP
```

Проверить, что metrics endpoint включён в runtime policy. Сам `/metrics` требует GlitchTip Auth Token, поэтому authenticated scrape будет проверен после создания отдельного Prometheus token в шагах 15–16:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python - <<'PY_GLITCHTIP_METRICS_ENV'
import os

value = os.environ.get("ENABLE_OBSERVABILITY_API")
if value != "True":
    raise SystemExit(
        f"ERROR: ENABLE_OBSERVABILITY_API={value!r}, expected 'True'"
    )

print("GlitchTip Prometheus metrics endpoint is enabled.")
PY_GLITCHTIP_METRICS_ENV
```
---

## 10. Создать bootstrap administrator до публикации GlitchTip

Открытая регистрация уже выключена. Administrator создаётся напрямую через Django ORM.

Создать idempotent helper:

````bash
cat > "$OPS_ROOT/scripts/glitchtip-admin-ensure.sh" <<'EOF_GLITCHTIP_ADMIN'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${GLITCHTIP_ADMIN_EMAIL:?GLITCHTIP_ADMIN_EMAIL is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${OPS_ROOT:?OPS_ROOT is not set}"

PASSWORD_FILE="$ERROR_TRACKING_SECRETS_ROOT/admin_password"

USERS_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.users_user')::text, '');"
)"

[[ "$USERS_TABLE" == "users_user" ]] || {
  printf 'ERROR: GlitchTip database schema is not initialized.\n' >&2
  printf 'Run: %s\n' \
    'glitchtip-compose.sh run --rm --no-deps glitchtip python /code/manage.py migrate --noinput' >&2
  exit 1
}

CACHE_TABLE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.django_cache')::text, '');"
)"

[[ "$CACHE_TABLE" == "django_cache" ]] || {
  printf 'ERROR: Django database cache table is not initialized.\n' >&2
  printf 'Run: %s\n' \
    'glitchtip-compose.sh run --rm --no-deps glitchtip python /code/manage.py createcachetable' >&2
  exit 1
}

[[ -s "$PASSWORD_FILE" ]] || {
  printf 'ERROR: admin password file is missing: %s\n' \
    "$PASSWORD_FILE" >&2
  exit 1
}

ADMIN_PASSWORD="$(<"$PASSWORD_FILE")"

[[ ${#ADMIN_PASSWORD} -ge 32 ]] || {
  printf 'ERROR: bootstrap admin password is unexpectedly short\n' >&2
  exit 1
}

export GLITCHTIP_BOOTSTRAP_EMAIL="$GLITCHTIP_ADMIN_EMAIL"
export GLITCHTIP_BOOTSTRAP_PASSWORD="$ADMIN_PASSWORD"

"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T \
  -e GLITCHTIP_BOOTSTRAP_EMAIL \
  -e GLITCHTIP_BOOTSTRAP_PASSWORD \
  glitchtip \
  python /code/manage.py shell <<'PY_DJANGO_ADMIN'
import os
from django.contrib.auth import get_user_model

email = os.environ["GLITCHTIP_BOOTSTRAP_EMAIL"].strip().lower()
password = os.environ["GLITCHTIP_BOOTSTRAP_PASSWORD"]

User = get_user_model()
user, created = User.objects.get_or_create(
    email=email,
    defaults={
        "is_active": True,
        "is_staff": True,
        "is_superuser": True,
    },
)

changed = False

for field in ("is_active", "is_staff", "is_superuser"):
    if not getattr(user, field):
        setattr(user, field, True)
        changed = True

if created:
    user.set_password(password)
    changed = True

if changed:
    user.save()

print(
    "GlitchTip bootstrap administrator created."
    if created
    else "GlitchTip administrator already exists."
)
PY_DJANGO_ADMIN

unset ADMIN_PASSWORD
unset GLITCHTIP_BOOTSTRAP_EMAIL
unset GLITCHTIP_BOOTSTRAP_PASSWORD

printf 'Administrator email: %s\n' "$GLITCHTIP_ADMIN_EMAIL"
printf 'Bootstrap password remains only in the secret file.\n'
EOF_GLITCHTIP_ADMIN

chmod 0750 "$OPS_ROOT/scripts/glitchtip-admin-ensure.sh"
````

Проверить helper:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-admin-ensure.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-admin-ensure.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/glitchtip-admin-ensure.sh"
```

Проверить administrator без вывода password:

```bash
export GLITCHTIP_CHECK_EMAIL="$GLITCHTIP_ADMIN_EMAIL"

"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T \
  -e GLITCHTIP_CHECK_EMAIL \
  glitchtip \
  python /code/manage.py shell <<'PY_ADMIN_CHECK'
import os
from django.contrib.auth import get_user_model

email = os.environ["GLITCHTIP_CHECK_EMAIL"].strip().lower()
User = get_user_model()

user = User.objects.get(email=email)

assert user.is_active
assert user.is_staff
assert user.is_superuser

print("GlitchTip administrator flags are correct.")
PY_ADMIN_CHECK

unset GLITCHTIP_CHECK_EMAIL
```

> `admin_password` — bootstrap credential. Не используйте `cat` этого файла в console transcript, который затем будет отправлен кому-либо.

---

## 11. Проверить, что registration действительно закрыта

Проверить effective environment **без вывода secrets**:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python - <<'PY_REGISTRATION_ENV'
import os

expected = {
    "ENABLE_USER_REGISTRATION": "False",
    "ENABLE_SOCIAL_APPS_USER_REGISTRATION": "False",
    "ENABLE_ORGANIZATION_CREATION": "False",
    "SERVER_ROLE": "all_in_one",
    "GLITCHTIP_EMBED_WORKER": "true",
    "GLITCHTIP_ENABLE_UPTIME": "False",
    "GLITCHTIP_ENABLE_LOGS": "False",
    "GLITCHTIP_ENABLE_MCP": "False",
    "GLITCHTIP_ENABLE_DUCKDB": "False",
    "ENABLE_OBSERVABILITY_API": "True",
}

for key, value in expected.items():
    actual = os.environ.get(key)
    if actual != value:
        raise SystemExit(
            f"ERROR: {key}={actual!r}, expected {value!r}"
        )

if os.environ.get("VALKEY_URL") != "":
    raise SystemExit("ERROR: VALKEY_URL is not empty")

print("GlitchTip security/runtime environment is correct.")
PY_REGISTRATION_ENV
```

---

## 12. Создать DNS record для GlitchTip

На этапе первичного выпуска certificate используем **прямой DNS**, без CDN/proxy.

Для Cloudflare запись `errors` временно должна быть **DNS only** (серое облако), а не Proxied.

Создать запись:

```text
Type: A
Name: errors
Value: SERVER_PUBLIC_IPV4
Proxy/CDN: DNS only
```

Убедиться, что public IPv4 сохранён в едином config и не исчезнет после нового SSH:

```bash
source "$HOME/config.env"

: "${SERVER_PUBLIC_IPV4:?SERVER_PUBLIC_IPV4 is not persisted in config.env}"

printf 'GlitchTip hostname: %s\n' "$GLITCHTIP_HOST"
printf 'VPS public IPv4:    %s\n' "$SERVER_PUBLIC_IPV4"
```

Дождаться, когда authoritative/public DNS начнёт возвращать именно VPS IPv4:

```bash
(
  set -Eeuo pipefail

  for attempt in $(seq 1 30); do
    mapfile -t resolved_ips < <(
      dig +short A "$GLITCHTIP_HOST" @1.1.1.1 |
        sort -u
    )

    if printf '%s\n' "${resolved_ips[@]}" |
         grep -Fxq "$SERVER_PUBLIC_IPV4"; then
      printf 'DNS-only record is ready: %s -> %s\n' \
        "$GLITCHTIP_HOST" "$SERVER_PUBLIC_IPV4"
      exit 0
    fi

    if (( attempt == 30 )); then
      printf 'ERROR: %s does not resolve directly to %s.\n' \
        "$GLITCHTIP_HOST" "$SERVER_PUBLIC_IPV4" >&2
      printf 'Current A records:\n' >&2
      printf '  %s\n' "${resolved_ips[@]:-<empty>}" >&2
      printf 'If Cloudflare is used, set only the errors record to DNS only and retry.\n' >&2
      exit 1
    fi

    sleep 10
  done
)
```

Не включать Cloudflare Proxy обратно до успешного завершения public HTTPS checks этой главы. После того как origin certificate и route подтверждены, proxy можно включить отдельно и повторить public checks.

---

## 13. Добавить GlitchTip route в центральный Caddy

Перед изменением route сначала проверяем сам Caddy filesystem contract. Это защищает central edge от опасного reload с пустым `sites/*.caddy`: Caddy считает пустой glob допустимым и validation может завершиться с кодом `0`, даже если ни один site не импортирован.

Caddy запускается с `cap_drop: ALL`, поэтому versioned Caddy config не должен зависеть от Linux capabilities для обхода filesystem permissions. В `/opt/ops/config/caddy` секретов нет: каталоги должны быть `0755`, файлы — `0644`. Нормализовать permissions **до** любых `validate`, `run` или `reload`:

```bash
source "$HOME/config.env"

sudo find "$OPS_ROOT/config/caddy" \
  -type d \
  -exec chmod 0755 {} +

sudo find "$OPS_ROOT/config/caddy" \
  -type f \
  -exec chmod 0644 {} +

namei -l "$OPS_ROOT/config/caddy/Caddyfile"
namei -l "$OPS_ROOT/config/caddy/sites"
```

Проверить, что Compose действительно монтирует весь versioned Caddy config directory в `/etc/caddy`:

```bash
(
  set -Eeuo pipefail

  source "$HOME/config.env"
  cd "$OPS_ROOT/compose/edge"

  EXPECTED_SOURCE="$(readlink -f "$OPS_ROOT/config/caddy")"

  RESOLVED_SOURCE="$(
    docker compose config --format json |
      jq -r '
        .services.caddy.volumes[]?
        | select(.target == "/etc/caddy")
        | .source
      ' |
      head -n 1
  )"

  [[ -n "$RESOLVED_SOURCE" ]] || {
    printf 'ERROR: Caddy Compose has no /etc/caddy directory mount.\n' >&2
    exit 1
  }

  RESOLVED_SOURCE="$(readlink -f "$RESOLVED_SOURCE")"

  [[ "$RESOLVED_SOURCE" == "$EXPECTED_SOURCE" ]] || {
    printf 'ERROR: wrong Caddy config mount.\n' >&2
    printf 'expected: %s\nactual:   %s\n' \
      "$EXPECTED_SOURCE" "$RESOLVED_SOURCE" >&2
    exit 1
  }

  printf 'Caddy config mount resolves to %s.\n' "$RESOLVED_SOURCE"
)
```

Проверить host-side sites до reload:

```bash
find "$OPS_ROOT/config/caddy/sites" \
  -maxdepth 1 \
  -type f \
  -name '*.caddy' \
  -printf '%f\n' |
  sort
```

Central Caddy уже обслуживает production route из предыдущих глав, поэтому каталог не должен быть пустым.

Проверить, что running Caddy видит те же site files. Если старый container использует stale/incorrect bind mount, автоматически пересоздать только Caddy из текущего Compose:

```bash
(
  set -Eeuo pipefail

  source "$HOME/config.env"
  cd "$OPS_ROOT/compose/edge"

  host_count="$(
    find "$OPS_ROOT/config/caddy/sites" \
      -maxdepth 1 \
      -type f \
      -name '*.caddy' |
      wc -l |
      tr -d ' '
  )"

  (( host_count > 0 )) || {
    printf 'ERROR: host Caddy sites directory is empty.\n' >&2
    exit 1
  }

  # A bind mount can exist and still be unreadable inside a hardened Caddy
  # container. Reject restrictive permissions before any container recreate.
  while IFS= read -r path; do
    mode="$(stat -c '%a' "$path")"
    case "$mode" in
      755|2755) ;;
      *)
        printf 'ERROR: Caddy config directory is not traversable: %s mode=%s\n' \
          "$path" "$mode" >&2
        exit 1
        ;;
    esac
  done < <(find "$OPS_ROOT/config/caddy" -type d -print)

  container_count="$({
    docker compose exec -T caddy \
      sh -eu -c '
        find /etc/caddy/sites \
          -maxdepth 1 \
          -type f \
          -name "*.caddy" |
          wc -l
      ' 2>/dev/null || true
  } | tr -d '[:space:]')"

  if [[ ! "$container_count" =~ ^[0-9]+$ ]] || \
     (( container_count == 0 )); then
    printf 'Caddy does not currently see versioned site files; recreating Caddy with current bind mounts.\n'

    docker compose \
      up -d \
      --force-recreate \
      --no-deps \
      caddy

    sleep 5
  fi

  docker compose exec -T caddy \
    sh -eu -c '
      test -d /etc/caddy/sites
      count="$(find /etc/caddy/sites -maxdepth 1 -type f -name "*.caddy" | wc -l)"
      test "$count" -gt 0
      printf "Caddy container sees %s site file(s).\n" "$count"
      ls -la /etc/caddy/sites
    '
)
```

### 13.1. Harden `caddy-add-site.sh` against empty-site reload

Перезаписать helper безопасной idempotent-версией. Она:

- использует только `$HOME/config.env`;
- проверяет whole-directory bind mount `/etc/caddy`;
- проверяет, что новый site реально виден **внутри transient и running Caddy containers**;
- считает warning `No files matching import glob pattern` ошибкой;
- не выполняет reload, если filesystem contract нарушен;
- откатывает новый site file при любой ошибке до reload.

````bash
cat > "$OPS_ROOT/scripts/caddy-add-site.sh" <<'EOF_CADDY_ADD_SITE'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s DOMAIN UPSTREAM\n' "$0" >&2
  exit 2
fi

DOMAIN="${1,,}"
UPSTREAM="$2"

[[ "$DOMAIN" =~ ^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$ ]] || {
  printf 'ERROR: invalid domain: %s\n' "$DOMAIN" >&2
  exit 2
}

[[ "$UPSTREAM" =~ ^[a-zA-Z0-9._-]+:[0-9]{1,5}$ ]] || {
  printf 'ERROR: invalid upstream: %s\n' "$UPSTREAM" >&2
  exit 2
}

CADDY_ROOT="$OPS_ROOT/config/caddy"
SITE_DIR="$CADDY_ROOT/sites"
SITE_FILE="$SITE_DIR/$DOMAIN.caddy"
EDGE_ROOT="$OPS_ROOT/compose/edge"
BACKUP_FILE="$(mktemp)"
HAD_FILE=false

trap 'rm -f "$BACKUP_FILE"' EXIT

install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0755 \
  "$CADDY_ROOT" \
  "$SITE_DIR"

# Versioned Caddy configuration contains no secrets. Caddy runs hardened
# with all capabilities dropped, so it must be able to traverse/read these
# paths using ordinary Unix permissions.
find "$CADDY_ROOT" -type d -exec chmod 0755 {} +
find "$CADDY_ROOT" -type f -exec chmod 0644 {} +

if [[ -f "$SITE_FILE" ]]; then
  cp -a "$SITE_FILE" "$BACKUP_FILE"
  HAD_FILE=true
fi

rollback_site() {
  if [[ "$HAD_FILE" == true ]]; then
    install -m 0644 "$BACKUP_FILE" "$SITE_FILE"
  else
    rm -f "$SITE_FILE"
  fi
}

cat > "$SITE_FILE" <<EOF_SITE
$DOMAIN {
    import common

    reverse_proxy $UPSTREAM {
        transport http {
            dial_timeout 5s
            response_header_timeout 30s
        }
    }
}
EOF_SITE

chmod 0644 "$SITE_FILE"

cd "$EDGE_ROOT"

EXPECTED_SOURCE="$(readlink -f "$CADDY_ROOT")"
RESOLVED_SOURCE="$(
  docker compose config --format json |
    jq -r '
      .services.caddy.volumes[]?
      | select(.target == "/etc/caddy")
      | .source
    ' |
    head -n 1
)"

if [[ -z "$RESOLVED_SOURCE" ]] || \
   [[ "$(readlink -f "$RESOLVED_SOURCE")" != "$EXPECTED_SOURCE" ]]; then
  rollback_site
  printf 'ERROR: Caddy /etc/caddy bind mount does not point to %s\n' \
    "$EXPECTED_SOURCE" >&2
  exit 1
fi

TRANSIENT_VISIBILITY="$(
  docker compose run \
    --rm \
    --no-deps \
    --entrypoint sh \
    caddy \
    -eu -c \
    "test -s '/etc/caddy/sites/$DOMAIN.caddy' && printf visible" \
    2>/dev/null || true
)"

if [[ "$TRANSIENT_VISIBILITY" != "visible" ]]; then
  rollback_site
  printf 'ERROR: transient Caddy container cannot see %s\n' \
    "/etc/caddy/sites/$DOMAIN.caddy" >&2
  exit 1
fi

VALIDATION_OUTPUT="$(
  docker compose run \
    --rm \
    --no-deps \
    caddy \
    caddy validate \
    --config /etc/caddy/Caddyfile \
    --adapter caddyfile \
    2>&1
)" || {
  rollback_site
  printf '%s\n' "$VALIDATION_OUTPUT" >&2
  printf 'ERROR: Caddy validation failed; site reverted.\n' >&2
  exit 1
}

printf '%s\n' "$VALIDATION_OUTPUT"

if grep -Fq 'No files matching import glob pattern' \
    <<<"$VALIDATION_OUTPUT"; then
  rollback_site
  printf 'ERROR: Caddy validation saw an empty site import glob; reload aborted.\n' >&2
  exit 1
fi

if ! docker compose exec -T caddy \
    sh -eu -c "test -s '/etc/caddy/sites/$DOMAIN.caddy'"; then
  rollback_site
  printf 'ERROR: running Caddy container cannot see the new site; reload aborted.\n' >&2
  exit 1
fi

RUNNING_VALIDATION="$(
  docker compose exec -T caddy \
    caddy validate \
    --config /etc/caddy/Caddyfile \
    --adapter caddyfile \
    2>&1
)" || {
  rollback_site
  printf '%s\n' "$RUNNING_VALIDATION" >&2
  printf 'ERROR: running Caddy validation failed; site reverted.\n' >&2
  exit 1
}

printf '%s\n' "$RUNNING_VALIDATION"

if grep -Fq 'No files matching import glob pattern' \
    <<<"$RUNNING_VALIDATION"; then
  rollback_site
  printf 'ERROR: running Caddy sees an empty site import glob; reload aborted.\n' >&2
  exit 1
fi

if ! docker compose exec -T -w /etc/caddy caddy \
    caddy reload \
    --config /etc/caddy/Caddyfile \
    --adapter caddyfile; then
  rollback_site

  docker compose exec -T -w /etc/caddy caddy \
    caddy reload \
    --config /etc/caddy/Caddyfile \
    --adapter caddyfile || true

  printf 'ERROR: Caddy reload failed; previous site restored.\n' >&2
  exit 1
fi

printf 'Configured: https://%s -> %s\n' \
  "$DOMAIN" "$UPSTREAM"
EOF_CADDY_ADD_SITE

chmod 0750 "$OPS_ROOT/scripts/caddy-add-site.sh"
````

Проверить helper:

```bash
bash -n "$OPS_ROOT/scripts/caddy-add-site.sh"
shellcheck -x "$OPS_ROOT/scripts/caddy-add-site.sh"
```

Добавить GlitchTip route:

```bash
"$OPS_ROOT/scripts/caddy-add-site.sh" \
  "$GLITCHTIP_HOST" \
  "$GLITCHTIP_UPSTREAM"
```

Проверить site file на host:

```bash
SITE_FILE="$OPS_ROOT/config/caddy/sites/$GLITCHTIP_HOST.caddy"

test -s "$SITE_FILE" || {
  printf 'ERROR: Caddy site file was not created: %s\n' \
    "$SITE_FILE" >&2
  exit 1
}

sed -n '1,160p' "$SITE_FILE"
```

Проверить, что running Caddy действительно импортирует site files без empty-glob warning:

```bash
(
  set -Eeuo pipefail

  cd "$OPS_ROOT/compose/edge"

  VALIDATION_OUTPUT="$(
    docker compose exec -T caddy \
      caddy validate \
      --config /etc/caddy/Caddyfile \
      --adapter caddyfile \
      2>&1
  )"

  printf '%s\n' "$VALIDATION_OUTPUT"

  if grep -Fq 'No files matching import glob pattern' \
      <<<"$VALIDATION_OUTPUT"; then
    printf 'ERROR: Caddy still has an empty site import glob.\n' >&2
    exit 1
  fi

  printf 'Caddy imports versioned site files correctly.\n'
)
```

Проверить, что Caddy и GlitchTip находятся в общей edge network:

```bash
CADDY_CONTAINER="$(
  docker ps \
    --filter "label=com.docker.compose.project=${CADDY_STACK}" \
    --filter "label=com.docker.compose.service=caddy" \
    --format '{{.Names}}' |
  head -n 1
)"

GLITCHTIP_CONTAINER="$(
  docker ps \
    --filter "label=com.docker.compose.project=${ERROR_TRACKING_STACK}" \
    --filter 'label=com.docker.compose.service=glitchtip' \
    --format '{{.Names}}' |
  head -n 1
)"

[[ -n "$CADDY_CONTAINER" ]] || {
  printf 'ERROR: Caddy container not found\n' >&2
  exit 1
}

[[ -n "$GLITCHTIP_CONTAINER" ]] || {
  printf 'ERROR: GlitchTip container not found\n' >&2
  exit 1
}

for container in \
  "$CADDY_CONTAINER" \
  "$GLITCHTIP_CONTAINER"; do

  docker inspect "$container" |
    jq -e \
      --arg network "$EDGE_NETWORK" \
      '.[0].NetworkSettings.Networks[$network] != null' \
      >/dev/null || {
        printf 'ERROR: %s is not attached to %s\n' \
          "$container" "$EDGE_NETWORK" >&2
        exit 1
      }
done

printf 'Caddy and GlitchTip share the edge network.\n'
```

---

## 14. Проверить public HTTPS GlitchTip

Дождаться certificate/public readiness:

```bash
for attempt in $(seq 1 36); do
  if curl \
      --fail \
      --silent \
      --show-error \
      --max-time 10 \
      "$GLITCHTIP_URL/" \
      >/dev/null 2>&1; then

    printf 'Public GlitchTip HTTPS endpoint is ready.\n'
    break
  fi

  if (( attempt == 36 )); then
    printf 'ERROR: GlitchTip HTTPS endpoint did not become ready\n' >&2
    docker logs --tail=120 "$CADDY_CONTAINER" >&2
    "$OPS_ROOT/scripts/glitchtip-compose.sh" \
      logs --tail=120 glitchtip >&2
    exit 1
  fi

  sleep 5
done
```

Проверить response headers:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --head \
  "$GLITCHTIP_URL/"
```

Проверить TLS certificate:

```bash
CERT_INFO="$(
  openssl s_client \
    -connect "$GLITCHTIP_HOST:443" \
    -servername "$GLITCHTIP_HOST" \
    -verify_return_error \
    </dev/null 2>/dev/null |
  openssl x509 \
    -noout \
    -subject \
    -issuer \
    -dates
)"

printf '%s\n' "$CERT_INFO"
```

Проверить HTTP -> HTTPS redirect:

```bash
HTTP_CODE="$(
  curl \
    --silent \
    --output /dev/null \
    --write-out '%{http_code}' \
    "http://$GLITCHTIP_HOST/"
)"

[[ "$HTTP_CODE" =~ ^30[1278]$ ]] || {
  printf 'ERROR: expected HTTP redirect, got %s\n' \
    "$HTTP_CODE" >&2
  exit 1
}

printf 'HTTP redirects to HTTPS.\n'
```


---

## 15. Подключить GlitchTip к Prometheus и Blackbox Exporter

GlitchTip уже находится в external Docker network `$OBSERVABILITY_NETWORK`, поэтому Prometheus может собирать internal metrics напрямую по `glitchtip:8000` без host port.

В GlitchTip endpoint `/metrics` требует GlitchTip Auth Token. Токен создадим автоматически для bootstrap administrator, сохраним **вне Git** и передадим Prometheus через `authorization.credentials_file`. Значение токена не будет записано в `prometheus.yml` и не будет напечатано в terminal.

Дополнительно Blackbox Exporter будет проверять реальный public URL через Caddy/TLS.

Создать idempotent helper для отдельного Prometheus token:

````bash
cat > "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" <<'EOF_GLITCHTIP_PROM_TOKEN'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${GLITCHTIP_ADMIN_EMAIL:?GLITCHTIP_ADMIN_EMAIL is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"

COMPOSE="$OPS_ROOT/scripts/glitchtip-compose.sh"
TOKEN_FILE="$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"
TOKEN_LABEL="prometheus-observability"

[[ -x "$COMPOSE" ]] || {
  printf 'ERROR: GlitchTip Compose wrapper is missing: %s\n' \
    "$COMPOSE" >&2
  exit 1
}

install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2750 \
  "$ERROR_TRACKING_SECRETS_ROOT"

export GLITCHTIP_PROMETHEUS_EMAIL="$GLITCHTIP_ADMIN_EMAIL"
export GLITCHTIP_PROMETHEUS_TOKEN_LABEL="$TOKEN_LABEL"

TOKEN="$(
  "$COMPOSE" exec -T \
    -e GLITCHTIP_PROMETHEUS_EMAIL \
    -e GLITCHTIP_PROMETHEUS_TOKEN_LABEL \
    glitchtip \
    python /code/manage.py shell \
      --no-imports \
      --verbosity 0 \
      --interface python \
      <<'PY_GLITCHTIP_PROM_TOKEN'
import os

from django.apps import apps
from django.contrib.auth import get_user_model

email = os.environ["GLITCHTIP_PROMETHEUS_EMAIL"].strip().lower()
label = os.environ["GLITCHTIP_PROMETHEUS_TOKEN_LABEL"].strip()

User = get_user_model()
user = User.objects.get(email=email)

preferred_names = {"APIToken", "AuthToken"}
models = [
    model
    for model in apps.get_models()
    if model.__name__ in preferred_names
]

if not models:
    models = []
    for model in apps.get_models():
        field_names = {
            field.name
            for field in model._meta.get_fields()
            if hasattr(field, "name")
        }
        if (
            "token" in field_names
            and "user" in field_names
            and "token" in model.__name__.lower()
        ):
            models.append(model)

if len(models) != 1:
    labels = [model._meta.label for model in models]
    raise SystemExit(
        "ERROR: expected exactly one GlitchTip API token model; "
        f"found {labels!r}"
    )

Token = models[0]
field_names = {
    field.name
    for field in Token._meta.get_fields()
    if hasattr(field, "name")
}

lookup = {"user": user}
if "label" in field_names:
    lookup["label"] = label
elif "name" in field_names:
    lookup["name"] = label

query = Token.objects.filter(**lookup).order_by("pk")
token_obj = query.first()

if token_obj is None:
    token_obj = Token.objects.create(**lookup)

token = str(getattr(token_obj, "token", "")).strip()

if len(token) < 20 or any(char.isspace() for char in token):
    raise SystemExit("ERROR: GlitchTip API token has unexpected format")

print(token, end="")
PY_GLITCHTIP_PROM_TOKEN
)"

unset GLITCHTIP_PROMETHEUS_EMAIL
unset GLITCHTIP_PROMETHEUS_TOKEN_LABEL

[[ ${#TOKEN} -ge 20 ]] || {
  printf 'ERROR: GlitchTip Prometheus token was not created\n' >&2
  unset TOKEN
  exit 1
}

umask 077
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
unset TOKEN

chown "$ADMIN_USER:$OPS_GROUP" "$TOKEN_FILE"
chmod 0640 "$TOKEN_FILE"

[[ -s "$TOKEN_FILE" ]] || {
  printf 'ERROR: Prometheus token file is empty\n' >&2
  exit 1
}

[[ "$(stat -c '%a' "$TOKEN_FILE")" == "640" ]] || {
  printf 'ERROR: unexpected Prometheus token mode\n' >&2
  exit 1
}

printf 'GlitchTip Prometheus auth token is ready.\n'
printf 'Token value was not printed.\n'
EOF_GLITCHTIP_PROM_TOKEN

chmod 0750 "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh"
````

Проверить helper:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh"
```

Создать/reuse token:

```bash
"$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh"
```

Проверить только metadata secret-файла, **не его содержимое**:

```bash
stat \
  -c '%a %U:%G %n' \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"
```

Ожидаемый mode — `640`.

До изменения Prometheus проверить token непосредственно против GlitchTip `/metrics`. Значение token не печатается:

```bash
(
  set -Eeuo pipefail

  GLITCHTIP_METRICS_TOKEN="$(<"$ERROR_TRACKING_SECRETS_ROOT/prometheus_token")"
  export GLITCHTIP_METRICS_TOKEN

  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T \
    -e GLITCHTIP_METRICS_TOKEN \
    glitchtip \
    python - <<'PY_GLITCHTIP_AUTH_METRICS'
import http.client
import os
from urllib.parse import urlsplit

host = urlsplit(os.environ["GLITCHTIP_DOMAIN"]).hostname
token = os.environ["GLITCHTIP_METRICS_TOKEN"]

if not host:
    raise SystemExit("ERROR: GLITCHTIP_DOMAIN has no hostname")

conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
conn.request(
    "GET",
    "/metrics",
    headers={
        "Host": host,
        "X-Forwarded-Proto": "https",
        "Authorization": f"Bearer {token}",
    },
)
response = conn.getresponse()
body = response.read().decode("utf-8", errors="replace")
conn.close()

if response.status != 200:
    raise SystemExit(
        f"ERROR: authenticated /metrics returned {response.status}"
    )

samples = [
    line
    for line in body.splitlines()
    if line and not line.startswith("#")
]

if not samples:
    raise SystemExit("ERROR: authenticated /metrics returned no samples")

print(
    f"Authenticated GlitchTip /metrics works: {len(samples)} samples."
)
PY_GLITCHTIP_AUTH_METRICS

  unset GLITCHTIP_METRICS_TOKEN
)
```

Создать idempotent integration helper:

````bash
cat > "$OPS_ROOT/scripts/glitchtip-integrate-observability.sh" <<'EOF_GLITCHTIP_OBS'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${OBSERVABILITY_ROOT:?OBSERVABILITY_ROOT is not set}"
: "${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${GLITCHTIP_URL:?GLITCHTIP_URL is not set}"

PROMETHEUS_CONFIG="$OBSERVABILITY_CONFIG_ROOT/prometheus/prometheus.yml"
PROMETHEUS_RULES="$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml"
OBSERVABILITY_COMPOSE="$OBSERVABILITY_ROOT/compose.yaml"
TOKEN_FILE="$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"
TOKEN_HELPER="$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh"

for file in \
  "$PROMETHEUS_CONFIG" \
  "$PROMETHEUS_RULES" \
  "$OBSERVABILITY_COMPOSE"; do

  [[ -f "$file" ]] || {
    printf 'ERROR: required file not found: %s\n' "$file" >&2
    exit 1
  }
done

[[ -x "$TOKEN_HELPER" ]] || {
  printf 'ERROR: token helper is missing: %s\n' \
    "$TOKEN_HELPER" >&2
  exit 1
}

"$TOKEN_HELPER"

[[ -s "$TOKEN_FILE" ]] || {
  printf 'ERROR: Prometheus token file is missing or empty\n' >&2
  exit 1
}

python3 - \
  "$PROMETHEUS_CONFIG" \
  "$PROMETHEUS_RULES" \
  "$OBSERVABILITY_COMPOSE" \
  "$GLITCHTIP_URL" <<'PY_GLITCHTIP_OBS'
from pathlib import Path
import sys

prometheus_path = Path(sys.argv[1])
rules_path = Path(sys.argv[2])
compose_path = Path(sys.argv[3])
glitchtip_url = sys.argv[4].rstrip("/") + "/"

prometheus = prometheus_path.read_text(encoding="utf-8")
rules = rules_path.read_text(encoding="utf-8")
compose = compose_path.read_text(encoding="utf-8")

if "scrape_configs:\n" not in prometheus:
    raise SystemExit("ERROR: scrape_configs section not found")

if "  - job_name: blackbox-exporter\n" not in prometheus:
    raise SystemExit(
        "ERROR: expected chapter-07 blackbox-exporter job not found"
    )

old_glitchtip_job = '''  - job_name: glitchtip
    metrics_path: /metrics
    static_configs:
      - targets:
          - glitchtip:8000
'''

new_glitchtip_job = '''  - job_name: glitchtip
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/glitchtip_prometheus_token
    static_configs:
      - targets:
          - glitchtip:8000
'''

if new_glitchtip_job not in prometheus:
    if old_glitchtip_job in prometheus:
        prometheus = prometheus.replace(
            old_glitchtip_job,
            new_glitchtip_job,
            1,
        )
    elif "  - job_name: glitchtip\n" in prometheus:
        raise SystemExit(
            "ERROR: existing glitchtip Prometheus job has unexpected format"
        )
    else:
        prometheus = (
            prometheus.rstrip()
            + "\n\n"
            + new_glitchtip_job
        )

if "  - job_name: blackbox-glitchtip\n" not in prometheus:
    prometheus = prometheus.rstrip() + f'''\n\n  - job_name: blackbox-glitchtip
    metrics_path: /probe
    params:
      module:
        - https_2xx
    static_configs:
      - targets:
          - "{glitchtip_url}"
    relabel_configs:
      - source_labels:
          - __address__
        target_label: __param_target
      - source_labels:
          - __param_target
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
'''

if "groups:\n" not in rules:
    raise SystemExit("ERROR: Prometheus groups section not found")

if "  - name: error-tracking\n" not in rules:
    rules = rules.rstrip() + '''

  - name: error-tracking
    interval: 30s
    rules:
      - alert: GlitchTipPublicEndpointDown
        expr: probe_success{job="blackbox-glitchtip"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "GlitchTip public HTTPS endpoint is down"
          description: "Public GlitchTip probe failed for {{ $labels.instance }} for more than 2 minutes."

      - alert: GlitchTipTLSCertificateExpiringSoon
        expr: |
          (
            probe_ssl_earliest_cert_expiry{job="blackbox-glitchtip"} - time()
          ) / 86400 < 14
          and
          probe_success{job="blackbox-glitchtip"} == 1
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "GlitchTip TLS certificate expires in less than 14 days"
          description: "TLS certificate for {{ $labels.instance }} expires soon."
'''

prometheus_mount_marker = (
    "      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}"
    "/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro\n"
)

token_mount = (
    "      - ${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
    "/prometheus_token:/run/secrets/glitchtip_prometheus_token:ro\n"
)

if token_mount not in compose:
    if prometheus_mount_marker not in compose:
        raise SystemExit(
            "ERROR: Prometheus config bind mount marker not found in observability Compose"
        )

    compose = compose.replace(
        prometheus_mount_marker,
        prometheus_mount_marker + token_mount,
        1,
    )

if compose.count(token_mount) != 1:
    raise SystemExit(
        "ERROR: unexpected GlitchTip Prometheus token mount count"
    )

prometheus_path.write_text(
    prometheus.rstrip() + "\n",
    encoding="utf-8",
)
rules_path.write_text(
    rules.rstrip() + "\n",
    encoding="utf-8",
)
compose_path.write_text(
    compose.rstrip() + "\n",
    encoding="utf-8",
)
PY_GLITCHTIP_OBS

chmod 0644 \
  "$PROMETHEUS_CONFIG" \
  "$PROMETHEUS_RULES" \
  "$OBSERVABILITY_COMPOSE"

printf 'GlitchTip Prometheus/Blackbox integration is configured.\n'
printf 'Prometheus uses a credentials_file; token value is not versioned.\n'
EOF_GLITCHTIP_OBS

chmod 0750 "$OPS_ROOT/scripts/glitchtip-integrate-observability.sh"
````

Проверить helper:

```bash
bash -n \
  "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-integrate-observability.sh"

shellcheck -x \
  "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-integrate-observability.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/glitchtip-integrate-observability.sh"
```

Проверить, что jobs добавлены ровно по одному разу и authentication не содержит plaintext token:

```bash
(
  set -Eeuo pipefail

  PROM_CONFIG="$OBSERVABILITY_CONFIG_ROOT/prometheus/prometheus.yml"

  [[ "$(grep -c '^  - job_name: glitchtip$' "$PROM_CONFIG")" == "1" ]]
  [[ "$(grep -c '^  - job_name: blackbox-glitchtip$' "$PROM_CONFIG")" == "1" ]]

  [[ "$(grep -c '^  - name: error-tracking$' \
    "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml")" == "1" ]]

  grep -Fq \
    'credentials_file: /run/secrets/glitchtip_prometheus_token' \
    "$PROM_CONFIG"

  if grep -Eq \
      '^[[:space:]]+credentials:[[:space:]]+[^[:space:]]+' \
      "$PROM_CONFIG"; then
    printf 'ERROR: inline Prometheus credential found\n' >&2
    exit 1
  fi

  printf 'Prometheus GlitchTip configuration is idempotent and uses credentials_file.\n'
)
```

Проверить, что observability Compose действительно монтирует secret только read-only:

```bash
(
  set -Eeuo pipefail

  "$OPS_ROOT/scripts/observability-compose.sh" config --quiet

  PROM_TOKEN_MOUNT="$(
    "$OPS_ROOT/scripts/observability-compose.sh" config --format json |
    jq -r '
      .services.prometheus.volumes[]?
      | select(.target == "/run/secrets/glitchtip_prometheus_token")
      | [.type, .source, .target, (.read_only | tostring)]
      | @tsv
    '
  )"

  [[ -n "$PROM_TOKEN_MOUNT" ]] || {
    printf 'ERROR: Prometheus token mount is absent\n' >&2
    exit 1
  }

  printf '%s\n' "$PROM_TOKEN_MOUNT"
)
```

Строка должна заканчиваться на:

```text
/run/secrets/glitchtip_prometheus_token    true
```

Валидировать Prometheus config **до recreate**. Secret также монтируется в temporary `promtool`, а `OPS_GID` добавляется только для read-доступа к `0640 alex:ops` файлу:

```bash
docker run --rm \
  --group-add "$OPS_GID" \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus:/etc/prometheus:ro" \
  -v "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token:/run/secrets/glitchtip_prometheus_token:ro" \
  "$PROMETHEUS_IMAGE" \
  check config /etc/prometheus/prometheus.yml
```

Проверить alert rules отдельно:

```bash
docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules:/rules:ro" \
  "$PROMETHEUS_IMAGE" \
  check rules /rules/vps.yml
```

Пересоздать только Prometheus:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  up \
  -d \
  --force-recreate \
  prometheus
```

Дождаться readiness без риска закрыть SSH session:

```bash
(
  set -Eeuo pipefail

  for attempt in $(seq 1 24); do
    if curl \
        --fail \
        --silent \
        --show-error \
        http://127.0.0.1:9090/-/ready \
        >/dev/null 2>&1; then
      printf 'Prometheus is ready after GlitchTip integration.\n'
      exit 0
    fi

    sleep 5
  done

  printf 'ERROR: Prometheus did not become ready\n' >&2
  "$OPS_ROOT/scripts/observability-compose.sh" \
    logs --tail=160 prometheus >&2
  exit 1
)
```

---

## 16. Проверить GlitchTip Prometheus targets и public probe

Дождаться двух healthy targets. Проверка сама ждёт несколько scrape intervals и при ошибке выводит диагностику, но `exit 1` остаётся внутри subshell и не закрывает SSH session:

```bash
(
  set -Eeuo pipefail

  for attempt in $(seq 1 24); do
    TARGET_JSON="$(
      curl \
        --fail \
        --silent \
        --show-error \
        http://127.0.0.1:9090/api/v1/targets
    )"

    TARGET_COUNT="$(
      jq '
        [
          .data.activeTargets[]
          | select(
              .labels.job == "glitchtip"
              or .labels.job == "blackbox-glitchtip"
            )
        ]
        | length
      ' <<<"$TARGET_JSON"
    )"

    DOWN_COUNT="$(
      jq '
        [
          .data.activeTargets[]
          | select(
              .labels.job == "glitchtip"
              or .labels.job == "blackbox-glitchtip"
            )
          | select(.health != "up")
        ]
        | length
      ' <<<"$TARGET_JSON"
    )"

    if [[ "$TARGET_COUNT" == "2" ]] && \
       [[ "$DOWN_COUNT" == "0" ]]; then
      jq -r '
        .data.activeTargets[]
        | select(
            .labels.job == "glitchtip"
            or .labels.job == "blackbox-glitchtip"
          )
        | [
            .labels.job,
            (.labels.instance // "-"),
            .health,
            (.lastError // "")
          ]
        | @tsv
      ' <<<"$TARGET_JSON" |
      column -t -s $'\t'

      printf 'GlitchTip internal metrics and public Blackbox target are up.\n'
      exit 0
    fi

    sleep 5
  done

  printf 'ERROR: GlitchTip Prometheus targets did not become healthy.\n' >&2

  jq -r '
    .data.activeTargets[]
    | select(
        .labels.job == "glitchtip"
        or .labels.job == "blackbox-glitchtip"
      )
    | [
        .labels.job,
        (.labels.instance // "-"),
        .health,
        (.lastError // "")
      ]
    | @tsv
  ' <<<"$TARGET_JSON" |
  column -t -s $'\t' >&2

  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    logs --since=5m glitchtip >&2

  exit 1
)
```

Ожидаемо оба targets имеют `up`:

```text
blackbox-glitchtip  https://errors.<domain>/  up
glitchtip           glitchtip:8000            up
```

Проверить Blackbox probe value непосредственно через Prometheus:

```bash
(
  set -Eeuo pipefail

  PROBE_SUCCESS="$(
    curl \
      --fail \
      --silent \
      --show-error \
      --get \
      --data-urlencode \
        'query=probe_success{job="blackbox-glitchtip"}' \
      http://127.0.0.1:9090/api/v1/query |
    jq -r '.data.result[0].value[1] // "0"'
  )"

  [[ "$PROBE_SUCCESS" == "1" ]] || {
    printf 'ERROR: GlitchTip public probe_success=%s\n' \
      "$PROBE_SUCCESS" >&2
    exit 1
  }

  printf 'GlitchTip public HTTPS probe is successful.\n'
)
```

Проверить, что alert rules загружены:

```bash
(
  set -Eeuo pipefail

  curl \
    --fail \
    --silent \
    --show-error \
    http://127.0.0.1:9090/api/v1/rules |
  jq -e '
    [
      .data.groups[]
      | select(.name == "error-tracking")
      | .rules[]
      | .name
    ]
    | sort
    == [
      "GlitchTipPublicEndpointDown",
      "GlitchTipTLSCertificateExpiringSoon"
    ]
  ' >/dev/null

  printf 'GlitchTip alert rules are loaded.\n'
)
```
---

## 17. Проверить GlitchTip/PostgreSQL logs в Loki

Alloy из главы 07 автоматически обнаруживает новые Docker containers. Дополнительный Docker socket mount GlitchTip не нужен.

Проверить, что startup logs уже пришли в Loki:

```bash
NOW_NS="$(date +%s%N)"
START_NS="$(( NOW_NS - 1800000000000 ))"

LOG_COUNT="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode \
      "query={source=\"docker\",compose_project=\"${ERROR_TRACKING_STACK}\"}" \
    --data-urlencode "start=$START_NS" \
    --data-urlencode "end=$NOW_NS" \
    --data-urlencode 'limit=100' \
    --data-urlencode 'direction=backward' \
    http://127.0.0.1:3100/loki/api/v1/query_range |
  jq '[.data.result[].values[]] | length'
)"

(( LOG_COUNT > 0 )) || {
  printf 'ERROR: no error-tracking Docker logs found in Loki\n' >&2
  "$OPS_ROOT/scripts/observability-compose.sh" \
    logs --tail=120 alloy >&2
  exit 1
}

printf 'Error-tracking Docker logs reached Loki: %s entries.\n' \
  "$LOG_COUNT"
```

Показать только labels, без вывода всего log payload:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode \
    "query={source=\"docker\",compose_project=\"${ERROR_TRACKING_STACK}\"}" \
  --data-urlencode "start=$START_NS" \
  --data-urlencode "end=$NOW_NS" \
  --data-urlencode 'limit=1' \
  http://127.0.0.1:3100/loki/api/v1/query_range |
jq -r '.data.result[].stream | to_entries | sort_by(.key) | from_entries'
```

---

## 18. Создать строгий runtime health-check GlitchTip

Этот script должен стать основной operational-проверкой главы. Он не должен возвращать success, если database, Django, HTTPS, Prometheus target или security isolation реально сломаны.

Создать:

````bash
cat > "$OPS_ROOT/scripts/glitchtip-check.sh" <<'EOF_GLITCHTIP_CHECK'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ERROR_TRACKING_STACK:?ERROR_TRACKING_STACK is not set}"
: "${ERROR_TRACKING_ROOT:?ERROR_TRACKING_ROOT is not set}"
: "${ERROR_TRACKING_DATA_ROOT:?ERROR_TRACKING_DATA_ROOT is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${GLITCHTIP_HOST:?GLITCHTIP_HOST is not set}"
: "${GLITCHTIP_URL:?GLITCHTIP_URL is not set}"
: "${GLITCHTIP_IMAGE:?GLITCHTIP_IMAGE is not set}"
: "${GLITCHTIP_POSTGRES_IMAGE:?GLITCHTIP_POSTGRES_IMAGE is not set}"
: "${GLITCHTIP_UID:?GLITCHTIP_UID is not set}"
: "${POSTGRES_UID:?POSTGRES_UID is not set}"
: "${EDGE_NETWORK:?EDGE_NETWORK is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"

COMPOSE="$OPS_ROOT/scripts/glitchtip-compose.sh"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

printf '## Compose\n'
"$COMPOSE" config --quiet
"$COMPOSE" ps

for service in postgres glitchtip; do
  container_id="$("$COMPOSE" ps -q "$service")"
  [[ -n "$container_id" ]] || fail "$service container not found"

  running="$(
    docker inspect \
      --format '{{.State.Running}}' \
      "$container_id"
  )"

  [[ "$running" == "true" ]] || \
    fail "$service container is not running"

  health="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$container_id"
  )"

  [[ "$health" == "healthy" ]] || \
    fail "$service health=$health"
done

printf '\n## Immutable images\n'
mapfile -t images < <("$COMPOSE" config --images)

[[ ${#images[@]} -eq 2 ]] || \
  fail "expected 2 Compose images, got ${#images[@]}"

for image in "${images[@]}"; do
  [[ "$image" =~ @sha256:[a-f0-9]{64}$ ]] || \
    fail "mutable image reference: $image"
done

printf 'All error-tracking images are immutable.\n'

printf '\n## PostgreSQL\n'
"$COMPOSE" exec -T postgres \
  pg_isready -U glitchtip -d glitchtip -h 127.0.0.1

[[ "$(
  "$COMPOSE" exec -T postgres \
    psql -U glitchtip -d glitchtip -Atqc 'SELECT 1;'
)" == "1" ]] || fail 'PostgreSQL SELECT 1 failed'

users_table="$(
  "$COMPOSE" exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.users_user')::text, '');"
)"

[[ "$users_table" == "users_user" ]] || \
  fail 'GlitchTip users_user table is missing'

cache_table="$(
  "$COMPOSE" exec -T postgres \
    psql \
    -U glitchtip \
    -d glitchtip \
    -Atqc \
    "SELECT COALESCE(to_regclass('public.django_cache')::text, '');"
)"

[[ "$cache_table" == "django_cache" ]] || \
  fail 'Django database cache table is missing'

printf 'GlitchTip database schema and cache table exist.\n'

printf '\n## Django\n'
"$COMPOSE" exec -T glitchtip python /code/manage.py migrate --check
"$COMPOSE" exec -T glitchtip python /code/manage.py check

"$COMPOSE" exec -T glitchtip python - <<'PY_HTTP'
import http.client
import os
from urllib.parse import urlsplit

host = urlsplit(os.environ["GLITCHTIP_DOMAIN"]).hostname
if not host:
    raise SystemExit("ERROR: GLITCHTIP_DOMAIN has no hostname")

conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
conn.request(
    "GET",
    "/",
    headers={
        "Host": host,
        "X-Forwarded-Proto": "https",
    },
)
response = conn.getresponse()
response.read()
conn.close()

if not 200 <= response.status < 400:
    raise SystemExit(
        f"ERROR: internal HTTP endpoint returned {response.status}"
    )

print("Internal GlitchTip HTTP endpoint works.")
PY_HTTP

printf '\n## Public HTTPS\n'
curl \
  --fail \
  --silent \
  --show-error \
  --max-time 10 \
  "$GLITCHTIP_URL/" \
  >/dev/null

printf 'Public GlitchTip HTTPS works.\n'

printf '\n## Prometheus targets\n'
target_error="$(
  curl \
    --fail \
    --silent \
    --show-error \
    http://127.0.0.1:9090/api/v1/targets |
  jq -r '
    [
      .data.activeTargets[]
      | select(
          .labels.job == "glitchtip"
          or .labels.job == "blackbox-glitchtip"
        )
    ] as $targets
    | if ($targets | length) != 2 then
        "expected 2 targets, got \($targets | length)"
      elif any($targets[]; .health != "up") then
        "one or more targets are down"
      else
        ""
      end
  '
)"

[[ -z "$target_error" ]] || fail "$target_error"
printf 'GlitchTip Prometheus targets are up.\n'

probe_success="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode \
      'query=probe_success{job="blackbox-glitchtip"}' \
    http://127.0.0.1:9090/api/v1/query |
  jq -r '.data.result[0].value[1] // "0"'
)"

[[ "$probe_success" == "1" ]] || \
  fail "GlitchTip Blackbox probe_success=$probe_success"

printf 'GlitchTip public Blackbox probe is successful.\n'

rules_ok="$(
  curl \
    --fail \
    --silent \
    --show-error \
    http://127.0.0.1:9090/api/v1/rules |
  jq -r '
    [
      .data.groups[]
      | select(.name == "error-tracking")
      | .rules[]
      | .name
    ]
    | sort
    | if . == [
        "GlitchTipPublicEndpointDown",
        "GlitchTipTLSCertificateExpiringSoon"
      ] then "yes" else "no" end
  '
)"

[[ "$rules_ok" == "yes" ]] || \
  fail 'GlitchTip Prometheus alert rules are not loaded'
printf 'GlitchTip Prometheus alert rules are loaded.\n'

printf '\n## Registration policy\n'
"$COMPOSE" exec -T glitchtip python - <<'PY_ENV'
import os

expected = {
    "ENABLE_USER_REGISTRATION": "False",
    "ENABLE_SOCIAL_APPS_USER_REGISTRATION": "False",
    "ENABLE_ORGANIZATION_CREATION": "False",
    "SERVER_ROLE": "all_in_one",
    "GLITCHTIP_EMBED_WORKER": "true",
    "GLITCHTIP_ENABLE_UPTIME": "False",
    "GLITCHTIP_ENABLE_LOGS": "False",
    "GLITCHTIP_ENABLE_MCP": "False",
    "GLITCHTIP_ENABLE_DUCKDB": "False",
    "ENABLE_OBSERVABILITY_API": "True",
}

for key, expected_value in expected.items():
    actual = os.environ.get(key)
    if actual != expected_value:
        raise SystemExit(
            f"ERROR: {key}={actual!r}; expected {expected_value!r}"
        )

if os.environ.get("VALKEY_URL") != "":
    raise SystemExit("ERROR: VALKEY_URL must be empty")

print("GlitchTip registration/runtime policy is correct.")
PY_ENV

printf '\n## Network isolation\n'
POSTGRES_ID="$("$COMPOSE" ps -q postgres)"
GLITCHTIP_ID="$("$COMPOSE" ps -q glitchtip)"

postgres_networks="$(
  docker inspect "$POSTGRES_ID" |
  jq -r '.[0].NetworkSettings.Networks | keys[]'
)"

grep -Fxq "$EDGE_NETWORK" <<<"$postgres_networks" && \
  fail 'PostgreSQL is attached to public edge network'

grep -Fxq "$OBSERVABILITY_NETWORK" <<<"$postgres_networks" && \
  fail 'PostgreSQL is attached to observability network'

for network in "$EDGE_NETWORK" "$OBSERVABILITY_NETWORK"; do
  docker inspect "$GLITCHTIP_ID" |
    jq -e \
      --arg network "$network" \
      '.[0].NetworkSettings.Networks[$network] != null' \
      >/dev/null || fail "GlitchTip is not attached to $network"
done

for service in postgres glitchtip; do
  container_id="$("$COMPOSE" ps -q "$service")"
  published="$(docker port "$container_id" 2>/dev/null || true)"
  [[ -z "$published" ]] || \
    fail "$service unexpectedly publishes host ports: $published"
done

printf 'Database is internal and no error-tracking host ports are published.\n'

printf '\n## Persistent storage\n'
postgres_owner="$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/postgres")"
uploads_owner="$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/uploads")"

[[ "$postgres_owner" == "$POSTGRES_UID" ]] || \
  fail "PostgreSQL directory UID=$postgres_owner expected $POSTGRES_UID"

[[ "$uploads_owner" == "$GLITCHTIP_UID" ]] || \
  fail "uploads directory UID=$uploads_owner expected $GLITCHTIP_UID"

printf 'Persistent storage ownership is correct.\n'

printf '\n## Secrets\n'
for file in \
  secret_key \
  postgres_password \
  admin_password \
  prometheus_token \
  postgres.env \
  glitchtip.env; do

  path="$ERROR_TRACKING_SECRETS_ROOT/$file"
  [[ -s "$path" ]] || fail "missing secret file: $file"

  mode="$(stat -c '%a' "$path")"
  [[ "$mode" == "640" ]] || \
    fail "$file mode=$mode expected 640"
done

if git -C "$OPS_ROOT" ls-files |
  grep -Eq \
    '(^|/)(admin_password|postgres_password|prometheus_token|secret_key|postgres\.env|glitchtip\.env)$'; then
  fail 'GlitchTip secret file is tracked by Git'
fi

printf 'Secret files are present, protected and outside Git.\n'

printf '\nGlitchTip check passed.\n'
EOF_GLITCHTIP_CHECK

chmod 0750 "$OPS_ROOT/scripts/glitchtip-check.sh"
````

Проверить script:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-check.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-check.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/glitchtip-check.sh"
```

Последняя строка должна быть:

```text
GlitchTip check passed.
```

---

## 19. Войти в GlitchTip через браузер

GlitchTip уже опубликован, но self-registration отключена. Используется administrator из шага 10.

Открыть:

```text
https://errors.<BASE_DOMAIN>/
```

Email administrator можно безопасно вывести:

```bash
printf '%s\n' "$GLITCHTIP_ADMIN_EMAIL"
```

Пароль намеренно не печатается общими командами главы.

Если терминал сейчас **не записывается** и его output не будет отправляться в chat/issue/log, пароль можно локально посмотреть одной командой:

```bash
less "$ERROR_TRACKING_SECRETS_ROOT/admin_password"
```

После копирования выйти из `less` клавишей `q`.

> Не вставляйте вывод password в отчёт о выполнении главы.
>
> В следующей главе secrets будут переведены на SOPS + age; пока этот файл является локальным bootstrap secret.

После входа убедиться, что отображается GlitchTip UI и administrator account.

---

## 20. Создать первую Organization и Project

Этот шаг выполняется в UI, потому что именно здесь создаётся реальный project DSN, который затем используют Sentry-compatible SDK приложений.

В GlitchTip:

1. Создать organization, например `production`.
2. Создать project, например `deploy-test` или название первого production-приложения.
3. Открыть настройки проекта / SDK setup.
4. Скопировать **DSN** проекта.

DSN выглядит примерно так:

```text
https://PUBLIC_KEY@errors.example.com/1
```

DSN **не является паролем**: client SDK должен иметь возможность отправлять его с frontend/mobile-кода. Но в этой инфраструктуре мы всё равно храним test DSN централизованно в `$HOME/config.env`, а не размазываем по shell history.

Сохранить DSN интерактивно, без записи самого значения в команду/history:

```bash
printf 'Paste GlitchTip project DSN and press Enter: '
IFS= read -r GLITCHTIP_TEST_DSN

[[ -n "$GLITCHTIP_TEST_DSN" ]] || {
  printf 'ERROR: empty DSN\n' >&2
  exit 1
}

export GLITCHTIP_TEST_DSN
```

Проверить DSN до сохранения:

```bash
python3 - <<'PY_DSN_VALIDATE'
import os
from urllib.parse import urlsplit

expected_host = os.environ["GLITCHTIP_HOST"]
dsn = os.environ["GLITCHTIP_TEST_DSN"].strip()
parsed = urlsplit(dsn)

if parsed.scheme != "https":
    raise SystemExit("ERROR: DSN must use https")

if parsed.hostname != expected_host:
    raise SystemExit(
        f"ERROR: DSN host={parsed.hostname!r}, "
        f"expected {expected_host!r}"
    )

if not parsed.username:
    raise SystemExit("ERROR: DSN public key is missing")

project_id = parsed.path.strip("/").split("/")[-1]
if not project_id.isdigit():
    raise SystemExit("ERROR: DSN project id is not numeric")

print("GlitchTip DSN format is valid.")
PY_DSN_VALIDATE
```

Сохранить/обновить только `GLITCHTIP_TEST_DSN` в unified config:

```bash
python3 - "$HOME/config.env" "$GLITCHTIP_TEST_DSN" <<'PY_SAVE_DSN'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
value = sys.argv[2]
key = "GLITCHTIP_TEST_DSN"

text = path.read_text(encoding="utf-8")
lines = text.splitlines()
pattern = re.compile(r"^\s*export\s+GLITCHTIP_TEST_DSN=")

out = []
replaced = False

for line in lines:
    if pattern.match(line):
        if not replaced:
            out.append(f"export {key}={shlex.quote(value)}")
            replaced = True
        continue
    out.append(line)

if not replaced:
    if out and out[-1].strip():
        out.append("")
    out.append(f"export {key}={shlex.quote(value)}")

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY_SAVE_DSN

chmod 0600 "$HOME/config.env"
unset GLITCHTIP_TEST_DSN
source "$HOME/config.env"
```

Проверить только metadata DSN, не public key:

```bash
python3 - <<'PY_DSN_METADATA'
import os
from urllib.parse import urlsplit

parsed = urlsplit(os.environ["GLITCHTIP_TEST_DSN"])
project_id = parsed.path.strip("/").split("/")[-1]

print(f"DSN host: {parsed.hostname}")
print(f"DSN project id: {project_id}")
PY_DSN_METADATA
```

---

## 21. Создать repeatable GlitchTip test-event sender

Для infrastructure smoke test не устанавливаем случайный SDK package на VPS. Отправляем минимальный Sentry-compatible envelope напрямую в documented ingest endpoint.

Создать helper:

````bash
cat > "$OPS_ROOT/scripts/glitchtip-send-test-event.sh" <<'EOF_GLITCHTIP_TEST_EVENT'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' \
    "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${GLITCHTIP_TEST_DSN:?GLITCHTIP_TEST_DSN is not set}"
: "${GLITCHTIP_HOST:?GLITCHTIP_HOST is not set}"

export GLITCHTIP_TEST_DSN GLITCHTIP_HOST

python3 - <<'PY_SEND_EVENT'
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


dsn = os.environ["GLITCHTIP_TEST_DSN"].strip()
expected_host = os.environ["GLITCHTIP_HOST"]
parsed = urlsplit(dsn)

if parsed.scheme != "https" or parsed.hostname != expected_host:
    raise SystemExit("ERROR: invalid GlitchTip test DSN")

if not parsed.username:
    raise SystemExit("ERROR: DSN public key missing")

project_id = parsed.path.strip("/").split("/")[-1]
if not project_id.isdigit():
    raise SystemExit("ERROR: invalid DSN project id")

host = parsed.hostname
if parsed.port:
    host = f"{host}:{parsed.port}"

query = urlencode({
    "sentry_key": parsed.username,
    "sentry_version": "7",
    "sentry_client": "vps-guide-chapter-08/1.0",
})
endpoint = (
    f"{parsed.scheme}://{host}/api/{project_id}/envelope/?{query}"
)
event_id = uuid.uuid4().hex
sent_at = utc_now()

header = {
    "event_id": event_id,
    "dsn": dsn,
    "sent_at": sent_at,
}

item_header = {
    "type": "event",
    "content_type": "application/json",
}

event = {
    "event_id": event_id,
    "timestamp": sent_at,
    "platform": "other",
    "level": "error",
    "environment": "production",
    "release": "vps-guide-chapter-08",
    "logger": "vps-guide",
    "message": "Chapter 08 GlitchTip production smoke test",
    "tags": {
        "source": "vps-guide",
        "chapter": "08",
    },
    "extra": {
        "purpose": "verify GlitchTip Sentry-compatible ingest path",
    },
}

payload = (
    json.dumps(header, separators=(",", ":"))
    + "\n"
    + json.dumps(item_header, separators=(",", ":"))
    + "\n"
    + json.dumps(event, separators=(",", ":"))
    + "\n"
).encode("utf-8")

request = Request(
    endpoint,
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/x-sentry-envelope",
        "User-Agent": "vps-guide-chapter-08/1.0",
    },
)

try:
    with urlopen(request, timeout=15) as response:
        status = response.status
except Exception as exc:
    raise SystemExit(f"ERROR: GlitchTip ingest request failed: {exc}") from exc

if not 200 <= status < 300:
    raise SystemExit(f"ERROR: GlitchTip ingest HTTP status {status}")

print(f"GlitchTip smoke event accepted: HTTP {status}")
print(f"Event ID: {event_id}")
PY_SEND_EVENT
EOF_GLITCHTIP_TEST_EVENT

chmod 0750 "$OPS_ROOT/scripts/glitchtip-send-test-event.sh"
````

Проверить:

```bash
bash -n "$OPS_ROOT/scripts/glitchtip-send-test-event.sh"
shellcheck -x "$OPS_ROOT/scripts/glitchtip-send-test-event.sh"
```

Отправить event:

```bash
"$OPS_ROOT/scripts/glitchtip-send-test-event.sh"
```

Ожидается:

```text
GlitchTip smoke event accepted: HTTP 2xx
Event ID: <32 hex characters>
```

> HTTP acceptance подтверждает ingest path. Sender передаёт DSN public key также как `sentry_key` query parameter, потому что GlitchTip требует этот параметр для envelope authentication. В следующем шаге дополнительно проверяем, что background worker обработал событие и оно появилось в UI.

---

## 22. Подтвердить end-to-end error tracking в UI

После test event подождать несколько секунд:

```bash
sleep 10
```

Проверить, что all-in-one process не упал после обработки event:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" ps

BAD_STATE="$(
  docker ps -a \
    --filter "label=com.docker.compose.project=$ERROR_TRACKING_STACK" \
    --format '{{.Names}} {{.Status}}' |
  grep -E 'Restarting|Exited|Dead' || true
)"

[[ -z "$BAD_STATE" ]] || {
  printf 'ERROR: error-tracking became unstable after event ingest:\n%s\n' \
    "$BAD_STATE" >&2
  exit 1
}

printf 'GlitchTip stack remained stable after event ingest.\n'
```

Проверить последние application logs только на fatal patterns:

```bash
RECENT_ERRORS="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    logs --since=2m glitchtip 2>&1 |
  grep -Ei \
    'Traceback|panic|fatal|unhandled exception|database.*(refused|failed)' || true
)"

[[ -z "$RECENT_ERRORS" ]] || {
  printf 'ERROR: suspicious GlitchTip log lines after smoke event:\n%s\n' \
    "$RECENT_ERRORS" >&2
  exit 1
}

printf 'No fatal GlitchTip log patterns detected after smoke event.\n'
```

В браузере открыть созданный project и перейти в **Issues**.

Должен появиться issue/event с сообщением:

```text
Chapter 08 GlitchTip production smoke test
```

Проверить у события:

- environment: `production`;
- release: `vps-guide-chapter-08`;
- level: `error`;
- tag `source=vps-guide`.

Это единственный обязательный визуальный confirmation в главе: ingest API может вернуть success раньше, чем async worker завершит создание issue.

---

## 23. Проверить production network isolation

GlitchTip должен быть доступен Caddy и Prometheus, но не публиковать host port. PostgreSQL должен находиться только во внутренней network stack.

Получить container IDs:

```bash
POSTGRES_ID="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q postgres
)"
GLITCHTIP_ID="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q glitchtip
)"

[[ -n "$POSTGRES_ID" && -n "$GLITCHTIP_ID" ]] || {
  printf 'ERROR: GlitchTip container IDs not found\n' >&2
  exit 1
}
```

Проверить host port mappings:

```bash
for container in \
  "$POSTGRES_ID" \
  "$GLITCHTIP_ID"; do

  published="$(docker port "$container" 2>/dev/null || true)"

  [[ -z "$published" ]] || {
    printf 'ERROR: container %s publishes host ports:\n%s\n' \
      "$container" "$published" >&2
    exit 1
  }
done

printf 'GlitchTip/PostgreSQL publish no host ports.\n'
```

Убедиться, что host не слушает `8000` и `5432` от Docker:

```bash
if sudo ss -lntp |
  grep -E ':(8000|5432)[[:space:]]'; then
  printf 'ERROR: unexpected host listener on 8000/5432\n' >&2
  exit 1
fi

printf 'No host listeners on GlitchTip/PostgreSQL ports.\n'
```

Проверить PostgreSQL networks:

```bash
docker inspect "$POSTGRES_ID" |
jq -r '.[0].NetworkSettings.Networks | keys[]' |
sort
```

Автоматический gate:

```bash
POSTGRES_NETWORKS="$(
  docker inspect "$POSTGRES_ID" |
  jq -r '.[0].NetworkSettings.Networks | keys[]'
)"

if grep -Fxq "$EDGE_NETWORK" <<<"$POSTGRES_NETWORKS"; then
  printf 'ERROR: PostgreSQL is attached to edge network\n' >&2
  exit 1
fi

if grep -Fxq "$OBSERVABILITY_NETWORK" <<<"$POSTGRES_NETWORKS"; then
  printf 'ERROR: PostgreSQL is attached to observability network\n' >&2
  exit 1
fi

[[ "$(wc -l <<<"$POSTGRES_NETWORKS" | tr -d ' ')" == "1" ]] || {
  printf 'ERROR: PostgreSQL should have exactly one internal network\n' >&2
  exit 1
}

printf 'PostgreSQL is isolated on one internal network.\n'
```

Проверить GlitchTip external networks:

```bash
for network in \
  "$EDGE_NETWORK" \
  "$OBSERVABILITY_NETWORK"; do

  docker inspect "$GLITCHTIP_ID" |
    jq -e \
      --arg network "$network" \
      '.[0].NetworkSettings.Networks[$network] != null' \
      >/dev/null || {
        printf 'ERROR: GlitchTip is not attached to %s\n' \
          "$network" >&2
        exit 1
      }
done

printf 'GlitchTip is reachable only through intended Docker networks.\n'
```

Проверить internal network flag:

```bash
INTERNAL_NETWORK="$(
  docker inspect "$POSTGRES_ID" |
  jq -r '.[0].NetworkSettings.Networks | keys[0]'
)"

[[ "$(
  docker network inspect "$INTERNAL_NETWORK" \
    --format '{{.Internal}}'
)" == "true" ]] || {
  printf 'ERROR: PostgreSQL network is not internal=true\n' >&2
  exit 1
}

printf 'PostgreSQL Docker network is internal=true.\n'
```

---

## 24. Проверить container security и filesystem permissions

Проверить фактический GlitchTip process user:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip id
```

Автоматическая проверка UID:

```bash
RUNTIME_GLITCHTIP_UID="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T glitchtip id -u
)"

[[ "$RUNTIME_GLITCHTIP_UID" == "$GLITCHTIP_UID" ]] || {
  printf 'ERROR: GlitchTip runtime UID=%s expected %s\n' \
    "$RUNTIME_GLITCHTIP_UID" "$GLITCHTIP_UID" >&2
  exit 1
}

printf 'GlitchTip runs as expected non-root image user.\n'
```

Проверить `no-new-privileges` и dropped capabilities:

```bash
docker inspect "$GLITCHTIP_ID" |
jq -e '
  .[0].HostConfig.SecurityOpt
  | index("no-new-privileges:true") != null
' >/dev/null || {
  printf 'ERROR: GlitchTip no-new-privileges is missing\n' >&2
  exit 1
}

CAP_DROP="$(
  docker inspect "$GLITCHTIP_ID" |
  jq -r '.[0].HostConfig.CapDrop[]?'
)"

[[ "$CAP_DROP" == "ALL" ]] || {
  printf 'ERROR: GlitchTip does not drop all capabilities\n' >&2
  exit 1
}

printf 'GlitchTip container hardening is active.\n'
```

Проверить persistent directories:

```bash
sudo find "$ERROR_TRACKING_DATA_ROOT" \
  -maxdepth 2 \
  -printf '%m %u:%g %p\n' |
sort
```

Автоматический owner gate:

```bash
[[ "$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/postgres")" \
    == "$POSTGRES_UID" ]] || {
  printf 'ERROR: PostgreSQL data owner is wrong\n' >&2
  exit 1
}

[[ "$(stat -c '%u' "$ERROR_TRACKING_DATA_ROOT/uploads")" \
    == "$GLITCHTIP_UID" ]] || {
  printf 'ERROR: GlitchTip uploads owner is wrong\n' >&2
  exit 1
}

printf 'Persistent directory owners are correct.\n'
```

Проверить secret modes без вывода values:

```bash
for file in \
  secret_key \
  postgres_password \
  admin_password \
  postgres.env \
  glitchtip.env; do

  mode="$(
    stat -c '%a' \
      "$ERROR_TRACKING_SECRETS_ROOT/$file"
  )"

  [[ "$mode" == "640" ]] || {
    printf 'ERROR: %s mode=%s expected 640\n' \
      "$file" "$mode" >&2
    exit 1
  }
done

printf 'GlitchTip secret permissions are correct.\n'
```

---

## 25. Проверить database backup-readiness

Полноценный offsite backup будет настроен позже. Сейчас проверяем важное prerequisite: PostgreSQL должен успешно создавать **логический custom-format dump**, который `pg_restore` умеет прочитать.

> Нельзя делать backup PostgreSQL простым копированием live `/var/lib/postgresql/data`. Для production backup будет использоваться logical dump + offsite restic.

Создать test dump только внутри `/tmp` PostgreSQL container:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T postgres \
  sh -eu -c '
    dump=/tmp/glitchtip-ch08-smoke.dump
    rm -f "$dump"

    pg_dump \
      -U glitchtip \
      -d glitchtip \
      -Fc \
      -f "$dump"

    test -s "$dump"
    pg_restore --list "$dump" >/dev/null

    size="$(du -h "$dump" | cut -f1)"
    printf "Logical PostgreSQL dump is readable: %s\\n" "$size"

    rm -f "$dump"
  '
```

Проверить, что application tables существуют:

```bash
TABLE_COUNT="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T postgres \
    psql \
      -U glitchtip \
      -d glitchtip \
      -Atqc \
      "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
)"

(( TABLE_COUNT > 0 )) || {
  printf 'ERROR: GlitchTip database has no public tables\n' >&2
  exit 1
}

printf 'GlitchTip database contains %s public tables.\n' \
  "$TABLE_COUNT"
```

---

## 26. Проверить persistence после controlled restart

Проверим, что persistent state не зависит от lifecycle container.

Запомнить administrator count:

```bash
ADMIN_COUNT_BEFORE="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T glitchtip \
    python /code/manage.py shell -c \
    'from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).count())' |
  tail -n 1 |
  tr -d '\r'
)"

(( ADMIN_COUNT_BEFORE >= 1 )) || {
  printf 'ERROR: no GlitchTip superuser before restart\n' >&2
  exit 1
}

printf 'Superusers before restart: %s\n' "$ADMIN_COUNT_BEFORE"
```

Перезапустить database отдельно и дождаться health:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" restart postgres

for attempt in $(seq 1 24); do
  POSTGRES_ID="$(
    "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q postgres
  )"

  health_status="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$POSTGRES_ID"
  )"

  [[ "$health_status" == "healthy" ]] && break

  if (( attempt == 24 )); then
    printf 'ERROR: PostgreSQL did not recover after restart\n' >&2
    "$OPS_ROOT/scripts/glitchtip-compose.sh" \
      logs --tail=160 postgres >&2
    exit 1
  fi

  sleep 5
done

printf 'PostgreSQL recovered after restart.\n'
```

Перезапустить GlitchTip:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" restart glitchtip

for attempt in $(seq 1 30); do
  GLITCHTIP_ID="$(
    "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q glitchtip
  )"

  health_status="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$GLITCHTIP_ID"
  )"

  [[ "$health_status" == "healthy" ]] && break

  if (( attempt == 30 )); then
    printf 'ERROR: GlitchTip did not recover after restart\n' >&2
    "$OPS_ROOT/scripts/glitchtip-compose.sh" \
      logs --tail=200 glitchtip >&2
    exit 1
  fi

  sleep 5
done

printf 'GlitchTip recovered after restart.\n'
```

Проверить administrator после restart:

```bash
ADMIN_COUNT_AFTER="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T glitchtip \
    python /code/manage.py shell -c \
    'from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).count())' |
  tail -n 1 |
  tr -d '\r'
)"

[[ "$ADMIN_COUNT_AFTER" == "$ADMIN_COUNT_BEFORE" ]] || {
  printf 'ERROR: superuser count changed after restart: %s -> %s\n' \
    "$ADMIN_COUNT_BEFORE" "$ADMIN_COUNT_AFTER" >&2
  exit 1
}

printf 'GlitchTip persistent database state survived restart.\n'
```

Запустить полный health check ещё раз:

```bash
"$OPS_ROOT/scripts/glitchtip-check.sh"
```

---

## 27. Зафиксировать integration contract для production-приложений

Создать versioned документацию без реального DSN:

```bash
install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0755 \
  "$ERROR_TRACKING_CONFIG_ROOT"
```

````bash
cat > "$ERROR_TRACKING_CONFIG_ROOT/README.md" <<'EOF_ERROR_TRACKING_README'
# Error tracking contract

Production applications report exceptions to the central GlitchTip instance.

## Runtime variables

Each application receives its own project DSN through runtime environment/secrets:

- `SENTRY_DSN` — GlitchTip project DSN;
- `SENTRY_ENVIRONMENT=production`;
- `SENTRY_RELEASE` — immutable application release, preferably Git SHA or deployed image identifier.

Do not hard-code a DSN into server-side source when runtime environment injection is available.

## SDK policy

- initialize the Sentry-compatible SDK early in application startup;
- capture unhandled exceptions;
- set `environment=production`;
- set an immutable `release` value;
- keep production transaction sampling low initially (`0.01` / 1%);
- disable Sentry session tracking when the SDK supports that option;
- do not enable GlitchTip structured-log ingestion by default because central runtime logs are already stored in Loki;
- never send passwords, authorization headers, cookies, tokens or other secrets as custom context.

## Verification

After every first integration of a new application:

1. deploy the application with its project DSN;
2. emit one intentional test exception;
3. verify the event appears in the correct GlitchTip project;
4. verify `environment` and `release` labels;
5. remove any temporary debug endpoint used to create the exception.

## Infrastructure ownership

GlitchTip server configuration is managed by:

- `compose/error-tracking/compose.yaml`;
- `scripts/glitchtip-*.sh`;
- central Caddy;
- Prometheus/Blackbox/Loki from the observability stack.

Credentials and database data live outside Git under `/opt/data/error-tracking`.
EOF_ERROR_TRACKING_README
````

Permissions:

```bash
chmod 0644 "$ERROR_TRACKING_CONFIG_ROOT/README.md"
```

---

## 28. SMTP/email notifications — optional, not a chapter gate

GlitchTip `6.2` no longer requires email configuration for a working self-hosted installation. Поэтому глава считается production-valid без SMTP.

Это намеренно: нельзя безопасно придумать SMTP credentials за пользователя.

Если позже появится отдельный transactional SMTP provider, configure email через GlitchTip environment variables из official documentation и храните credentials только в encrypted/runtime secrets.

До этого:

- GlitchTip UI полностью работает;
- SDK ingest работает;
- Prometheus/Blackbox availability alerts продолжают приходить через существующий Alertmanager -> Telegram;
- application issues доступны в GlitchTip UI.

Не добавляйте fake SMTP server, `localhost:25` или публичный mail relay только ради прохождения главы.

---

## 29. Проверить resource budget VPS

GlitchTip + PostgreSQL добавляют постоянную нагрузку к observability stack. На VPS 4 GB RAM важно проверить фактический headroom.

Снимок container resources:

```bash
docker stats \
  --no-stream \
  --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}'
```

Host memory:

```bash
free -h
```

Disk:

```bash
df -h /
```

Размер error-tracking data:

```bash
sudo du -sh "$ERROR_TRACKING_DATA_ROOT"
```

Проверить OOM killer с момента boot:

```bash
if sudo journalctl \
    -k \
    -b \
    --no-pager |
  grep -Ei \
    'out of memory|oom-kill|killed process' \
    >/tmp/ch08-oom.log; then

  printf 'ERROR: kernel OOM activity detected:\n' >&2
  cat /tmp/ch08-oom.log >&2
  rm -f /tmp/ch08-oom.log
  exit 1
fi

rm -f /tmp/ch08-oom.log
printf 'No kernel OOM activity detected in current boot.\n'
```

Проверить минимум `4 GiB` свободного disk после установки:

```bash
FREE_GIB="$(
  df -BG --output=avail / |
  tail -n 1 |
  tr -dc '0-9'
)"

(( FREE_GIB >= 4 )) || {
  printf 'ERROR: less than 4 GiB free after GlitchTip install: %s GiB\n' \
    "$FREE_GIB" >&2
  exit 1
}

printf 'Post-install free disk: %s GiB\n' "$FREE_GIB"
```

---

## 30. Выполнить полный static audit файлов главы 08

Загрузить config:

```bash
source "$HOME/config.env"
```

Проверить Bash scripts:

```bash
for script in \
  chapter-08-configure.sh \
  glitchtip-secrets-ensure.sh \
  glitchtip-compose.sh \
  glitchtip-admin-ensure.sh \
  glitchtip-prometheus-token-ensure.sh \
  glitchtip-integrate-observability.sh \
  glitchtip-check.sh \
  glitchtip-send-test-event.sh; do

  bash -n "$OPS_ROOT/scripts/$script" || exit 1
  shellcheck -x "$OPS_ROOT/scripts/$script" || exit 1
done

printf 'Chapter 08 Bash scripts pass syntax and ShellCheck.\n'
```

Проверить Compose:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" config --quiet
```

Проверить immutable images:

```bash
MUTABLE_IMAGES="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" config --images |
  grep -Ev '@sha256:[a-f0-9]{64}$' || true
)"

[[ -z "$MUTABLE_IMAGES" ]] || {
  printf 'ERROR: mutable error-tracking images found:\n%s\n' \
    "$MUTABLE_IMAGES" >&2
  exit 1
}

printf 'All error-tracking images are immutable.\n'
```

Проверить Prometheus config/rules ещё раз:

```bash
docker run --rm \
  --group-add "$OPS_GID" \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus:/etc/prometheus:ro" \
  -v "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token:/run/secrets/glitchtip_prometheus_token:ro" \
  "$PROMETHEUS_IMAGE" \
  check config /etc/prometheus/prometheus.yml

docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules:/rules:ro" \
  "$PROMETHEUS_IMAGE" \
  check rules /rules/vps.yml
```

Проверить Caddy:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Проверить, что active scripts больше не source legacy `/etc/vps-guide`:

```bash
if grep -R -nE \
    '^[[:space:]]*(source|\.)[[:space:]]+/etc/vps-guide/' \
    "$OPS_ROOT/scripts" \
    --exclude='chapter-06-configure.sh'; then

  printf 'ERROR: active legacy /etc/vps-guide config reference remains\n' >&2
  exit 1
fi

printf 'No active legacy config references remain.\n'
```

Проверить, что no secret values случайно попали в versioned files через известные secret file contents:

```bash
for secret_file in \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"; do

  secret="$(<"$secret_file")"

  [[ -n "$secret" ]] || {
    printf 'ERROR: empty secret file: %s\n' "$secret_file" >&2
    exit 1
  }

  if grep -R -F -l \
      --exclude-dir=.git \
      -- "$secret" \
      "$OPS_ROOT"; then
    printf 'ERROR: a GlitchTip secret leaked into %s\n' \
      "$OPS_ROOT" >&2
    unset secret
    exit 1
  fi

done

unset secret
printf 'No known GlitchTip secret value exists in versioned tree.\n'
```

Проверить, что `$HOME/config.env` не tracked:

```bash
CONFIG_REALPATH="$(realpath "$HOME/config.env")"
OPS_REALPATH="$(realpath "$OPS_ROOT")"

case "$CONFIG_REALPATH" in
  "$OPS_REALPATH"/*)
    printf 'ERROR: unified config.env is inside repository\n' >&2
    exit 1
    ;;
esac

printf 'Unified config.env remains outside Git.\n'
```

---

## 31. Обновить repository README

Добавить раздел idempotently:

````bash
python3 - "$OPS_ROOT/README.md" <<'PY_README_GLITCHTIP'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

marker = "## Error tracking"

section = '''

## Error tracking

Production application errors are collected by a self-hosted GlitchTip stack:

- GlitchTip all-in-one service;
- dedicated PostgreSQL;
- central Caddy HTTPS ingress;
- no public GlitchTip/PostgreSQL host ports;
- Prometheus `/metrics` scraping;
- Blackbox public HTTPS probing;
- Docker logs through Alloy -> Loki;
- runtime data and credentials outside Git under `/opt/data/error-tracking`.

Operational check:

```bash
/opt/ops/scripts/glitchtip-check.sh
```
'''

if marker not in text:
    path.write_text(text.rstrip() + section + "\n", encoding="utf-8")
    print("README error-tracking section added.")
else:
    print("README error-tracking section already exists.")
PY_README_GLITCHTIP
````

Проверить section:

```bash
grep -n -A24 '^## Error tracking$' "$OPS_ROOT/README.md"
```

---

## 32. Финальный runtime gate главы 08

Сначала базовый observability stack:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
```

Затем GlitchTip:

```bash
"$OPS_ROOT/scripts/glitchtip-check.sh"
```

Ожидаемые последние строки:

```text
Observability check passed.
GlitchTip check passed.
```

Проверить все error-tracking containers:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" ps
```

Должны быть только:

- `postgres` — `Up ... (healthy)`;
- `glitchtip` — `Up ... (healthy)`.

Автоматически исключить restart/exited state:

```bash
BAD_ERROR_TRACKING="$(
  docker ps -a \
    --filter "label=com.docker.compose.project=$ERROR_TRACKING_STACK" \
    --format '{{.Names}} {{.Status}}' |
  grep -E 'Restarting|Exited|Dead' || true
)"

[[ -z "$BAD_ERROR_TRACKING" ]] || {
  printf 'ERROR: error-tracking final state is unhealthy:\n%s\n' \
    "$BAD_ERROR_TRACKING" >&2
  exit 1
}

printf 'Error-tracking containers are stable.\n'
```

Проверить failed systemd units:

```bash
FAILED_UNITS="$(
  systemctl \
    --failed \
    --no-legend \
    --plain |
  awk 'NF {print}'
)"

[[ -z "$FAILED_UNITS" ]] || {
  printf 'ERROR: failed systemd units exist:\n%s\n' \
    "$FAILED_UNITS" >&2
  exit 1
}

printf 'No failed systemd units.\n'
```

Проверить production application из предыдущих глав:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health"
```

Проверить GlitchTip public endpoint:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --output /dev/null \
  "$GLITCHTIP_URL/"

printf 'Production app and GlitchTip public endpoints are healthy.\n'
```

---

## 33. Проверить Git diff до commit

Вернуться в repository:

```bash
cd "$OPS_ROOT"
```

Посмотреть изменения:

```bash
git status --short
```

Ожидаемые versioned изменения включают:

```text
compose/error-tracking/compose.yaml
compose/observability/compose.yaml
config/error-tracking/README.md
config/caddy/sites/errors.<domain>.caddy
config/observability/prometheus/prometheus.yml
config/observability/prometheus/rules/vps.yml
scripts/chapter-08-configure.sh
scripts/glitchtip-secrets-ensure.sh
scripts/glitchtip-compose.sh
scripts/glitchtip-admin-ensure.sh
scripts/glitchtip-prometheus-token-ensure.sh
scripts/glitchtip-integrate-observability.sh
scripts/glitchtip-check.sh
scripts/glitchtip-send-test-event.sh
README.md
```

Secrets из `/opt/data/error-tracking/secrets` здесь появляться не должны.

Проверить diff whitespace:

```bash
git diff --check
```

Проверить, что Compose действительно содержит именно два services:

```bash
SERVICE_COUNT="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    config --services |
  wc -l |
  tr -d ' '
)"

[[ "$SERVICE_COUNT" == "2" ]] || {
  printf 'ERROR: expected 2 GlitchTip services, got %s\n' \
    "$SERVICE_COUNT" >&2
  exit 1
}

printf 'GlitchTip Compose contains exactly two services.\n'
```

---

## 34. Commit и push главы 08

Добавлять файлы явно, а не `git add -A`:

```bash
source "$HOME/config.env"

SITE_FILE="$OPS_ROOT/config/caddy/sites/$GLITCHTIP_HOST.caddy"

cd "$OPS_ROOT"

git add \
  README.md \
  compose/error-tracking/compose.yaml \
  compose/observability/compose.yaml \
  config/error-tracking/README.md \
  "$SITE_FILE" \
  config/observability/prometheus/prometheus.yml \
  config/observability/prometheus/rules/vps.yml \
  scripts/chapter-08-configure.sh \
  scripts/glitchtip-secrets-ensure.sh \
  scripts/glitchtip-compose.sh \
  scripts/glitchtip-admin-ensure.sh \
  scripts/glitchtip-prometheus-token-ensure.sh \
  scripts/glitchtip-integrate-observability.sh \
  scripts/glitchtip-check.sh \
  scripts/glitchtip-send-test-event.sh
```

Проверить staged files:

```bash
git diff --cached --name-status
```

Проверить staged whitespace:

```bash
git diff --cached --check
```

Финально проверить known-secret leakage **в staged content**:

```bash
STAGED_PATCH="$(mktemp)"
git diff --cached --binary > "$STAGED_PATCH"

for secret_file in \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"; do

  secret="$(<"$secret_file")"

  if grep -F -q -- "$secret" "$STAGED_PATCH"; then
    printf 'ERROR: secret value found in staged Git diff\n' >&2
    rm -f "$STAGED_PATCH"
    unset secret
    exit 1
  fi
done

rm -f "$STAGED_PATCH"
unset secret
printf 'Staged Git diff contains no known GlitchTip secret values.\n'
```

Перед commit ещё раз выполнить оба runtime checks:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
"$OPS_ROOT/scripts/glitchtip-check.sh"
```

Только после двух success:

```bash
git commit -m 'Add GlitchTip error tracking'
git push origin main
```

Проверить local/remote state:

```bash
git fetch --quiet origin main

LOCAL_SHA="$(git rev-parse main)"
REMOTE_SHA="$(git rev-parse origin/main)"

[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ after push\n' >&2
  exit 1
}

[[ -z "$(git status --porcelain)" ]] || {
  printf 'ERROR: Git working tree is not clean after push\n' >&2
  git status --short >&2
  exit 1
}

printf 'Chapter 08 Git state is clean and synchronized: %s\n' \
  "$LOCAL_SHA"
```

---

## 35. Что должно получиться после главы

После успешного выполнения:

```text
Internet
  |
  +--> :80/:443 Caddy
            |
            +--> errors.<domain> --> GlitchTip:8000
                                      |
                                      +--> PostgreSQL:5432

Prometheus --> GlitchTip /metrics
Blackbox   --> https://errors.<domain>/
Alloy      --> Docker logs --> Loki
Alertmanager --> Telegram availability alerts
```

На host:

```text
PUBLIC:
80/tcp
443/tcp
443/udp

PRIVATE / EXISTING:
SSH over Tailscale
Grafana over Tailscale Serve

NOT PUBLISHED:
GlitchTip 8000
PostgreSQL 5432
Prometheus 9090
Loki 3100
Alertmanager 9093
Alloy 12345
```

Persistent GlitchTip data:

```text
/opt/data/error-tracking/
├── postgres/
├── uploads/
└── secrets/
    ├── secret_key
    ├── postgres_password
    ├── admin_password
    ├── postgres.env
    └── glitchtip.env
```

Versioned configuration:

```text
/opt/ops/
├── compose/error-tracking/compose.yaml
├── compose/observability/compose.yaml
├── config/error-tracking/README.md
├── config/caddy/sites/errors.<domain>.caddy
├── config/observability/prometheus/prometheus.yml
├── config/observability/prometheus/rules/vps.yml
└── scripts/
    ├── chapter-08-configure.sh
    ├── glitchtip-secrets-ensure.sh
    ├── glitchtip-compose.sh
    ├── glitchtip-admin-ensure.sh
    ├── glitchtip-prometheus-token-ensure.sh
    ├── glitchtip-integrate-observability.sh
    ├── glitchtip-check.sh
    └── glitchtip-send-test-event.sh
```

---

## 36. Критерии завершения главы

Глава завершена только если одновременно выполняется всё ниже:

- [ ] `observability-check.sh` завершается `Observability check passed.`;
- [ ] `glitchtip-check.sh` завершается `GlitchTip check passed.`;
- [ ] PostgreSQL и GlitchTip имеют `healthy` state;
- [ ] нет `Restarting`, `Exited`, `Dead` containers в error-tracking stack;
- [ ] public `https://errors.<domain>/` открывается;
- [ ] HTTP перенаправляется на HTTPS;
- [ ] GlitchTip `/metrics` target в Prometheus — `up`;
- [ ] Blackbox GlitchTip target — `up`;
- [ ] `probe_success{job="blackbox-glitchtip"}` равно `1`;
- [ ] GlitchTip/PostgreSQL Docker logs видны в Loki;
- [ ] test Sentry-compatible event появился в GlitchTip Issues;
- [ ] self-registration отключена;
- [ ] organization creation ограничена superuser;
- [ ] Valkey не используется;
- [ ] GlitchTip structured logs и uptime отключены, потому что эти роли выполняют Loki/Blackbox;
- [ ] PostgreSQL находится только в `internal=true` Docker network;
- [ ] host ports `8000`/`5432` не опубликованы;
- [ ] images используют exact `@sha256` digest;
- [ ] secrets имеют mode `0640` и находятся вне Git;
- [ ] logical PostgreSQL dump успешно создаётся и читается `pg_restore`;
- [ ] persistent state переживает controlled restart;
- [ ] на host нет kernel OOM events текущего boot;
- [ ] Caddy config valid;
- [ ] Prometheus config/rules valid;
- [ ] Git working tree clean;
- [ ] `main` синхронизирован с `origin/main`.

---

## 37. Диагностика

### GlitchTip container не становится healthy

```bash
source "$HOME/config.env"

"$OPS_ROOT/scripts/glitchtip-compose.sh" ps

"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  logs --tail=240 postgres glitchtip
```

Проверить health status:

```bash
for service in postgres glitchtip; do
  id="$(
    "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q "$service"
  )"

  printf '\n## %s\n' "$service"
  docker inspect "$id" |
    jq '.[0].State'
done
```

Не отключайте healthcheck и не увеличивайте retries вслепую. Сначала исправьте фактическую ошибку.

### `permission denied` для PostgreSQL data

Проверить image UID/GID и host directory:

```bash
printf 'Expected PostgreSQL UID:GID: %s:%s\n' \
  "$POSTGRES_UID" "$POSTGRES_GID"

stat -c '%A %u:%g %n' \
  "$ERROR_TRACKING_DATA_ROOT/postgres"
```

Исправить owner из уже вычисленных image values:

```bash
sudo chown -R \
  "$POSTGRES_UID:$POSTGRES_GID" \
  "$ERROR_TRACKING_DATA_ROOT/postgres"

sudo chmod 0700 \
  "$ERROR_TRACKING_DATA_ROOT/postgres"
```

Затем:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  up -d --force-recreate postgres glitchtip
```

### `permission denied` для `/code/uploads`

```bash
printf 'Expected GlitchTip UID:GID: %s:%s\n' \
  "$GLITCHTIP_UID" "$GLITCHTIP_GID"

stat -c '%A %u:%g %n' \
  "$ERROR_TRACKING_DATA_ROOT/uploads"
```

Исправить:

```bash
sudo chown -R \
  "$GLITCHTIP_UID:$GLITCHTIP_GID" \
  "$ERROR_TRACKING_DATA_ROOT/uploads"

sudo chmod 0750 \
  "$ERROR_TRACKING_DATA_ROOT/uploads"

"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  up -d --force-recreate glitchtip
```

### PostgreSQL `password authentication failed`

Не меняйте `postgres_password` в одном файле вручную: password уже записан внутрь existing database cluster при первом init.

Сначала проверить metadata files, не выводя password:

```bash
for file in \
  postgres_password \
  postgres.env \
  glitchtip.env; do

  stat -c '%m %U:%G %s %n' \
    "$ERROR_TRACKING_SECRETS_ROOT/$file"
done
```

Если cluster уже инициализирован с другим password, не удаляйте `/opt/data/error-tracking/postgres` ради быстрого исправления. Сначала меняйте PostgreSQL role password через `ALTER ROLE` и синхронизируйте secret files; destructive reset допустим только когда точно нет нужных данных.

### GlitchTip отдаёт `400 Bad Request` через Caddy

Проверить documented production host/origin variables:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  python - <<'PY_PROXY_ENV'
import os

for key in (
    "GLITCHTIP_DOMAIN",
    "ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
):
    print(f"{key}={os.environ.get(key)!r}")
PY_PROXY_ENV
```

Ожидается один и тот же `errors.<domain>`/HTTPS origin.

Проверить Caddy route:

```bash
SITE_FILE="$OPS_ROOT/config/caddy/sites/$GLITCHTIP_HOST.caddy"
sed -n '1,160p' "$SITE_FILE"
```

Проверить internal connectivity из Caddy network:

```bash
CADDY_CONTAINER="$(
  docker ps \
    --filter "label=com.docker.compose.project=${CADDY_STACK}" \
    --filter 'label=com.docker.compose.service=caddy' \
    --format '{{.Names}}' |
  head -n 1
)"

docker exec "$CADDY_CONTAINER" \
  wget -qO- \
  --timeout=5 \
  "http://$GLITCHTIP_UPSTREAM/" \
  >/dev/null &&
printf 'Caddy can reach GlitchTip upstream.\n'
```

### HTTPS не открывается

Проверить DNS:

```bash
getent ahostsv4 "$GLITCHTIP_HOST"
```

Проверить Caddy:

```bash
cd "$OPS_ROOT/compose/edge"
docker compose ps
docker compose logs --tail=160 caddy
```

Проверить certificate handshake:

```bash
openssl s_client \
  -connect "$GLITCHTIP_HOST:443" \
  -servername "$GLITCHTIP_HOST" \
  -verify_return_error \
  </dev/null
```

Не открывайте host port `8000` как workaround. Публичный ingress должен оставаться только через Caddy.

### Prometheus target `glitchtip` down

Проверить, что GlitchTip и Prometheus разделяют observability network:

```bash
GLITCHTIP_ID="$(
  "$OPS_ROOT/scripts/glitchtip-compose.sh" ps -q glitchtip
)"
PROMETHEUS_ID="$(
  "$OPS_ROOT/scripts/observability-compose.sh" ps -q prometheus
)"

for id in "$GLITCHTIP_ID" "$PROMETHEUS_ID"; do
  docker inspect "$id" |
    jq -r '.[0].Name, (.[0].NetworkSettings.Networks | keys[])'
done
```

Проверить authenticated `/metrics` внутри GlitchTip. Secret не печатается:

```bash
(
  set -Eeuo pipefail

  TOKEN_FILE="$ERROR_TRACKING_SECRETS_ROOT/prometheus_token"
  [[ -s "$TOKEN_FILE" ]] || {
    printf 'ERROR: Prometheus token file is missing\n' >&2
    exit 1
  }

  GLITCHTIP_METRICS_TOKEN="$(<"$TOKEN_FILE")"
  export GLITCHTIP_METRICS_TOKEN

  "$OPS_ROOT/scripts/glitchtip-compose.sh" \
    exec -T \
    -e GLITCHTIP_METRICS_TOKEN \
    glitchtip \
    python - <<'PY_METRICS_DEBUG'
import http.client
import os
from urllib.parse import urlsplit

host = urlsplit(os.environ["GLITCHTIP_DOMAIN"]).hostname
token = os.environ["GLITCHTIP_METRICS_TOKEN"]

if not host:
    raise SystemExit("ERROR: GLITCHTIP_DOMAIN has no hostname")

conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
conn.request(
    "GET",
    "/metrics",
    headers={
        "Host": host,
        "X-Forwarded-Proto": "https",
        "Authorization": f"Bearer {token}",
    },
)
response = conn.getresponse()
body = response.read().decode("utf-8", errors="replace")
conn.close()

if response.status != 200:
    raise SystemExit(
        f"ERROR: authenticated /metrics returned {response.status}"
    )

samples = [
    line
    for line in body.splitlines()
    if line and not line.startswith("#")
]

if not samples:
    raise SystemExit("ERROR: /metrics returned no samples")

print(f"Authenticated GlitchTip /metrics works: {len(samples)} samples.")
PY_METRICS_DEBUG

  unset GLITCHTIP_METRICS_TOKEN
)
```
Проверить Prometheus target error:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:9090/api/v1/targets |
jq -r '
  .data.activeTargets[]
  | select(.labels.job == "glitchtip")
  | {health, lastError, scrapeUrl}
'
```

### Blackbox target down, но UI открывается

Проверить последние probe metrics через Prometheus:

```bash
for metric in \
  probe_success \
  probe_http_status_code \
  probe_ssl_earliest_cert_expiry; do

  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode \
      "query=${metric}{job=\"blackbox-glitchtip\"}" \
    http://127.0.0.1:9090/api/v1/query |
  jq -r \
    --arg metric "$metric" \
    '.data.result[]? | [$metric, .metric.instance, .value[1]] | @tsv'
done |
column -t -s $'\t'
```

Если `probe_success` равен `0`, получить debug из Prometheus/Blackbox logs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  logs --tail=160 blackbox-exporter prometheus
```

### Error-tracking logs отсутствуют в Loki

Сначала убедиться, что Alloy всё ещё работает после исправлений главы 07:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  ps socket-proxy alloy

"$OPS_ROOT/scripts/observability-compose.sh" \
  logs --since=5m alloy
```

Не должно быть Docker discovery `403 Forbidden`.

Проверить labels в Loki:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:3100/loki/api/v1/label/compose_project/values |
jq
```

Должен присутствовать `$ERROR_TRACKING_STACK`.

### Test event получил HTTP error

Проверить DSN metadata без public key:

```bash
python3 - <<'PY_DSN_DEBUG'
import os
from urllib.parse import urlsplit

parsed = urlsplit(os.environ["GLITCHTIP_TEST_DSN"])
print("scheme:", parsed.scheme)
print("host:", parsed.hostname)
print("project:", parsed.path.strip("/").split("/")[-1])
PY_DSN_DEBUG
```

Проверить GlitchTip logs:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  logs --since=5m glitchtip
```

Если DSN был удалён/пересоздан в UI, обновить `GLITCHTIP_TEST_DSN` в `$HOME/config.env` через шаг 20, а не hard-code в script.

### Event accepted, но не появился в UI

Подождать до минуты и проверить worker/application logs:

```bash
sleep 30

"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  logs --since=5m glitchtip
```

Проверить all-in-one setting:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T glitchtip \
  sh -eu -c 'test "$SERVER_ROLE" = all_in_one; test "$GLITCHTIP_EMBED_WORKER" = true'
```

Если container стабилен, database доступна, event ingest возвращает 2xx, но issue всё равно не появляется — не включайте Valkey вслепую. Сначала диагностируйте worker traceback из GlitchTip logs.

### `glitchtip-check.sh` говорит, что secret tracked в Git

```bash
git -C "$OPS_ROOT" ls-files |
grep -E \
  '(^|/)(admin_password|postgres_password|secret_key|postgres\.env|glitchtip\.env)$'
```

Удалить secret из Git index и history при необходимости. Простого добавления в `.gitignore` недостаточно, если secret уже был committed.

---

## 38. Что намеренно не делаем в этой главе

Не добавляем:

- Valkey/Redis — для текущего small-VPS all-in-one deployment он не обязателен;
- отдельный GlitchTip worker — уменьшает число containers и RAM overhead;
- public `8000`/`5432`;
- pgAdmin;
- shared PostgreSQL для пользовательских приложений;
- S3/cold storage;
- SMTP без реального provider credential;
- GlitchTip uptime monitoring — уже есть Blackbox;
- GlitchTip application log ingestion — уже есть Loki;
- MCP endpoint — не нужен production error tracking baseline;
- полный backup/offsite retention — это отдельная backup-глава;
- Tempo/OpenTelemetry collector — отдельное расширение после базового production stack.

---

## 39. Технические ориентиры главы

При подготовке главы используются текущие upstream требования GlitchTip 6.x:

- PostgreSQL `14+` обязателен;
- Valkey является optional и может быть отключён пустым `VALKEY_URL`;
- `SERVER_ROLE=all_in_one` explicitly selects all-in-one mode; `GLITCHTIP_EMBED_WORKER=true` must be lowercase for GlitchTip 6.2.2 `bin/start.sh` compatibility;
- `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS` должны быть ограничены в production;
- `ENABLE_USER_REGISTRATION`, `ENABLE_SOCIAL_APPS_USER_REGISTRATION` и `ENABLE_ORGANIZATION_CREATION` управляют registration policy;
- `ENABLE_OBSERVABILITY_API=True` включает Prometheus metrics;
- retention настраивается отдельными `GLITCHTIP_*_RETENTION_DAYS` variables;
- `GLITCHTIP_ENABLE_UPTIME`, `GLITCHTIP_ENABLE_LOGS`, `GLITCHTIP_ENABLE_MCP` и cold storage через DuckDB можно отключать;
- production transaction sampling для SDK рекомендуется начинать с низкого значения, например `0.01`;
- GlitchTip принимает Sentry-compatible SDK/envelope events по project DSN.

Версии в этой главе разрешаются по controlled tags, но в runtime Compose записываются **exact image digests**, чтобы повторный `docker compose pull` не менял production image незаметно.

---

## 40. Следующая глава

После GlitchTip следующий крупный production gap — управление versioned secrets.

Следующая глава:

```text
09 — SOPS + age: encrypted secrets in Git, safe decrypt workflow и rotation
```

После неё current plaintext runtime secrets останутся доступны сервисам только на VPS, а versioned source-of-truth сможет безопасно храниться в repository в encrypted form.
