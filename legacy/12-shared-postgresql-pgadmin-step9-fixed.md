# Глава 12. Shared PostgreSQL platform: отдельные базы проектов, pgAdmin и monitoring

Эта глава добавляет на VPS **общий PostgreSQL cluster для собственных application-проектов**.

После выполнения главы:

- на сервере работает один PostgreSQL 18 cluster как shared platform service;
- PostgreSQL не публикует `5432/tcp` на host и недоступен из Internet/Tailscale напрямую;
- каждый проект получает **отдельную database**, а не отдельную schema в общей database;
- каждый проект получает отдельные `runtime` и `migrator` PostgreSQL roles;
- runtime role не является owner database и не может выполнять migrations/DDL;
- migrator role используется только для migrations;
- `PUBLIC` privileges явно ужесточены;
- network authentication использует `SCRAM-SHA-256`;
- network login под PostgreSQL superuser `postgres` запрещён;
- `pg_stat_statements` включён для диагностики SQL;
- PostgreSQL настроен консервативно под VPS `2 vCPU / 4 GB RAM`, где уже работают Caddy, observability и GlitchTip;
- PostgreSQL, pgAdmin и postgres_exporter pinned на immutable image digests;
- pgAdmin доступен только через Tailscale Serve;
- pgAdmin не публикуется через Caddy и public DNS;
- postgres_exporter подключён к существующему Prometheus;
- Grafana получает отдельный PostgreSQL dashboard;
- Alertmanager получает alerts для exporter/down, ошибок exporter, большого количества connections и deadlocks;
- global database credentials и credentials каждого проекта хранятся в Git только через SOPS;
- plaintext application credentials materialize только в `/opt/apps/<app>/secrets/`;
- создаётся idempotent `database-project-create.sh`, который одной командой создаёт database, roles, grants, SOPS secret и runtime env files;
- создаётся smoke-test, который проверяет реальное разграничение прав через TCP;
- существующий PostgreSQL GlitchTip **не переносится** в shared platform cluster.

> Команды рассчитаны на Ubuntu 24.04 после успешно завершённой главы 09.
>
> Главы 10–11 с off-site backup и disaster recovery в текущем прохождении отложены. Shared PostgreSQL без проверенного off-site backup **ещё не является законченным production state**.
>
> В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, **не переходите к следующему номеру шага**, пока причина не устранена.
>
> Не публикуйте PostgreSQL `5432/tcp` через `ports:`, UFW, Caddy или Tailscale Serve.
>
> Не используйте PostgreSQL role `postgres` в приложениях, pgAdmin или exporter.

---

## 0. Архитектурное решение

Для single-VPS с несколькими собственными небольшими production-проектами используем:

```text
                           Internet
                              |
                              v
                            Caddy
                              |
                    application containers
                              |
                    Docker network: database
                              |
                              v
                    shared PostgreSQL cluster
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
     project_a DB        project_b DB        project_c DB
     project_a_*         project_b_*         project_c_*
        roles               roles               roles
```

Administrative path:

```text
admin laptop
    |
    | Tailscale
    v
server.tailnet.ts.net:8444
    |
    | Tailscale Serve -> 127.0.0.1:5050
    v
pgAdmin
    |
    | database Docker network
    v
PostgreSQL as platform_admin
```

Monitoring path:

```text
PostgreSQL
    |
    v
postgres_exporter
    |
    | observability network
    v
Prometheus -> Grafana
    |
    v
Alertmanager -> Telegram
```

### Почему один cluster — нормально

PostgreSQL изначально рассчитан на несколько databases внутри одного cluster.

Для unrelated projects правильная граница в текущем масштабе:

```text
1 VPS
  -> 1 PostgreSQL cluster
      -> 1 database per project
          -> 1 migrator role per project
          -> 1 runtime role per project
```

Не используем:

```text
1 database
  -> schema project_a
  -> schema project_b
  -> schema project_c
```

как основную изоляцию независимых проектов.

Отдельная database даёт более понятную границу:

- `CONNECT` privilege;
- ownership;
- migrations;
- default privileges;
- extensions;
- observability;
- lifecycle проекта.

### Когда проекту нужен отдельный PostgreSQL instance

Не помещать приложение в shared cluster, если ему требуется хотя бы одно из следующего:

- другая major-версия PostgreSQL;
- специальные/нестандартные extensions;
- высокая или непредсказуемая CPU/RAM/IO нагрузка;
- сотни/тысячи concurrent connections;
- независимое окно PostgreSQL upgrades/restarts;
- строгая security/compliance isolation;
- недоверенный application workload;
- независимый recovery/PITR lifecycle;
- отдельная HA/replication topology.

В таком случае отдельный PostgreSQL Compose stack или managed PostgreSQL — правильнее.

### Почему GlitchTip PostgreSQL не переносим

Уже существующий GlitchTip database остаётся внутри `error-tracking` stack.

Причины:

```text
GlitchTip DB = infrastructure-tool state
Application DBs = user-project state
```

У них разные:

- lifecycle;
- upgrade procedure;
- failure domain;
- restore procedure;
- ownership.

Автоматическая миграция GlitchTip в platform PostgreSQL не даёт достаточной пользы и увеличивает blast radius.

---

## 1. Выполнить preflight главы 12

Загрузить configuration:

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${APPS_ROOT:?APPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"
: "${TAILSCALE_DNS_NAME:?TAILSCALE_DNS_NAME is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
```

Создать временный preflight:

````bash
PREFLIGHT_SCRIPT="$(mktemp)"
chmod 0700 "$PREFLIGHT_SCRIPT"

cat > "$PREFLIGHT_SCRIPT" <<'EOF_CH12_PREFLIGHT'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT APPS_ROOT DATA_ROOT ADMIN_USER OPS_GROUP \
  OBSERVABILITY_NETWORK OBSERVABILITY_CONFIG_ROOT \
  OBSERVABILITY_STACK TAILSCALE_DNS_NAME BASE_DOMAIN \
  SOPS_CONFIG SOPS_AGE_KEY_FILE SOPS_SECRETS_ROOT; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s, not %s\n' "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}

for command in docker git jq openssl python3 sops tailscale curl; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

[[ -d "$OPS_ROOT/.git" ]] || {
  printf 'ERROR: %s is not a Git repository\n' "$OPS_ROOT" >&2
  exit 1
}

[[ -s "$SOPS_CONFIG" ]] || {
  printf 'ERROR: SOPS config is missing: %s\n' "$SOPS_CONFIG" >&2
  exit 1
}

[[ -s "$SOPS_AGE_KEY_FILE" ]] || {
  printf 'ERROR: age identity is missing: %s\n' "$SOPS_AGE_KEY_FILE" >&2
  exit 1
}

if [[ -n "$(git -C "$OPS_ROOT" status --porcelain)" ]]; then
  printf 'ERROR: %s working tree is not clean.\n' "$OPS_ROOT" >&2
  printf 'Commit or restore previous changes before Chapter 12.\n' >&2
  exit 1
fi

docker info >/dev/null

docker network inspect "$OBSERVABILITY_NETWORK" >/dev/null

for stack_service in \
  observability-prometheus-1 \
  observability-grafana-1 \
  observability-alertmanager-1 \
  error-tracking-glitchtip-1; do
  docker inspect "$stack_service" >/dev/null 2>&1 || {
    printf 'ERROR: expected container not found: %s\n' "$stack_service" >&2
    exit 1
  }
done

if sudo ss -lntH '( sport = :5432 )' | grep -q .; then
  printf 'ERROR: host TCP port 5432 is already listening.\n' >&2
  sudo ss -lntp '( sport = :5432 )' >&2 || true
  exit 1
fi

if sudo ss -lntH '( sport = :5050 )' | grep -q .; then
  printf 'ERROR: host TCP port 5050 is already listening.\n' >&2
  sudo ss -lntp '( sport = :5050 )' >&2 || true
  exit 1
fi

printf 'Chapter 12 preflight passed.\n'
EOF_CH12_PREFLIGHT

"$PREFLIGHT_SCRIPT"
rm -f "$PREFLIGHT_SCRIPT"
unset PREFLIGHT_SCRIPT
````

---

## 2. Зафиксировать production versions и paths

В этой главе используются:

```text
PostgreSQL       18.4
pgAdmin          9.17
postgres_exporter 0.20.1
```

Mutable tags используются только как controlled input при установке.

В `config.env` сохраняются уже **immutable digest refs**.

Создать configure script:

````bash
cat > "$OPS_ROOT/scripts/chapter-12-configure.sh" <<'EOF_CH12_CONFIGURE'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"
: "${TAILSCALE_DNS_NAME:?TAILSCALE_DNS_NAME is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"
: "${SOPS_SECRETS_ROOT:?SOPS_SECRETS_ROOT is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in docker git install python3; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

PLATFORM_DATABASE_STACK="database"
PLATFORM_DATABASE_ROOT="$OPS_ROOT/compose/database"
PLATFORM_DATABASE_CONFIG_ROOT="$OPS_ROOT/config/database"
PLATFORM_DATABASE_DATA_ROOT="$DATA_ROOT/database"
PLATFORM_DATABASE_SECRETS_ROOT="$DATA_ROOT/database/secrets"
PLATFORM_DATABASE_PROJECTS_ROOT="$OPS_ROOT/config/database/projects"
PLATFORM_DATABASE_NETWORK="database"
PLATFORM_DATABASE_SUBNET=""

# The database network is created in step 5. If this configure script is
# re-run later, preserve the subnet already allocated by Docker.
if docker network inspect "$PLATFORM_DATABASE_NETWORK" >/dev/null 2>&1; then
  PLATFORM_DATABASE_SUBNET="$(
    docker network inspect "$PLATFORM_DATABASE_NETWORK" |
    jq -er '.[0].IPAM.Config[]? | select(.Subnet != null and (.Subnet | contains(":") | not)) | .Subnet' |
    head -n 1
  )"
fi

PLATFORM_POSTGRES_TAG="postgres:18.4-alpine"
PLATFORM_PGADMIN_TAG="dpage/pgadmin4:9.17"
PLATFORM_POSTGRES_EXPORTER_TAG="quay.io/prometheuscommunity/postgres-exporter:v0.20.1"

PLATFORM_POSTGRES_MEMORY_LIMIT="1024m"
PLATFORM_POSTGRES_CPU_LIMIT="1.00"
PLATFORM_PGADMIN_MEMORY_LIMIT="256m"
PLATFORM_PGADMIN_CPU_LIMIT="0.25"
PLATFORM_POSTGRES_EXPORTER_MEMORY_LIMIT="96m"
PLATFORM_POSTGRES_EXPORTER_CPU_LIMIT="0.15"

PLATFORM_POSTGRES_MAX_CONNECTIONS="60"
PLATFORM_POSTGRES_SHARED_BUFFERS="256MB"
PLATFORM_POSTGRES_EFFECTIVE_CACHE_SIZE="512MB"
PLATFORM_POSTGRES_WORK_MEM="4MB"
PLATFORM_POSTGRES_MAINTENANCE_WORK_MEM="64MB"
PLATFORM_POSTGRES_AUTOVACUUM_WORK_MEM="32MB"

PLATFORM_DB_RUNTIME_CONNECTION_LIMIT="8"
PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT="2"

PGADMIN_LOCAL_PORT="5050"
PGADMIN_TAILSCALE_PORT="8444"
PGADMIN_URL="https://${TAILSCALE_DNS_NAME}:${PGADMIN_TAILSCALE_PORT}"
PGADMIN_ADMIN_EMAIL="${ADMIN_USER}@${BASE_DOMAIN}"

SOPS_DATABASE_FILE="$SOPS_SECRETS_ROOT/database.enc.yaml"
SOPS_DATABASE_PROJECTS_ROOT="$SOPS_SECRETS_ROOT/database"

resolve_digest() {
  local tag="$1"
  local digest

  printf 'Pulling %s ...\n' "$tag" >&2
  docker pull "$tag" >/dev/null

  digest="$(
    docker image inspect "$tag" \
      --format '{{range .RepoDigests}}{{println .}}{{end}}' |
    head -n 1
  )"

  [[ "$digest" =~ @sha256:[a-f0-9]{64}$ ]] || {
    printf 'ERROR: cannot resolve immutable digest for %s\n' "$tag" >&2
    exit 1
  }

  printf '%s\n' "$digest"
}

PLATFORM_POSTGRES_IMAGE="$(resolve_digest "$PLATFORM_POSTGRES_TAG")"
PLATFORM_PGADMIN_IMAGE="$(resolve_digest "$PLATFORM_PGADMIN_TAG")"
PLATFORM_POSTGRES_EXPORTER_IMAGE="$(resolve_digest "$PLATFORM_POSTGRES_EXPORTER_TAG")"

PLATFORM_POSTGRES_UID="$(
  docker run --rm \
    --entrypoint sh \
    "$PLATFORM_POSTGRES_IMAGE" \
    -c 'id -u postgres'
)"
PLATFORM_POSTGRES_GID="$(
  docker run --rm \
    --entrypoint sh \
    "$PLATFORM_POSTGRES_IMAGE" \
    -c 'id -g postgres'
)"

[[ "$PLATFORM_POSTGRES_UID" =~ ^[0-9]+$ ]] || {
  printf 'ERROR: invalid PostgreSQL uid\n' >&2
  exit 1
}
[[ "$PLATFORM_POSTGRES_GID" =~ ^[0-9]+$ ]] || {
  printf 'ERROR: invalid PostgreSQL gid\n' >&2
  exit 1
}

# pgAdmin official image contract.
PLATFORM_PGADMIN_UID="5050"
PLATFORM_PGADMIN_GID="5050"

# postgres_exporter official image contract.
PLATFORM_POSTGRES_EXPORTER_UID="65534"
PLATFORM_POSTGRES_EXPORTER_GID="65534"

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$PLATFORM_DATABASE_ROOT" \
  "$PLATFORM_DATABASE_CONFIG_ROOT" \
  "$PLATFORM_DATABASE_CONFIG_ROOT/postgres" \
  "$PLATFORM_DATABASE_CONFIG_ROOT/pgadmin" \
  "$PLATFORM_DATABASE_PROJECTS_ROOT" \
  "$SOPS_DATABASE_PROJECTS_ROOT"

sudo install -d -o root -g "$OPS_GROUP" -m 2750 \
  "$PLATFORM_DATABASE_DATA_ROOT" \
  "$PLATFORM_DATABASE_SECRETS_ROOT"

sudo install -d \
  -o "$PLATFORM_POSTGRES_UID" \
  -g "$PLATFORM_POSTGRES_GID" \
  -m 0700 \
  "$PLATFORM_DATABASE_DATA_ROOT/postgres"

sudo install -d \
  -o "$PLATFORM_PGADMIN_UID" \
  -g "$PLATFORM_PGADMIN_GID" \
  -m 0700 \
  "$PLATFORM_DATABASE_DATA_ROOT/pgadmin"

CONFIG_BLOCK="$(cat <<EOF_CONFIG_BLOCK
# BEGIN VPS GUIDE CHAPTER 12
export PLATFORM_DATABASE_STACK=${PLATFORM_DATABASE_STACK}
export PLATFORM_DATABASE_ROOT=${PLATFORM_DATABASE_ROOT}
export PLATFORM_DATABASE_CONFIG_ROOT=${PLATFORM_DATABASE_CONFIG_ROOT}
export PLATFORM_DATABASE_DATA_ROOT=${PLATFORM_DATABASE_DATA_ROOT}
export PLATFORM_DATABASE_SECRETS_ROOT=${PLATFORM_DATABASE_SECRETS_ROOT}
export PLATFORM_DATABASE_PROJECTS_ROOT=${PLATFORM_DATABASE_PROJECTS_ROOT}
export PLATFORM_DATABASE_NETWORK=${PLATFORM_DATABASE_NETWORK}
export PLATFORM_DATABASE_SUBNET=${PLATFORM_DATABASE_SUBNET}
export PLATFORM_POSTGRES_TAG=${PLATFORM_POSTGRES_TAG}
export PLATFORM_PGADMIN_TAG=${PLATFORM_PGADMIN_TAG}
export PLATFORM_POSTGRES_EXPORTER_TAG=${PLATFORM_POSTGRES_EXPORTER_TAG}
export PLATFORM_POSTGRES_IMAGE=${PLATFORM_POSTGRES_IMAGE}
export PLATFORM_PGADMIN_IMAGE=${PLATFORM_PGADMIN_IMAGE}
export PLATFORM_POSTGRES_EXPORTER_IMAGE=${PLATFORM_POSTGRES_EXPORTER_IMAGE}
export PLATFORM_POSTGRES_UID=${PLATFORM_POSTGRES_UID}
export PLATFORM_POSTGRES_GID=${PLATFORM_POSTGRES_GID}
export PLATFORM_PGADMIN_UID=${PLATFORM_PGADMIN_UID}
export PLATFORM_PGADMIN_GID=${PLATFORM_PGADMIN_GID}
export PLATFORM_POSTGRES_EXPORTER_UID=${PLATFORM_POSTGRES_EXPORTER_UID}
export PLATFORM_POSTGRES_EXPORTER_GID=${PLATFORM_POSTGRES_EXPORTER_GID}
export PLATFORM_POSTGRES_MEMORY_LIMIT=${PLATFORM_POSTGRES_MEMORY_LIMIT}
export PLATFORM_POSTGRES_CPU_LIMIT=${PLATFORM_POSTGRES_CPU_LIMIT}
export PLATFORM_PGADMIN_MEMORY_LIMIT=${PLATFORM_PGADMIN_MEMORY_LIMIT}
export PLATFORM_PGADMIN_CPU_LIMIT=${PLATFORM_PGADMIN_CPU_LIMIT}
export PLATFORM_POSTGRES_EXPORTER_MEMORY_LIMIT=${PLATFORM_POSTGRES_EXPORTER_MEMORY_LIMIT}
export PLATFORM_POSTGRES_EXPORTER_CPU_LIMIT=${PLATFORM_POSTGRES_EXPORTER_CPU_LIMIT}
export PLATFORM_POSTGRES_MAX_CONNECTIONS=${PLATFORM_POSTGRES_MAX_CONNECTIONS}
export PLATFORM_POSTGRES_SHARED_BUFFERS=${PLATFORM_POSTGRES_SHARED_BUFFERS}
export PLATFORM_POSTGRES_EFFECTIVE_CACHE_SIZE=${PLATFORM_POSTGRES_EFFECTIVE_CACHE_SIZE}
export PLATFORM_POSTGRES_WORK_MEM=${PLATFORM_POSTGRES_WORK_MEM}
export PLATFORM_POSTGRES_MAINTENANCE_WORK_MEM=${PLATFORM_POSTGRES_MAINTENANCE_WORK_MEM}
export PLATFORM_POSTGRES_AUTOVACUUM_WORK_MEM=${PLATFORM_POSTGRES_AUTOVACUUM_WORK_MEM}
export PLATFORM_DB_RUNTIME_CONNECTION_LIMIT=${PLATFORM_DB_RUNTIME_CONNECTION_LIMIT}
export PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT=${PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT}
export PGADMIN_LOCAL_PORT=${PGADMIN_LOCAL_PORT}
export PGADMIN_TAILSCALE_PORT=${PGADMIN_TAILSCALE_PORT}
export PGADMIN_URL=${PGADMIN_URL}
export PGADMIN_ADMIN_EMAIL=${PGADMIN_ADMIN_EMAIL}
export SOPS_DATABASE_FILE=${SOPS_DATABASE_FILE}
export SOPS_DATABASE_PROJECTS_ROOT=${SOPS_DATABASE_PROJECTS_ROOT}
# END VPS GUIDE CHAPTER 12
EOF_CONFIG_BLOCK
)"

TMP_CONFIG="$(mktemp)"
chmod 0600 "$TMP_CONFIG"

python3 - "$VPS_GUIDE_CONFIG" "$TMP_CONFIG" "$CONFIG_BLOCK" <<'PY_CONFIG'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
block = sys.argv[3]
begin = "# BEGIN VPS GUIDE CHAPTER 12"
end = "# END VPS GUIDE CHAPTER 12"

lines = source.read_text(encoding="utf-8").splitlines()
out = []
in_block = False

for line in lines:
    if line.strip() == begin:
        in_block = True
        continue
    if in_block:
        if line.strip() == end:
            in_block = False
        continue
    out.append(line)

while out and not out[-1].strip():
    out.pop()

content = "\n".join(out).rstrip()
if content:
    content += "\n\n"
content += block.rstrip() + "\n"
target.write_text(content, encoding="utf-8")
PY_CONFIG

mv -f "$TMP_CONFIG" "$VPS_GUIDE_CONFIG"
chmod 0600 "$VPS_GUIDE_CONFIG"

printf 'Chapter 12 configuration prepared.\n'
printf 'PostgreSQL: %s\n' "$PLATFORM_POSTGRES_IMAGE"
printf 'pgAdmin: %s\n' "$PLATFORM_PGADMIN_IMAGE"
printf 'postgres_exporter: %s\n' "$PLATFORM_POSTGRES_EXPORTER_IMAGE"
printf 'PostgreSQL container uid:gid = %s:%s\n' \
  "$PLATFORM_POSTGRES_UID" "$PLATFORM_POSTGRES_GID"
EOF_CH12_CONFIGURE

chmod 0750 "$OPS_ROOT/scripts/chapter-12-configure.sh"
"$OPS_ROOT/scripts/chapter-12-configure.sh"
````

Перезагрузить environment:

```bash
source "$HOME/config.env"
```

Проверить только immutable image contract:

```bash
for image in \
  "$PLATFORM_POSTGRES_IMAGE" \
  "$PLATFORM_PGADMIN_IMAGE" \
  "$PLATFORM_POSTGRES_EXPORTER_IMAGE"; do
  [[ "$image" =~ @sha256:[a-f0-9]{64}$ ]] || exit 1
done

printf 'Database stack images are immutable.\n'
```

---

## 3. Создать SOPS source-of-truth database credentials

Global secret содержит только credentials platform services:

```text
postgres_password
platform_admin_password
pgadmin_password
exporter_password
```

Application credentials здесь **не хранятся**.

`SOPS_CONFIG` передаётся SOPS через environment. Это намеренно: `--config` является global option SOPS и не должен передаваться после subcommand `encrypt`.

Они будут создаваться отдельно:

```text
/opt/ops/secrets/database/<app>.enc.yaml
```

Создать script:

````bash
cat > "$OPS_ROOT/scripts/database-secrets-init.sh" <<'EOF_DB_SECRETS_INIT'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${SOPS_DATABASE_FILE:?SOPS_DATABASE_FILE is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

export SOPS_AGE_KEY_FILE SOPS_CONFIG

if [[ -s "$SOPS_DATABASE_FILE" ]]; then
  tmp_check="$(mktemp)"
  trap 'rm -f "${tmp_check:-}"' EXIT
  chmod 0600 "$tmp_check"

  sops decrypt --output-type json "$SOPS_DATABASE_FILE" > "$tmp_check"

  jq -e '
    (.postgres_password | type == "string" and length >= 32) and
    (.platform_admin_password | type == "string" and length >= 32) and
    (.pgadmin_password | type == "string" and length >= 32) and
    (.exporter_password | type == "string" and length >= 32)
  ' "$tmp_check" >/dev/null || {
    printf 'ERROR: existing database SOPS file has unexpected structure.\n' >&2
    exit 1
  }

  printf 'Database encrypted source already exists and is valid.\n'
  exit 0
fi

plain="$(mktemp)"
encrypted="$(mktemp "${SOPS_DATABASE_FILE}.tmp.XXXXXX")"
trap 'rm -f "${plain:-}" "${encrypted:-}"' EXIT
chmod 0600 "$plain" "$encrypted"

python3 - "$plain" <<'PY_SECRET'
from pathlib import Path
import json
import secrets
import sys

# Hex keeps generated passwords URI-safe for PostgreSQL connection strings.
def password() -> str:
    return secrets.token_hex(32)

payload = {
    "postgres_password": password(),
    "platform_admin_password": password(),
    "pgadmin_password": password(),
    "exporter_password": password(),
}

Path(sys.argv[1]).write_text(
    json.dumps(payload, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY_SECRET

SOPS_CONFIG="$SOPS_CONFIG" sops encrypt \
  --filename-override "$SOPS_DATABASE_FILE" \
  --input-type json \
  --output-type yaml \
  "$plain" > "$encrypted"

sops decrypt --output-type json "$encrypted" |
jq -e '
  (.postgres_password | length >= 32) and
  (.platform_admin_password | length >= 32) and
  (.pgadmin_password | length >= 32) and
  (.exporter_password | length >= 32)
' >/dev/null

mv -f "$encrypted" "$SOPS_DATABASE_FILE"
chmod 0644 "$SOPS_DATABASE_FILE"
chown "$ADMIN_USER:$OPS_GROUP" "$SOPS_DATABASE_FILE"

printf 'Created encrypted database source: %s\n' "$SOPS_DATABASE_FILE"
EOF_DB_SECRETS_INIT

chmod 0750 "$OPS_ROOT/scripts/database-secrets-init.sh"
"$OPS_ROOT/scripts/database-secrets-init.sh"
````

### Добавить database source в Chapter 09 secret policy

Сделать `database.enc.yaml` обязательным tracked encrypted source:

````bash
python3 - "$OPS_ROOT/scripts/secret-policy.py" <<'PY_SECRET_POLICY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

needle = '    "secrets/registry.enc.yaml",\n'
addition = '    "secrets/database.enc.yaml",\n'

if addition not in text:
    if needle not in text:
        raise SystemExit("ERROR: expected Chapter 09 required_paths block was not found")
    text = text.replace(needle, needle + addition, 1)

path.write_text(text, encoding="utf-8")
PY_SECRET_POLICY

chmod 0750 "$OPS_ROOT/scripts/secret-policy.py"
````

---

## 4. Materialize только runtime secrets

Создать materializer:

````bash
cat > "$OPS_ROOT/scripts/database-secrets-apply.sh" <<'EOF_DB_SECRETS_APPLY'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  SOPS_DATABASE_FILE SOPS_AGE_KEY_FILE PLATFORM_DATABASE_SECRETS_ROOT \
  PLATFORM_POSTGRES_UID PLATFORM_POSTGRES_GID \
  PLATFORM_PGADMIN_UID PLATFORM_PGADMIN_GID \
  PLATFORM_POSTGRES_EXPORTER_UID PLATFORM_POSTGRES_EXPORTER_GID; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ -s "$SOPS_DATABASE_FILE" ]] || {
  printf 'ERROR: encrypted database source is missing\n' >&2
  exit 1
}

export SOPS_AGE_KEY_FILE

plain="$(mktemp)"
value_file="$(mktemp)"
trap 'rm -f "$plain" "$value_file"' EXIT
chmod 0600 "$plain" "$value_file"

sops decrypt --output-type json "$SOPS_DATABASE_FILE" > "$plain"

install_secret() {
  local key="$1"
  local filename="$2"
  local uid="$3"
  local gid="$4"

  jq -er --arg key "$key" '.[$key]' "$plain" > "$value_file"
  printf '\n' >> "$value_file"

  sudo install \
    -o "$uid" \
    -g "$gid" \
    -m 0400 \
    "$value_file" \
    "$PLATFORM_DATABASE_SECRETS_ROOT/$filename"

  : > "$value_file"
  chmod 0600 "$value_file"
}

# The official PostgreSQL entrypoint starts as root, reads POSTGRES_PASSWORD_FILE,
# prepares PGDATA, then drops privileges to the postgres user. Keep the bootstrap
# password root-only on the host; it is never exposed as a Compose environment value.
install_secret \
  postgres_password \
  postgres_password \
  0 \
  0

install_secret \
  pgadmin_password \
  pgadmin_password \
  "$PLATFORM_PGADMIN_UID" \
  "$PLATFORM_PGADMIN_GID"

install_secret \
  exporter_password \
  exporter_password \
  "$PLATFORM_POSTGRES_EXPORTER_UID" \
  "$PLATFORM_POSTGRES_EXPORTER_GID"

printf 'Database runtime secrets materialized.\n'
EOF_DB_SECRETS_APPLY

chmod 0750 "$OPS_ROOT/scripts/database-secrets-apply.sh"
"$OPS_ROOT/scripts/database-secrets-apply.sh"
````

`platform_admin_password` намеренно **не** материализуется как постоянный plaintext file.

Он нужен только:

- PostgreSQL bootstrap/rotation;
- login в pgAdmin server connection.

---

## 5. Создать isolated Docker network

Database network создаётся как `internal` user-defined bridge.

Subnet **не задаём вручную**. Docker Engine сам выбирает свободный non-overlapping IPv4 subnet из своих address pools. После создания helper считывает фактический subnet и сохраняет его в Chapter 12 block файла `config.env`.

Это исключает конфликт с уже существующими Compose networks и сохраняет точный subnet для `pg_hba.conf`.

Создать helper:

````bash
cat > "$OPS_ROOT/scripts/database-network-ensure.sh" <<'EOF_DB_NETWORK'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${PLATFORM_DATABASE_NETWORK:?PLATFORM_DATABASE_NETWORK is not set}"

for command in docker python3; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

docker info >/dev/null

if docker network inspect "$PLATFORM_DATABASE_NETWORK" >/dev/null 2>&1; then
  driver="$(docker network inspect "$PLATFORM_DATABASE_NETWORK" --format '{{.Driver}}')"
  internal="$(docker network inspect "$PLATFORM_DATABASE_NETWORK" --format '{{.Internal}}')"

  [[ "$driver" == "bridge" ]] || {
    printf 'ERROR: existing network %s uses driver %s, expected bridge.\n' \
      "$PLATFORM_DATABASE_NETWORK" "$driver" >&2
    exit 1
  }

  [[ "$internal" == "true" ]] || {
    printf 'ERROR: existing network %s is not internal.\n' \
      "$PLATFORM_DATABASE_NETWORK" >&2
    exit 1
  }
else
  # Do not hard-code --subnet. Docker allocates a non-overlapping subnet from
  # its configured default address pools.
  docker network create \
    --driver bridge \
    --internal \
    "$PLATFORM_DATABASE_NETWORK" >/dev/null
fi

PLATFORM_DATABASE_SUBNET="$(
  docker network inspect "$PLATFORM_DATABASE_NETWORK" |
  python3 -c '
import ipaddress
import json
import sys

network = json.load(sys.stdin)[0]
subnets = []
for item in network.get("IPAM", {}).get("Config", []) or []:
    value = item.get("Subnet")
    if not value:
        continue
    try:
        parsed = ipaddress.ip_network(value, strict=False)
    except ValueError:
        continue
    if parsed.version == 4:
        subnets.append(str(parsed))

if len(subnets) != 1:
    raise SystemExit(
        f"ERROR: expected exactly one IPv4 subnet for database network, got: {subnets}"
    )

print(subnets[0])
'
)"

[[ -n "$PLATFORM_DATABASE_SUBNET" ]] || {
  printf 'ERROR: Docker did not allocate an IPv4 subnet.\n' >&2
  exit 1
}

TMP_CONFIG="$(mktemp)"
trap 'rm -f "$TMP_CONFIG"' EXIT
chmod 0600 "$TMP_CONFIG"

python3 - \
  "$VPS_GUIDE_CONFIG" \
  "$TMP_CONFIG" \
  "$PLATFORM_DATABASE_SUBNET" <<'PY_UPDATE_CONFIG'
from pathlib import Path
import ipaddress
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
subnet = str(ipaddress.ip_network(sys.argv[3], strict=False))

begin = "# BEGIN VPS GUIDE CHAPTER 12"
end = "# END VPS GUIDE CHAPTER 12"
prefix = "export PLATFORM_DATABASE_SUBNET="

lines = source.read_text(encoding="utf-8").splitlines()
in_block = False
updated = False
out = []

for line in lines:
    stripped = line.strip()

    if stripped == begin:
        in_block = True
        out.append(line)
        continue

    if stripped == end:
        if not updated:
            raise SystemExit(
                "ERROR: PLATFORM_DATABASE_SUBNET was not found in Chapter 12 config block"
            )
        in_block = False
        out.append(line)
        continue

    if in_block and line.startswith(prefix):
        out.append(f"{prefix}{subnet}")
        updated = True
        continue

    out.append(line)

if in_block:
    raise SystemExit("ERROR: unterminated Chapter 12 config block")
if not updated:
    raise SystemExit("ERROR: Chapter 12 config block was not found")

target.write_text("\n".join(out) + "\n", encoding="utf-8")
PY_UPDATE_CONFIG

mv -f "$TMP_CONFIG" "$VPS_GUIDE_CONFIG"
chmod 0600 "$VPS_GUIDE_CONFIG"
trap - EXIT

printf 'Database network ready: %s %s (internal)\n' \
  "$PLATFORM_DATABASE_NETWORK" "$PLATFORM_DATABASE_SUBNET"
EOF_DB_NETWORK

chmod 0750 "$OPS_ROOT/scripts/database-network-ensure.sh"
"$OPS_ROOT/scripts/database-network-ensure.sh"

# Reload the subnet persisted by the helper for all following steps.
source "$HOME/config.env"
: "${PLATFORM_DATABASE_SUBNET:?PLATFORM_DATABASE_SUBNET was not persisted}"
````

---

## 6. Создать PostgreSQL configuration

### `postgresql.conf`

Настройки ниже являются стартовым профилем именно для текущего shared VPS:

```text
RAM total:               4 GB
PostgreSQL mem_limit:    1 GB
shared_buffers:          256 MB
work_mem:                4 MB per operation
max_connections:         60
```

`work_mem` намеренно не увеличивается агрессивно: один query может использовать несколько sort/hash operations, а несколько connections делают это одновременно.

Создать config:

````bash
cat > "$PLATFORM_DATABASE_CONFIG_ROOT/postgres/postgresql.conf" <<EOF_POSTGRES_CONF
listen_addresses = '*'
port = 5432

max_connections = ${PLATFORM_POSTGRES_MAX_CONNECTIONS}
superuser_reserved_connections = 3

shared_buffers = '${PLATFORM_POSTGRES_SHARED_BUFFERS}'
effective_cache_size = '${PLATFORM_POSTGRES_EFFECTIVE_CACHE_SIZE}'
work_mem = '${PLATFORM_POSTGRES_WORK_MEM}'
maintenance_work_mem = '${PLATFORM_POSTGRES_MAINTENANCE_WORK_MEM}'
autovacuum_work_mem = '${PLATFORM_POSTGRES_AUTOVACUUM_WORK_MEM}'

huge_pages = try

password_encryption = 'scram-sha-256'

wal_compression = on
checkpoint_completion_target = 0.9
max_wal_size = '1GB'
min_wal_size = '256MB'

shared_preload_libraries = 'pg_stat_statements'
compute_query_id = auto
pg_stat_statements.max = 5000
pg_stat_statements.track = top
pg_stat_statements.track_utility = on
pg_stat_statements.track_planning = off

track_io_timing = on

# 2 vCPU mixed-use host: avoid one analytical query spawning several workers.
max_parallel_workers_per_gather = 1
max_parallel_maintenance_workers = 1

log_lock_waits = on
deadlock_timeout = '1s'
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%h '
log_statement = 'none'

timezone = 'UTC'
log_timezone = 'UTC'
EOF_POSTGRES_CONF

chmod 0644 "$PLATFORM_DATABASE_CONFIG_ROOT/postgres/postgresql.conf"
````

### `pg_hba.conf`

Network superuser login запрещаем **до** общего allow-rule.

Создать HBA:

````bash
cat > "$PLATFORM_DATABASE_CONFIG_ROOT/postgres/pg_hba.conf" <<EOF_PG_HBA
# TYPE  DATABASE  USER       ADDRESS                       METHOD

# Administrative access from inside the PostgreSQL container only.
local   all       postgres                                 peer

# Other local socket users still need SCRAM.
local   all       all                                      scram-sha-256

# Never allow the PostgreSQL superuser over the Docker network.
host    all       postgres   ${PLATFORM_DATABASE_SUBNET}   reject

# Application / pgAdmin / exporter traffic.
host    all       all        ${PLATFORM_DATABASE_SUBNET}   scram-sha-256

# Explicit deny outside the dedicated database network.
host    all       all        0.0.0.0/0                     reject
host    all       all        ::0/0                          reject
EOF_PG_HBA

chmod 0644 "$PLATFORM_DATABASE_CONFIG_ROOT/postgres/pg_hba.conf"
````

---

## 7. Создать declarative pgAdmin server definition

pgAdmin будет знать только один PostgreSQL server:

```text
Platform PostgreSQL
```

Все project databases будут видны внутри него согласно PostgreSQL privileges.

Пароль в `servers.json` не хранится.

```bash
cat > "$PLATFORM_DATABASE_CONFIG_ROOT/pgadmin/servers.json" <<'EOF_PGADMIN_SERVERS'
{
  "Servers": {
    "1": {
      "Name": "Platform PostgreSQL",
      "Group": "Production",
      "Host": "platform-postgres",
      "Port": 5432,
      "MaintenanceDB": "postgres",
      "Username": "platform_admin",
      "SSLMode": "disable"
    }
  }
}
EOF_PGADMIN_SERVERS

chmod 0644 "$PLATFORM_DATABASE_CONFIG_ROOT/pgadmin/servers.json"
jq empty "$PLATFORM_DATABASE_CONFIG_ROOT/pgadmin/servers.json"
```

`SSLMode=disable` здесь относится только к traffic внутри private Docker bridge на **том же VPS**.

PostgreSQL password authentication при этом всё равно использует SCRAM-SHA-256.

Не создаём внутренний self-signed TLS PKI только ради loopback/same-host Docker traffic: это добавило бы certificate lifecycle без реальной защиты от root-level host compromise.

---

## 8. Создать Database Compose stack

Создать Compose:

> Для `postgres` намеренно **не** задаём `user:` и не делаем `cap_drop: ALL`. Официальный Docker entrypoint PostgreSQL стартует от root, читает `POSTGRES_PASSWORD_FILE`, подготавливает права `PGDATA`, затем сам выполняет privilege drop до системного пользователя `postgres`. PostgreSQL server после bootstrap работает не от root.

````bash
cat > "$PLATFORM_DATABASE_ROOT/compose.yml" <<'EOF_DATABASE_COMPOSE'
services:
  postgres:
    image: ${PLATFORM_POSTGRES_IMAGE:?PLATFORM_POSTGRES_IMAGE is not set}
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_DB: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      POSTGRES_INITDB_ARGS: --auth-local=peer --auth-host=scram-sha-256 --data-checksums --encoding=UTF8
      PGDATA: /var/lib/postgresql/18/docker
    command:
      - postgres
      - -c
      - config_file=/etc/postgresql/postgresql.conf
      - -c
      - hba_file=/etc/postgresql/pg_hba.conf
    volumes:
      - ${PLATFORM_DATABASE_DATA_ROOT:?PLATFORM_DATABASE_DATA_ROOT is not set}/postgres:/var/lib/postgresql
      - ${PLATFORM_DATABASE_CONFIG_ROOT:?PLATFORM_DATABASE_CONFIG_ROOT is not set}/postgres/postgresql.conf:/etc/postgresql/postgresql.conf:ro
      - ${PLATFORM_DATABASE_CONFIG_ROOT:?PLATFORM_DATABASE_CONFIG_ROOT is not set}/postgres/pg_hba.conf:/etc/postgresql/pg_hba.conf:ro
      - ${PLATFORM_DATABASE_SECRETS_ROOT:?PLATFORM_DATABASE_SECRETS_ROOT is not set}/postgres_password:/run/secrets/postgres_password:ro
    networks:
      database:
        aliases:
          - platform-postgres
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U postgres -d postgres -h /var/run/postgresql
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
    shm_size: 256m
    security_opt:
      - no-new-privileges:true
    pids_limit: 256
    mem_limit: ${PLATFORM_POSTGRES_MEMORY_LIMIT:?PLATFORM_POSTGRES_MEMORY_LIMIT is not set}
    cpus: "${PLATFORM_POSTGRES_CPU_LIMIT:?PLATFORM_POSTGRES_CPU_LIMIT is not set}"
    stop_grace_period: 90s

  pgadmin:
    image: ${PLATFORM_PGADMIN_IMAGE:?PLATFORM_PGADMIN_IMAGE is not set}
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL: ${PGADMIN_ADMIN_EMAIL:?PGADMIN_ADMIN_EMAIL is not set}
      PGADMIN_DEFAULT_PASSWORD_FILE: /run/secrets/pgadmin_password
      PGADMIN_DISABLE_POSTFIX: "1"
      PGADMIN_LISTEN_PORT: "5050"
      PGADMIN_REPLACE_SERVERS_ON_STARTUP: "True"
      PGADMIN_CONFIG_ENHANCED_COOKIE_PROTECTION: "True"
      PGADMIN_CONFIG_UPGRADE_CHECK_ENABLED: "False"
    volumes:
      - ${PLATFORM_DATABASE_DATA_ROOT:?PLATFORM_DATABASE_DATA_ROOT is not set}/pgadmin:/var/lib/pgadmin
      - ${PLATFORM_DATABASE_CONFIG_ROOT:?PLATFORM_DATABASE_CONFIG_ROOT is not set}/pgadmin/servers.json:/pgadmin4/servers.json:ro
      - ${PLATFORM_DATABASE_SECRETS_ROOT:?PLATFORM_DATABASE_SECRETS_ROOT is not set}/pgadmin_password:/run/secrets/pgadmin_password:ro
    ports:
      - 127.0.0.1:${PGADMIN_LOCAL_PORT:?PGADMIN_LOCAL_PORT is not set}:5050
    networks:
      - database
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: ${PLATFORM_PGADMIN_MEMORY_LIMIT:?PLATFORM_PGADMIN_MEMORY_LIMIT is not set}
    cpus: "${PLATFORM_PGADMIN_CPU_LIMIT:?PLATFORM_PGADMIN_CPU_LIMIT is not set}"
    stop_grace_period: 30s
    depends_on:
      postgres:
        condition: service_healthy

  postgres-exporter:
    image: ${PLATFORM_POSTGRES_EXPORTER_IMAGE:?PLATFORM_POSTGRES_EXPORTER_IMAGE is not set}
    restart: unless-stopped
    environment:
      DATA_SOURCE_URI: platform-postgres:5432/postgres?sslmode=disable
      DATA_SOURCE_USER: postgres_exporter
      DATA_SOURCE_PASS_FILE: /run/secrets/exporter_password
      PG_EXPORTER_COLLECTION_TIMEOUT: 10s
    volumes:
      - ${PLATFORM_DATABASE_SECRETS_ROOT:?PLATFORM_DATABASE_SECRETS_ROOT is not set}/exporter_password:/run/secrets/exporter_password:ro
    networks:
      database: {}
      observability:
        aliases:
          - platform-postgres-exporter
    read_only: true
    tmpfs:
      - /tmp:size=16m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 64
    mem_limit: ${PLATFORM_POSTGRES_EXPORTER_MEMORY_LIMIT:?PLATFORM_POSTGRES_EXPORTER_MEMORY_LIMIT is not set}
    cpus: "${PLATFORM_POSTGRES_EXPORTER_CPU_LIMIT:?PLATFORM_POSTGRES_EXPORTER_CPU_LIMIT is not set}"
    stop_grace_period: 15s
    depends_on:
      postgres:
        condition: service_healthy

networks:
  database:
    external: true
    name: ${PLATFORM_DATABASE_NETWORK:?PLATFORM_DATABASE_NETWORK is not set}

  observability:
    external: true
    name: ${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}
EOF_DATABASE_COMPOSE
````

Создать wrapper:

````bash
cat > "$OPS_ROOT/scripts/database-compose.sh" <<'EOF_DATABASE_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${PLATFORM_DATABASE_ROOT:?PLATFORM_DATABASE_ROOT is not set}"
: "${PLATFORM_DATABASE_STACK:?PLATFORM_DATABASE_STACK is not set}"

exec docker compose \
  --project-name "$PLATFORM_DATABASE_STACK" \
  --env-file "$VPS_GUIDE_CONFIG" \
  -f "$PLATFORM_DATABASE_ROOT/compose.yml" \
  "$@"
EOF_DATABASE_WRAPPER

chmod 0750 "$OPS_ROOT/scripts/database-compose.sh"

"$OPS_ROOT/scripts/database-compose.sh" config --quiet
````

Проверить image refs:

```bash
"$OPS_ROOT/scripts/database-compose.sh" config --images |
while IFS= read -r image_ref; do
  [[ "$image_ref" =~ @sha256:[a-f0-9]{64}$ ]] || {
    printf 'ERROR: mutable image in database Compose: %s\n' "$image_ref" >&2
    exit 1
  }
done

printf 'Database Compose image contract passed.\n'
```

---

## 9. Проверить bootstrap contract и запустить PostgreSQL

Сначала поднимаем только PostgreSQL, чтобы bootstrap roles появились **до** запуска exporter.

Перед первым стартом автоматически проверяем:

- encrypted source существует;
- plaintext bootstrap secret заново materialized из SOPS;
- secret непустой и имеет ожидаемый формат;
- Compose действительно передаёт `POSTGRES_PASSWORD_FILE`;
- secret читается внутри **того же PostgreSQL image**;
- в `PGDATA` нет неполной/чужой PostgreSQL initialization.

Создать preflight:

````bash
cat > "$OPS_ROOT/scripts/database-postgres-preflight.sh" <<'EOF_DATABASE_POSTGRES_PREFLIGHT'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT \
  PLATFORM_DATABASE_DATA_ROOT \
  PLATFORM_DATABASE_SECRETS_ROOT \
  PLATFORM_POSTGRES_IMAGE; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ -x "$OPS_ROOT/scripts/database-secrets-apply.sh" ]] || {
  printf 'ERROR: database-secrets-apply.sh is missing\n' >&2
  exit 1
}

[[ -x "$OPS_ROOT/scripts/database-compose.sh" ]] || {
  printf 'ERROR: database-compose.sh is missing\n' >&2
  exit 1
}

# Always reconstruct runtime files from the encrypted SOPS source before a
# first start. This also repairs stale/empty plaintext files safely.
"$OPS_ROOT/scripts/database-secrets-apply.sh" >/dev/null

secret="$PLATFORM_DATABASE_SECRETS_ROOT/postgres_password"

sudo test -f "$secret" || {
  printf 'ERROR: PostgreSQL bootstrap secret is missing\n' >&2
  exit 1
}

secret_length="$(sudo sh -c 'value="$(cat "$1")"; printf "%s" "${#value}"' sh "$secret")"
[[ "$secret_length" == "64" ]] || {
  printf 'ERROR: PostgreSQL bootstrap secret has unexpected length: %s\n' \
    "$secret_length" >&2
  exit 1
}

sudo sh -c 'value="$(cat "$1")"; case "$value" in (*[!0-9a-f]*) exit 1;; esac' \
  sh "$secret" || {
  printf 'ERROR: PostgreSQL bootstrap secret has unexpected format\n' >&2
  exit 1
}

# The current failure happened before initdb. Refuse to guess if a partial or
# foreign cluster somehow appeared; Chapter 11/restore procedures must handle
# existing real data explicitly.
pgdata="$PLATFORM_DATABASE_DATA_ROOT/postgres/18/docker"
if sudo test -e "$pgdata/PG_VERSION"; then
  version="$(sudo cat "$pgdata/PG_VERSION")"
  [[ "$version" == "18" ]] || {
    printf 'ERROR: existing PGDATA belongs to PostgreSQL %s, expected 18\n' \
      "$version" >&2
    exit 1
  }
fi

# Verify the exact service environment/mount contract without starting the DB.
"$OPS_ROOT/scripts/database-compose.sh" run \
  --rm \
  --no-deps \
  --entrypoint sh \
  postgres \
  -ceu '
    test "${POSTGRES_PASSWORD_FILE:-}" = /run/secrets/postgres_password
    test -s "$POSTGRES_PASSWORD_FILE"
    value="$(cat "$POSTGRES_PASSWORD_FILE")"
    test "${#value}" -eq 64
    case "$value" in
      *[!0-9a-f]*) exit 1 ;;
    esac
  ' >/dev/null

printf 'PostgreSQL bootstrap contract passed.\n'
EOF_DATABASE_POSTGRES_PREFLIGHT

chmod 0750 "$OPS_ROOT/scripts/database-postgres-preflight.sh"
"$OPS_ROOT/scripts/database-postgres-preflight.sh"
````

Ожидаемый результат:

```text
PostgreSQL bootstrap contract passed.
```

Запустить PostgreSQL:

```bash
"$OPS_ROOT/scripts/database-compose.sh" up -d postgres
```

Дождаться readiness автоматически:

````bash
for attempt in $(seq 1 30); do
  if "$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
    pg_isready -U postgres -d postgres -h /var/run/postgresql \
    >/dev/null 2>&1; then
    printf 'PostgreSQL is ready.\n'
    break
  fi

  if [[ "$attempt" -eq 30 ]]; then
    printf 'ERROR: PostgreSQL did not become ready.\n' >&2
    "$OPS_ROOT/scripts/database-compose.sh" logs --tail=200 postgres >&2
    exit 1
  fi

  sleep 2
done
````

---

## 10. Bootstrap platform roles

Создаём:

```text
postgres
  superuser
  local socket only
  never used by applications

platform_admin
  LOGIN
  NOCREATEDB
  NOCREATEROLE
  NOSUPERUSER
  NOREPLICATION
  NOBYPASSRLS
  pgAdmin/operator role

postgres_exporter
  LOGIN
  pg_monitor
  no write privileges
```

Создать bootstrap script:

````bash
cat > "$OPS_ROOT/scripts/database-bootstrap.sh" <<'EOF_DATABASE_BOOTSTRAP'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${SOPS_DATABASE_FILE:?SOPS_DATABASE_FILE is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${OPS_ROOT:?OPS_ROOT is not set}"

export SOPS_AGE_KEY_FILE

plain="$(mktemp)"
trap 'rm -f "$plain"' EXIT
chmod 0600 "$plain"

sops decrypt --output-type json "$SOPS_DATABASE_FILE" > "$plain"

platform_admin_password="$(jq -er '.platform_admin_password' "$plain")"
exporter_password="$(jq -er '.exporter_password' "$plain")"

[[ "$platform_admin_password" =~ ^[a-f0-9]{64}$ ]] || {
  printf 'ERROR: unexpected platform_admin password format\n' >&2
  exit 1
}
[[ "$exporter_password" =~ ^[a-f0-9]{64}$ ]] || {
  printf 'ERROR: unexpected exporter password format\n' >&2
  exit 1
}

{
  cat <<'SQL_BOOTSTRAP_1'
DO $bootstrap$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'platform_admin'
  ) THEN
    CREATE ROLE platform_admin
      LOGIN
      NOSUPERUSER
      INHERIT
      NOCREATEDB
      NOCREATEROLE
      NOREPLICATION
      NOBYPASSRLS
      CONNECTION LIMIT 5;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter'
  ) THEN
    CREATE ROLE postgres_exporter
      LOGIN
      NOSUPERUSER
      INHERIT
      NOCREATEDB
      NOCREATEROLE
      NOREPLICATION
      NOBYPASSRLS
      CONNECTION LIMIT 3;
  END IF;
END
$bootstrap$;
SQL_BOOTSTRAP_1

  printf "ALTER ROLE platform_admin PASSWORD '%s';\n" \
    "$platform_admin_password"
  printf "ALTER ROLE postgres_exporter PASSWORD '%s';\n" \
    "$exporter_password"

  cat <<'SQL_BOOTSTRAP_2'
ALTER ROLE platform_admin
  NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 5;

ALTER ROLE postgres_exporter
  NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 3;

GRANT pg_monitor TO postgres_exporter;
GRANT pg_monitor TO platform_admin;

REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE postgres TO platform_admin;
GRANT CONNECT ON DATABASE postgres TO postgres_exporter;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO platform_admin;
GRANT USAGE ON SCHEMA public TO postgres_exporter;

ALTER ROLE postgres_exporter IN DATABASE postgres
  SET search_path = pg_catalog;
ALTER ROLE postgres_exporter IN DATABASE postgres
  SET statement_timeout = '10s';

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SQL_BOOTSTRAP_2
} |
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -v ON_ERROR_STOP=1 -U postgres -d postgres

unset platform_admin_password exporter_password

printf 'Platform PostgreSQL roles bootstrapped.\n'
EOF_DATABASE_BOOTSTRAP

chmod 0750 "$OPS_ROOT/scripts/database-bootstrap.sh"
"$OPS_ROOT/scripts/database-bootstrap.sh"
````

---

## 11. Запустить pgAdmin и postgres_exporter

```bash
"$OPS_ROOT/scripts/database-compose.sh" up -d
```

Не публикуем PostgreSQL port.

Единственный host listener этого stack должен быть:

```text
127.0.0.1:5050 -> pgAdmin
```

---

## 12. Опубликовать pgAdmin только через Tailscale Serve

Используем отдельный private HTTPS port:

```text
8444/tcp
```

Настроить Serve:

```bash
sudo tailscale serve \
  --bg \
  --https="$PGADMIN_TAILSCALE_PORT" \
  "http://127.0.0.1:${PGADMIN_LOCAL_PORT}"
```

Вывести URL:

```bash
printf '%s\n' "$PGADMIN_URL"
```

### Если tailnet policy restrictive

Разрешить `tcp:8444` только admin identity/server tag аналогично уже настроенному Grafana `tcp:8443`.

**Не добавлять** UFW public allow rule для `8444`.

**Не добавлять** Caddy route вида:

```text
pgadmin.example.com
```

pgAdmin — administrative surface и остаётся private-only.

### Получить login password pgAdmin

Email:

```bash
printf '%s\n' "$PGADMIN_ADMIN_EMAIL"
```

Пароль вывести только непосредственно перед login:

```bash
SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" \
  sops decrypt --output-type json "$SOPS_DATABASE_FILE" |
jq -r '.pgadmin_password'
```

После login не сохранять этот password в shell variables/history вручную.

---

## 13. Подключить PostgreSQL к существующему Prometheus

Prometheus уже находится в `observability` network.

Exporter подключён одновременно к:

```text
database
observability
```

и имеет network alias:

```text
platform-postgres-exporter
```

Patch Prometheus config идемпотентно:

````bash
python3 - "$OBSERVABILITY_CONFIG_ROOT/prometheus/prometheus.yml" <<'PY_PROMETHEUS'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "job_name: platform-postgres" not in text:
    marker = "  - job_name: blackbox-exporter\n"
    block = """  - job_name: platform-postgres
    static_configs:
      - targets:
          - platform-postgres-exporter:9187
        labels:
          instance: platform-postgres

"""
    if marker not in text:
        raise SystemExit("ERROR: expected blackbox-exporter scrape job was not found")
    text = text.replace(marker, block + marker, 1)

path.write_text(text, encoding="utf-8")
PY_PROMETHEUS
````

---

## 14. Добавить PostgreSQL alerts

Создать отдельный rules file:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/postgresql.yml" <<'EOF_POSTGRES_RULES'
groups:
  - name: platform-postgresql
    rules:
      - alert: PlatformPostgresExporterDown
        expr: up{job="platform-postgres"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Platform PostgreSQL exporter is down"
          description: "Prometheus cannot scrape postgres_exporter for more than 2 minutes."

      - alert: PlatformPostgresExporterError
        expr: pg_exporter_last_scrape_error{job="platform-postgres"} > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "postgres_exporter reports scrape errors"
          description: "postgres_exporter cannot collect one or more PostgreSQL metric groups."

      - alert: PlatformPostgresHighConnections
        expr: sum(pg_stat_database_numbackends{job="platform-postgres",datname!~"template0|template1"}) > 45
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Platform PostgreSQL has many active connections"
          description: "More than 45 PostgreSQL backends have been active for 10 minutes."

      - alert: PlatformPostgresDeadlocks
        expr: sum(increase(pg_stat_database_deadlocks{job="platform-postgres",datname!~"template0|template1"}[15m])) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL deadlock detected"
          description: "At least one deadlock was detected during the last 15 minutes."
EOF_POSTGRES_RULES

chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/postgresql.yml"
````

Проверить Prometheus config и rules:

````bash
docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus:/etc/prometheus:ro" \
  "$PROMETHEUS_IMAGE" \
  check config /etc/prometheus/prometheus.yml

docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules:/rules:ro" \
  "$PROMETHEUS_IMAGE" \
  check rules /rules/postgresql.yml
````

Применить config:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" restart prometheus
```

---

## 15. Добавить PostgreSQL dashboard в Grafana

Dashboard намеренно небольшой: только operational signals, которые полезны на single-VPS.

Создать JSON:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards/postgresql-platform.json" <<'EOF_PG_DASHBOARD'
{
  "annotations": {
    "list": []
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {},
        "overrides": []
      },
      "gridPos": {
        "h": 5,
        "w": 6,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "targets": [
        {
          "expr": "up{job=\"platform-postgres\"}",
          "refId": "A"
        }
      ],
      "title": "Exporter up",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {},
        "overrides": []
      },
      "gridPos": {
        "h": 5,
        "w": 6,
        "x": 6,
        "y": 0
      },
      "id": 2,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "targets": [
        {
          "expr": "sum(pg_stat_database_numbackends{job=\"platform-postgres\",datname!~\"template0|template1\"})",
          "refId": "A"
        }
      ],
      "title": "Connections",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "unit": "bytes"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 0
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "desc"
        }
      },
      "targets": [
        {
          "expr": "pg_database_size_bytes{job=\"platform-postgres\",datname!~\"template0|template1\"}",
          "legendFormat": "{{datname}}",
          "refId": "A"
        }
      ],
      "title": "Database size",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "unit": "ops"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 8
      },
      "id": 4,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "desc"
        }
      },
      "targets": [
        {
          "expr": "sum by (datname) (rate(pg_stat_database_xact_commit{job=\"platform-postgres\",datname!~\"template0|template1\"}[5m]))",
          "legendFormat": "{{datname}} commit",
          "refId": "A"
        },
        {
          "expr": "sum by (datname) (rate(pg_stat_database_xact_rollback{job=\"platform-postgres\",datname!~\"template0|template1\"}[5m]))",
          "legendFormat": "{{datname}} rollback",
          "refId": "B"
        }
      ],
      "title": "Transactions / second",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {},
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "id": 5,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "desc"
        }
      },
      "targets": [
        {
          "expr": "sum by (datname) (increase(pg_stat_database_deadlocks{job=\"platform-postgres\",datname!~\"template0|template1\"}[1h]))",
          "legendFormat": "{{datname}}",
          "refId": "A"
        }
      ],
      "title": "Deadlocks / hour",
      "type": "timeseries"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 41,
  "tags": ["postgresql", "platform", "production"],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-6h",
    "to": "now"
  },
  "timezone": "browser",
  "title": "PostgreSQL Platform",
  "uid": "postgresql-platform",
  "version": 1
}
EOF_PG_DASHBOARD

jq empty "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards/postgresql-platform.json"
````

Grafana provisioning уже смотрит этот directory, поэтому отдельный public route или новый Grafana datasource не нужен.

---

## 16. Создать project provisioner

Это основной operational helper главы.

Команда:

```text
database-project-create.sh my-app
```

создаёт:

```text
PostgreSQL:
  database:      my_app
  migrator role: my_app_migrator
  runtime role:  my_app_runtime

Git:
  secrets/database/my-app.enc.yaml
  config/database/projects/my-app.json

Runtime:
  /opt/apps/my-app/secrets/database-runtime.env
  /opt/apps/my-app/secrets/database-migration.env
```

### Privilege model

```text
my_app_migrator
  owns database
  CREATE/ALTER/DROP objects
  connection limit 2
  used only for migrations

my_app_runtime
  CONNECT
  schema USAGE
  SELECT/INSERT/UPDATE/DELETE
  sequence USAGE/SELECT
  EXECUTE functions created by migrator
  no DDL
  connection limit 8
```

Создать script:

````bash
cat > "$OPS_ROOT/scripts/database-project-create.sh" <<'EOF_DB_PROJECT_CREATE'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

usage() {
  printf 'Usage: %s <app-name>\n' "$0" >&2
  printf 'Example: %s my-api\n' "$0" >&2
}

[[ $# -eq 1 ]] || {
  usage
  exit 2
}

APP_NAME="$1"

[[ "$APP_NAME" =~ ^[a-z][a-z0-9-]{0,39}$ ]] || {
  printf 'ERROR: app-name must match ^[a-z][a-z0-9-]{0,39}$\n' >&2
  exit 2
}

for name in \
  OPS_ROOT APPS_ROOT OPS_GROUP ADMIN_USER \
  SOPS_CONFIG SOPS_AGE_KEY_FILE SOPS_DATABASE_PROJECTS_ROOT \
  PLATFORM_DATABASE_PROJECTS_ROOT PLATFORM_DB_RUNTIME_CONNECTION_LIMIT \
  PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

DB_IDENT="${APP_NAME//-/_}"
DB_NAME="$DB_IDENT"
RUNTIME_ROLE="${DB_IDENT}_runtime"
MIGRATOR_ROLE="${DB_IDENT}_migrator"

SOPS_FILE="$SOPS_DATABASE_PROJECTS_ROOT/${APP_NAME}.enc.yaml"
MANIFEST_FILE="$PLATFORM_DATABASE_PROJECTS_ROOT/${APP_NAME}.json"
APP_SECRET_DIR="$APPS_ROOT/$APP_NAME/secrets"
RUNTIME_ENV="$APP_SECRET_DIR/database-runtime.env"
MIGRATION_ENV="$APP_SECRET_DIR/database-migration.env"

export SOPS_AGE_KEY_FILE SOPS_CONFIG

create_encrypted_source() {
  local plain encrypted

  plain="$(mktemp)"
  encrypted="$(mktemp "${SOPS_FILE}.tmp.XXXXXX")"
  chmod 0600 "$plain" "$encrypted"

  python3 - \
    "$plain" \
    "$APP_NAME" \
    "$DB_NAME" \
    "$RUNTIME_ROLE" \
    "$MIGRATOR_ROLE" <<'PY_PROJECT_SECRET'
from pathlib import Path
import json
import secrets
import sys

path, app, db, runtime_role, migrator_role = sys.argv[1:]

payload = {
    "app_name": app,
    "database_name": db,
    "runtime_user": runtime_role,
    "runtime_password": secrets.token_hex(32),
    "migrator_user": migrator_role,
    "migrator_password": secrets.token_hex(32),
}

Path(path).write_text(
    json.dumps(payload, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY_PROJECT_SECRET

  if ! SOPS_CONFIG="$SOPS_CONFIG" sops encrypt \
    --filename-override "$SOPS_FILE" \
    --input-type json \
    --output-type yaml \
    "$plain" > "$encrypted"; then
    rm -f "$plain" "$encrypted"
    return 1
  fi

  rm -f "$plain"
  mv -f "$encrypted" "$SOPS_FILE"
  chmod 0644 "$SOPS_FILE"
  chown "$ADMIN_USER:$OPS_GROUP" "$SOPS_FILE"
}

if [[ ! -s "$SOPS_FILE" ]]; then
  # Do not silently take ownership of an existing database/roles when the
  # encrypted source-of-truth is missing. This protects manually created or
  # previously provisioned projects from accidental credential replacement.
  existing_objects="$(
    "$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
      psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
      "SELECT
         (SELECT count(*) FROM pg_roles
            WHERE rolname IN ('${RUNTIME_ROLE}', '${MIGRATOR_ROLE}'))
       + (SELECT count(*) FROM pg_database
            WHERE datname = '${DB_NAME}');"
  )"

  [[ "$existing_objects" == "0" ]] || {
    printf 'ERROR: database or project roles already exist, but %s is missing.\n' \
      "$SOPS_FILE" >&2
    printf 'Refusing to generate new credentials and take ownership automatically.\n' >&2
    exit 1
  }

  create_encrypted_source
  printf 'Created encrypted project secret: %s\n' "$SOPS_FILE"
fi

plain="$(mktemp)"
runtime_tmp="$(mktemp)"
migration_tmp="$(mktemp)"
trap 'rm -f "$plain" "$runtime_tmp" "$migration_tmp"' EXIT
chmod 0600 "$plain" "$runtime_tmp" "$migration_tmp"

sops decrypt --output-type json "$SOPS_FILE" > "$plain"

stored_app="$(jq -er '.app_name' "$plain")"
stored_db="$(jq -er '.database_name' "$plain")"
stored_runtime_role="$(jq -er '.runtime_user' "$plain")"
stored_runtime_password="$(jq -er '.runtime_password' "$plain")"
stored_migrator_role="$(jq -er '.migrator_user' "$plain")"
stored_migrator_password="$(jq -er '.migrator_password' "$plain")"

[[ "$stored_app" == "$APP_NAME" ]] || {
  printf 'ERROR: encrypted source app_name mismatch\n' >&2
  exit 1
}
[[ "$stored_db" == "$DB_NAME" ]] || {
  printf 'ERROR: encrypted source database_name mismatch\n' >&2
  exit 1
}
[[ "$stored_runtime_role" == "$RUNTIME_ROLE" ]] || {
  printf 'ERROR: encrypted source runtime_user mismatch\n' >&2
  exit 1
}
[[ "$stored_migrator_role" == "$MIGRATOR_ROLE" ]] || {
  printf 'ERROR: encrypted source migrator_user mismatch\n' >&2
  exit 1
}
[[ "$stored_runtime_password" =~ ^[a-f0-9]{64}$ ]] || {
  printf 'ERROR: runtime password format is invalid\n' >&2
  exit 1
}
[[ "$stored_migrator_password" =~ ^[a-f0-9]{64}$ ]] || {
  printf 'ERROR: migrator password format is invalid\n' >&2
  exit 1
}

psql_admin() {
  "$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
    psql -X -v ON_ERROR_STOP=1 -U postgres "$@"
}

role_exists() {
  local role="$1"
  [[ "$(
    psql_admin -d postgres -Atc \
      "SELECT 1 FROM pg_roles WHERE rolname = '${role}'"
  )" == "1" ]]
}

if ! role_exists "$MIGRATOR_ROLE"; then
  printf 'CREATE ROLE "%s" LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s;\n' \
    "$MIGRATOR_ROLE" \
    "$PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT" |
  psql_admin -d postgres
fi

if ! role_exists "$RUNTIME_ROLE"; then
  printf 'CREATE ROLE "%s" LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s;\n' \
    "$RUNTIME_ROLE" \
    "$PLATFORM_DB_RUNTIME_CONNECTION_LIMIT" |
  psql_admin -d postgres
fi

{
  printf 'ALTER ROLE "%s" NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s PASSWORD '\''%s'\'';\n' \
    "$MIGRATOR_ROLE" \
    "$PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT" \
    "$stored_migrator_password"

  printf 'ALTER ROLE "%s" NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s PASSWORD '\''%s'\'';\n' \
    "$RUNTIME_ROLE" \
    "$PLATFORM_DB_RUNTIME_CONNECTION_LIMIT" \
    "$stored_runtime_password"
} | psql_admin -d postgres

DB_EXISTS="$(
  psql_admin -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'"
)"

if [[ "$DB_EXISTS" != "1" ]]; then
  printf 'CREATE DATABASE "%s" OWNER "%s";\n' \
    "$DB_NAME" "$MIGRATOR_ROLE" |
  psql_admin -d postgres
fi

DB_OWNER="$(
  psql_admin -d postgres -Atc \
    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '${DB_NAME}'"
)"

[[ "$DB_OWNER" == "$MIGRATOR_ROLE" ]] || {
  printf 'ERROR: database %s exists but owner is %s, expected %s\n' \
    "$DB_NAME" "$DB_OWNER" "$MIGRATOR_ROLE" >&2
  exit 1
}

{
  printf 'REVOKE ALL ON DATABASE "%s" FROM PUBLIC;\n' "$DB_NAME"
  printf 'GRANT CONNECT, TEMPORARY ON DATABASE "%s" TO "%s";\n' \
    "$DB_NAME" "$MIGRATOR_ROLE"
  printf 'GRANT CONNECT ON DATABASE "%s" TO "%s";\n' \
    "$DB_NAME" "$RUNTIME_ROLE"
  printf 'GRANT CONNECT ON DATABASE "%s" TO platform_admin;\n' "$DB_NAME"
  printf 'GRANT "%s" TO platform_admin;\n' "$MIGRATOR_ROLE"
} | psql_admin -d postgres

{
  printf 'REVOKE ALL ON SCHEMA public FROM PUBLIC;\n'
  printf 'GRANT ALL ON SCHEMA public TO "%s";\n' "$MIGRATOR_ROLE"
  printf 'GRANT USAGE ON SCHEMA public TO "%s";\n' "$RUNTIME_ROLE"

  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;\n' \
    "$MIGRATOR_ROLE"
  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "%s";\n' \
    "$MIGRATOR_ROLE" "$RUNTIME_ROLE"

  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;\n' \
    "$MIGRATOR_ROLE"
  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "%s";\n' \
    "$MIGRATOR_ROLE" "$RUNTIME_ROLE"

  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" REVOKE USAGE ON TYPES FROM PUBLIC;\n' \
    "$MIGRATOR_ROLE"
  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public GRANT USAGE ON TYPES TO "%s";\n' \
    "$MIGRATOR_ROLE" "$RUNTIME_ROLE"

  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;\n' \
    "$MIGRATOR_ROLE"
  printf 'ALTER DEFAULT PRIVILEGES FOR ROLE "%s" IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO "%s";\n' \
    "$MIGRATOR_ROLE" "$RUNTIME_ROLE"

  printf 'ALTER ROLE "%s" IN DATABASE "%s" SET search_path = public;\n' \
    "$RUNTIME_ROLE" "$DB_NAME"
  printf 'ALTER ROLE "%s" IN DATABASE "%s" SET idle_in_transaction_session_timeout = '\''60s'\'';\n' \
    "$RUNTIME_ROLE" "$DB_NAME"

  printf 'ALTER ROLE "%s" IN DATABASE "%s" SET search_path = public;\n' \
    "$MIGRATOR_ROLE" "$DB_NAME"
  printf 'ALTER ROLE "%s" IN DATABASE "%s" SET idle_in_transaction_session_timeout = '\''5min'\'';\n' \
    "$MIGRATOR_ROLE" "$DB_NAME"

  printf 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements;\n'
} | psql_admin -d "$DB_NAME"

sudo install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0750 \
  "$APP_SECRET_DIR"

printf 'DATABASE_URL=postgresql://%s:%s@platform-postgres:5432/%s?sslmode=disable\n' \
  "$RUNTIME_ROLE" \
  "$stored_runtime_password" \
  "$DB_NAME" > "$runtime_tmp"

printf 'DATABASE_URL=postgresql://%s:%s@platform-postgres:5432/%s?sslmode=disable\n' \
  "$MIGRATOR_ROLE" \
  "$stored_migrator_password" \
  "$DB_NAME" > "$migration_tmp"

sudo install \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0640 \
  "$runtime_tmp" \
  "$RUNTIME_ENV"

sudo install \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0640 \
  "$migration_tmp" \
  "$MIGRATION_ENV"

python3 - \
  "$MANIFEST_FILE" \
  "$APP_NAME" \
  "$DB_NAME" \
  "$RUNTIME_ROLE" \
  "$MIGRATOR_ROLE" \
  "$PLATFORM_DB_RUNTIME_CONNECTION_LIMIT" \
  "$PLATFORM_DB_MIGRATOR_CONNECTION_LIMIT" <<'PY_MANIFEST'
from pathlib import Path
import json
import sys

(
    path,
    app,
    database,
    runtime_role,
    migrator_role,
    runtime_limit,
    migrator_limit,
) = sys.argv[1:]

payload = {
    "app": app,
    "database": database,
    "runtime_role": runtime_role,
    "migrator_role": migrator_role,
    "runtime_connection_limit": int(runtime_limit),
    "migrator_connection_limit": int(migrator_limit),
}

Path(path).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY_MANIFEST

chmod 0644 "$MANIFEST_FILE"
chown "$ADMIN_USER:$OPS_GROUP" "$MANIFEST_FILE"

unset stored_runtime_password stored_migrator_password

printf '\nProject database is ready.\n'
printf 'App:              %s\n' "$APP_NAME"
printf 'Database:         %s\n' "$DB_NAME"
printf 'Runtime role:     %s\n' "$RUNTIME_ROLE"
printf 'Migrator role:    %s\n' "$MIGRATOR_ROLE"
printf 'Runtime env:      %s\n' "$RUNTIME_ENV"
printf 'Migration env:    %s\n' "$MIGRATION_ENV"
printf 'Encrypted source: %s\n' "$SOPS_FILE"
EOF_DB_PROJECT_CREATE

chmod 0750 "$OPS_ROOT/scripts/database-project-create.sh"
````

Script не выводит passwords.

Он безопасно повторяем:

- существующий encrypted source не перегенерируется;
- password из SOPS повторно применяется к PostgreSQL;
- grants/default privileges повторно применяются;
- runtime env files восстанавливаются из SOPS;
- database с неожиданным owner вызывает ошибку вместо silent takeover.

---

## 17. Как подключать новый проект к platform PostgreSQL

Для реального проекта выполнить:

```bash
"$OPS_ROOT/scripts/database-project-create.sh" my-app
```

Заменить:

```text
my-app
```

на имя проекта.

В application Compose service добавить runtime secret file:

```yaml
env_file:
  - /opt/apps/my-app/secrets/database-runtime.env
```

и external network:

```yaml
networks:
  - edge
  - database

networks:
  edge:
    external: true
    name: ${EDGE_NETWORK:?EDGE_NETWORK is not set}

  database:
    external: true
    name: ${PLATFORM_DATABASE_NETWORK:?PLATFORM_DATABASE_NETWORK is not set}
```

Для migration service использовать **другой** env file:

```yaml
env_file:
  - /opt/apps/my-app/secrets/database-migration.env
```

### Важное правило

Application process работает как:

```text
<app>_runtime
```

Migration process работает как:

```text
<app>_migrator
```

Не используйте migrator credentials в обычном web/worker container.

Это ограничивает ущерб при application-level compromise: runtime process не получает DDL/ownership privileges.

---

## 18. Создать smoke-test privilege model

Smoke-test создаёт временную database/roles, проверяет TCP/SCRAM и затем полностью удаляет их.

Создать script:

````bash
cat > "$OPS_ROOT/scripts/database-smoke.sh" <<'EOF_DATABASE_SMOKE'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${PLATFORM_DATABASE_NETWORK:?PLATFORM_DATABASE_NETWORK is not set}"
: "${PLATFORM_POSTGRES_IMAGE:?PLATFORM_POSTGRES_IMAGE is not set}"

SUFFIX="$(openssl rand -hex 4)"
DB="ch12_smoke_${SUFFIX}"
OWNER="ch12_owner_${SUFFIX}"
RUNTIME="ch12_runtime_${SUFFIX}"
PASSWORD="$(openssl rand -hex 24)"

psql_admin() {
  "$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
    psql -X -v ON_ERROR_STOP=1 -U postgres "$@"
}

cleanup() {
  set +e
  printf 'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''%s'\'' AND pid <> pg_backend_pid();\n' "$DB" |
    psql_admin -d postgres >/dev/null 2>&1
  printf 'DROP DATABASE IF EXISTS "%s";\n' "$DB" |
    psql_admin -d postgres >/dev/null 2>&1
  printf 'DROP ROLE IF EXISTS "%s";\n' "$RUNTIME" |
    psql_admin -d postgres >/dev/null 2>&1
  printf 'DROP ROLE IF EXISTS "%s";\n' "$OWNER" |
    psql_admin -d postgres >/dev/null 2>&1
}
trap cleanup EXIT

printf 'CREATE ROLE "%s" LOGIN PASSWORD '\''%s'\'';\n' "$OWNER" "$PASSWORD" |
  psql_admin -d postgres
printf 'CREATE ROLE "%s" LOGIN PASSWORD '\''%s'\'';\n' "$RUNTIME" "$PASSWORD" |
  psql_admin -d postgres
printf 'CREATE DATABASE "%s" OWNER "%s";\n' "$DB" "$OWNER" |
  psql_admin -d postgres

{
  printf 'REVOKE ALL ON DATABASE "%s" FROM PUBLIC;\n' "$DB"
  printf 'GRANT CONNECT ON DATABASE "%s" TO "%s";\n' "$DB" "$RUNTIME"
} | psql_admin -d postgres

{
  printf 'REVOKE ALL ON SCHEMA public FROM PUBLIC;\n'
  printf 'GRANT USAGE ON SCHEMA public TO "%s";\n' "$RUNTIME"
  printf 'CREATE TABLE smoke_value (id bigint PRIMARY KEY, value text NOT NULL);\n'
  printf 'GRANT SELECT, INSERT, UPDATE, DELETE ON smoke_value TO "%s";\n' "$RUNTIME"
} | psql_admin -d "$DB"

PGPASSWORD="$PASSWORD" docker run --rm \
  --network "$PLATFORM_DATABASE_NETWORK" \
  -e PGPASSWORD \
  "$PLATFORM_POSTGRES_IMAGE" \
  psql \
    -X \
    -v ON_ERROR_STOP=1 \
    -h platform-postgres \
    -U "$RUNTIME" \
    -d "$DB" \
    -c "INSERT INTO smoke_value VALUES (1, 'ok'); SELECT * FROM smoke_value;" \
    >/dev/null

if PGPASSWORD="$PASSWORD" docker run --rm \
  --network "$PLATFORM_DATABASE_NETWORK" \
  -e PGPASSWORD \
  "$PLATFORM_POSTGRES_IMAGE" \
  psql \
    -X \
    -v ON_ERROR_STOP=1 \
    -h platform-postgres \
    -U "$RUNTIME" \
    -d "$DB" \
    -c 'CREATE TABLE should_fail(id integer);' \
    >/dev/null 2>&1; then
  printf 'ERROR: runtime role unexpectedly has CREATE privilege.\n' >&2
  exit 1
fi

if PGPASSWORD="$PASSWORD" docker run --rm \
  --network "$PLATFORM_DATABASE_NETWORK" \
  -e PGPASSWORD \
  "$PLATFORM_POSTGRES_IMAGE" \
  psql \
    -X \
    -v ON_ERROR_STOP=1 \
    -h platform-postgres \
    -U "$RUNTIME" \
    -d postgres \
    -c 'SELECT 1;' \
    >/dev/null 2>&1; then
  printf 'ERROR: runtime role unexpectedly connects to postgres database.\n' >&2
  exit 1
fi

printf 'Database privilege smoke-test passed.\n'
EOF_DATABASE_SMOKE

chmod 0750 "$OPS_ROOT/scripts/database-smoke.sh"
"$OPS_ROOT/scripts/database-smoke.sh"
````

---

## 19. Проверить PostgreSQL security contract

Основная проверка одной командой:

````bash
cat > "$OPS_ROOT/scripts/database-check.sh" <<'EOF_DATABASE_CHECK'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for command in docker jq curl; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: command not found: %s\n' "$command" >&2
    exit 1
  }
done

"$OPS_ROOT/scripts/database-compose.sh" config --quiet

for service in postgres pgadmin postgres-exporter; do
  container_id="$("$OPS_ROOT/scripts/database-compose.sh" ps -q "$service")"
  [[ -n "$container_id" ]] || {
    printf 'ERROR: container missing: %s\n' "$service" >&2
    exit 1
  }

  state="$(docker inspect "$container_id" --format '{{.State.Status}}')"
  [[ "$state" == "running" ]] || {
    printf 'ERROR: %s is not running: %s\n' "$service" "$state" >&2
    exit 1
  }
done

POSTGRES_ID="$("$OPS_ROOT/scripts/database-compose.sh" ps -q postgres)"
EXPORTER_ID="$("$OPS_ROOT/scripts/database-compose.sh" ps -q postgres-exporter)"
PGADMIN_ID="$("$OPS_ROOT/scripts/database-compose.sh" ps -q pgadmin)"

# The official entrypoint may start as root, but the long-running PostgreSQL
# server process itself must run as the image postgres user.
POSTGRES_PID1_UID="$(
  docker exec "$POSTGRES_ID" sh -c     "awk '/^Uid:/{print \\$2}' /proc/1/status"
)"
[[ "$POSTGRES_PID1_UID" == "$PLATFORM_POSTGRES_UID" ]] || {
  printf 'ERROR: PostgreSQL PID 1 runs as uid %s, expected %s\n' \
    "$POSTGRES_PID1_UID" "$PLATFORM_POSTGRES_UID" >&2
  exit 1
}

# PostgreSQL must publish no host ports.
docker inspect "$POSTGRES_ID" |
jq -e '.[0].HostConfig.PortBindings | length == 0' >/dev/null || {
  printf 'ERROR: PostgreSQL publishes a host port\n' >&2
  exit 1
}

# Exporter must publish no host ports.
docker inspect "$EXPORTER_ID" |
jq -e '.[0].HostConfig.PortBindings | length == 0' >/dev/null || {
  printf 'ERROR: postgres_exporter publishes a host port\n' >&2
  exit 1
}

# pgAdmin must bind to loopback only.
PGADMIN_BIND="$(
  docker inspect "$PGADMIN_ID" |
  jq -r '.[0].HostConfig.PortBindings["5050/tcp"][0].HostIp'
)"
[[ "$PGADMIN_BIND" == "127.0.0.1" ]] || {
  printf 'ERROR: pgAdmin is not loopback-only: %s\n' "$PGADMIN_BIND" >&2
  exit 1
}

# database network must be internal and use the configured subnet.
docker network inspect "$PLATFORM_DATABASE_NETWORK" |
jq -e --arg subnet "$PLATFORM_DATABASE_SUBNET" '
  .[0].Internal == true and
  any(.[0].IPAM.Config[]?; .Subnet == $subnet)
' >/dev/null || {
  printf 'ERROR: database network contract failed\n' >&2
  exit 1
}

# HBA must parse without errors.
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
  "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL" |
grep -Fxq '0' || {
  printf 'ERROR: pg_hba.conf contains invalid rules\n' >&2
  exit 1
}

# Required role properties.
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
  "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname='platform_admin'" |
grep -Fxq 'f|f|f|f|f' || {
  printf 'ERROR: platform_admin role attributes differ from contract\n' >&2
  exit 1
}

"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
  "SELECT pg_has_role('postgres_exporter', 'pg_monitor', 'MEMBER')" |
grep -Fxq 't' || {
  printf 'ERROR: postgres_exporter is not a pg_monitor member\n' >&2
  exit 1
}

# pg_stat_statements must be active.
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
  "SELECT extname FROM pg_extension WHERE extname='pg_stat_statements'" |
grep -Fxq 'pg_stat_statements' || {
  printf 'ERROR: pg_stat_statements is not installed\n' >&2
  exit 1
}

# pgAdmin must answer on loopback. Give the container time to finish startup.
pgadmin_ready=0
for _ in $(seq 1 30); do
  if curl --fail --silent --show-error \
    --max-time 3 \
    http://127.0.0.1:5050/misc/ping >/dev/null 2>&1; then
    pgadmin_ready=1
    break
  fi
  sleep 2
done

[[ "$pgadmin_ready" == "1" ]] || {
  printf 'ERROR: pgAdmin did not become ready on 127.0.0.1:5050\n' >&2
  exit 1
}

# Prometheus scrape is asynchronous. Wait for at least one successful scrape
# instead of failing immediately after the exporter/Prometheus reload.
prometheus_ready=0
for _ in $(seq 1 12); do
  if curl --fail --silent --show-error \
    --max-time 5 \
    --get \
    --data-urlencode 'query=up{job="platform-postgres"}' \
    http://127.0.0.1:9090/api/v1/query |
    jq -e '.status == "success" and any(.data.result[]?; .value[1] == "1")' \
      >/dev/null 2>&1; then
    prometheus_ready=1
    break
  fi
  sleep 5
done

[[ "$prometheus_ready" == "1" ]] || {
  printf 'ERROR: Prometheus does not see platform-postgres as up\n' >&2
  exit 1
}

printf 'Database platform check passed.\n'
EOF_DATABASE_CHECK

chmod 0750 "$OPS_ROOT/scripts/database-check.sh"
````

Проверить script и выполнить acceptance check:

```bash
bash -n "$OPS_ROOT/scripts/database-check.sh"
"$OPS_ROOT/scripts/database-check.sh"
```

---

## 20. Проверить pgAdmin

Открыть на admin workstation:

```text
$PGADMIN_URL
```

В UI должен появиться server:

```text
Production
└── Platform PostgreSQL
```

При первом connect pgAdmin попросит database password для:

```text
platform_admin
```

Получить его на VPS:

```bash
SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" \
  sops decrypt --output-type json "$SOPS_DATABASE_FILE" |
jq -r '.platform_admin_password'
```

Этот password можно сохранить внутри pgAdmin после login.

pgAdmin storage находится в:

```text
/opt/data/database/pgadmin
```

и сам pgAdmin доступен только через private Tailscale path.

---

## 21. Проверить PostgreSQL monitoring

Prometheus target:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=up{job="platform-postgres"}' \
  http://127.0.0.1:9090/api/v1/query |
jq '.data.result'
```

В результате должно быть значение:

```text
1
```

Grafana:

```text
PostgreSQL Platform
```

должен появиться автоматически в provisioned dashboards.

---

## 22. Проверить secret policy и Git diff

```bash
cd "$OPS_ROOT"

python3 scripts/secret-policy.py
```

Проверить repository diff:

```bash
git status --short
git diff --check
```

В Git допустимы:

```text
config/database/...
compose/database/compose.yml
scripts/database-*.sh
scripts/chapter-12-configure.sh
secrets/database.enc.yaml
secrets/database/*.enc.yaml
observability config/rules/dashboard changes
```

В Git **не должны** попасть:

```text
/opt/data/database/secrets/*
/opt/apps/*/secrets/database-runtime.env
/opt/apps/*/secrets/database-migration.env
age private identity
plaintext passwords
```

---

## 23. Зафиксировать Chapter 12 в Git

Сначала проверить:

```bash
cd "$OPS_ROOT"

python3 scripts/secret-policy.py
bash -n scripts/chapter-12-configure.sh
bash -n scripts/database-secrets-init.sh
bash -n scripts/database-secrets-apply.sh
bash -n scripts/database-network-ensure.sh
bash -n scripts/database-compose.sh
bash -n scripts/database-bootstrap.sh
bash -n scripts/database-project-create.sh
bash -n scripts/database-smoke.sh
bash -n scripts/database-check.sh

git diff --check
```

Добавить файлы:

```bash
git add \
  compose/database \
  config/database \
  scripts/chapter-12-configure.sh \
  scripts/database-secrets-init.sh \
  scripts/database-secrets-apply.sh \
  scripts/database-network-ensure.sh \
  scripts/database-compose.sh \
  scripts/database-bootstrap.sh \
  scripts/database-project-create.sh \
  scripts/database-smoke.sh \
  scripts/database-check.sh \
  scripts/secret-policy.py \
  secrets/database.enc.yaml \
  config/observability/prometheus/prometheus.yml \
  config/observability/prometheus/rules/postgresql.yml \
  config/observability/grafana/dashboards/postgresql-platform.json
```

Если `OBSERVABILITY_CONFIG_ROOT=/opt/ops/config/observability`, предыдущая команда корректно добавит эти paths из repository.

Проверить staged secret policy:

```bash
python3 scripts/secret-policy.py --staged
```

Commit:

```bash
git commit -m "Add shared PostgreSQL platform service"
git push origin main
```

Проверить clean state:

```bash
git status --short
```

Вывод должен быть пустым.

---

## 24. Ежедневный operational workflow

### Создать database для нового проекта

```bash
"$OPS_ROOT/scripts/database-project-create.sh" my-app
```

После этого закоммитить только encrypted source + manifest:

```bash
cd "$OPS_ROOT"

git add \
  "secrets/database/my-app.enc.yaml" \
  "config/database/projects/my-app.json"

python3 scripts/secret-policy.py --staged

git commit -m "Provision my-app PostgreSQL database"
git push origin main
```

### Проверить stack

```bash
"$OPS_ROOT/scripts/database-check.sh"
```

### Посмотреть PostgreSQL logs

```bash
"$OPS_ROOT/scripts/database-compose.sh" logs --since=30m postgres
```

### Посмотреть pgAdmin logs

```bash
"$OPS_ROOT/scripts/database-compose.sh" logs --since=30m pgadmin
```

### Посмотреть exporter logs

```bash
"$OPS_ROOT/scripts/database-compose.sh" logs --since=30m postgres-exporter
```

### Посмотреть active connections без паролей

```bash
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -U postgres -d postgres -c '
    SELECT
      datname,
      usename,
      application_name,
      client_addr,
      state,
      count(*)
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
    GROUP BY 1,2,3,4,5
    ORDER BY count(*) DESC;
  '
```

### Посмотреть top SQL по total execution time

```bash
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -U postgres -d postgres -c '
    SELECT
      dbid,
      userid,
      calls,
      round(total_exec_time::numeric, 2) AS total_exec_ms,
      round(mean_exec_time::numeric, 2) AS mean_exec_ms,
      rows,
      LEFT(query, 160) AS query
    FROM pg_stat_statements
    ORDER BY total_exec_time DESC
    LIMIT 20;
  '
```

> Query text может содержать application data. Не публикуйте такой вывод в issue/GitHub без review.

---

## 25. Connection pooling policy

На этом VPS **не добавляем PgBouncer автоматически**.

Сначала используем:

```text
small application pools
+ PostgreSQL role CONNECTION LIMIT
+ PostgreSQL max_connections=60
```

Рекомендованный baseline на один application process:

```text
pool min: 0-1
pool max: 5
```

Если приложение имеет несколько replicas/workers, суммарное число connections должно укладываться в role limit.

PgBouncer добавляется позже, когда появляется реальная проблема:

- много short-lived connections;
- несколько worker replicas;
- connection count стабильно приближается к limit;
- framework/serverless-like behavior создаёт connection churn.

Не повышайте `max_connections` до `200/500` как первый способ решения проблемы: каждый backend потребляет ресурсы, а `work_mem` может использоваться многократно в каждой session.

---

## 26. Почему не добавляем общий Redis/Valkey в эту главу

Redis/Valkey — не обязательный слой production VPS.

Он нужен только если приложение действительно использует:

- cache;
- task queue;
- pub/sub;
- locks;
- rate-limit counters;
- ephemeral shared state.

Не создаём shared Redis сейчас только ради «полноты инфраструктуры».

Особенно не используем:

```text
SELECT 0 -> project A
SELECT 1 -> project B
SELECT 2 -> project C
```

как security/isolation mechanism.

Если позже появится shared Valkey use case, правильный design отдельно определит:

- отдельные ACL users;
- key-prefix permissions;
- memory limits;
- eviction policy;
- persistence requirement;
- queue-vs-cache semantics;
- blast radius.

Для critical queue/state workloads отдельный Valkey instance per workload может быть правильнее shared instance.

---

## 27. PostgreSQL update policy

### Minor update

Текущая ветка:

```text
18.x
```

Для minor update:

```text
18.4 -> 18.5
```

не выполняется `pg_upgrade`.

Но update всё равно должен быть controlled:

1. прочитать PostgreSQL release notes;
2. иметь verified backup/restore capability;
3. заменить tag в Chapter 12 source/configuration;
4. resolve новый immutable digest;
5. выполнить planned restart;
6. запустить `database-check.sh` и application smoke tests.

Не использовать Watchtower для автоматического обновления stateful PostgreSQL container.

### Major update

Для:

```text
18 -> 19
```

нужен отдельный migration plan:

- `pg_upgrade`; либо
- dump/restore;
- extension compatibility check;
- rollback window;
- verified backup.

Никогда не меняйте просто:

```text
postgres:18 -> postgres:19
```

поверх существующего data directory.

---

## 28. Backup warning

Главы 10–11 сейчас отложены, поэтому важно явно зафиксировать состояние:

```text
PostgreSQL configured != PostgreSQL disaster-recoverable
```

Docker volume/data directory на том же VPS **не является backup**.

SOPS encrypted credentials в Git также **не являются backup database data**.

До возвращения к backup/restore главам остаётся риск:

```text
VPS/storage lost -> application database data lost
```

Поэтому для реальных ценных production данных Chapters 10–11 остаются P0 requirement.

---

## 29. Диагностика

<details>
<summary>PostgreSQL container не становится healthy</summary>

Проверить только PostgreSQL logs:

```bash
"$OPS_ROOT/scripts/database-compose.sh" logs --tail=250 postgres
```

Проверить host permissions:

```bash
sudo stat -c '%U:%G %a %n' \
  "$PLATFORM_DATABASE_DATA_ROOT/postgres" \
  "$PLATFORM_DATABASE_SECRETS_ROOT/postgres_password"
```

Ожидается:

```text
postgres data owner uid/gid == PLATFORM_POSTGRES_UID:PLATFORM_POSTGRES_GID
postgres_password owner == root:root
postgres_password mode == 400
```

Для PostgreSQL 18 bind mount должен быть именно:

```text
host .../postgres -> /var/lib/postgresql
```

а `PGDATA`:

```text
/var/lib/postgresql/18/docker
```

Не возвращайте старый PostgreSQL Docker layout `/var/lib/postgresql/data` из старых инструкций.

</details>

<details>
<summary><code>Database is uninitialized and superuser password is not specified</code></summary>

Не включать `POSTGRES_HOST_AUTH_METHOD=trust`.

Сначала повторно применить SOPS runtime secret и запустить bootstrap preflight:

```bash
"$OPS_ROOT/scripts/database-secrets-apply.sh"
"$OPS_ROOT/scripts/database-postgres-preflight.sh"
```

Preflight обязан завершиться строкой:

```text
PostgreSQL bootstrap contract passed.
```

После этого recreate только PostgreSQL:

```bash
"$OPS_ROOT/scripts/database-compose.sh" \
  up -d --no-deps --force-recreate postgres
```

Если preflight не проходит, не удалять `PGDATA` и не создавать новый password вручную. Использовать сообщение preflight как точную причину ошибки.

</details>

<details>
<summary><code>password authentication failed</code> для application role</summary>

Не копировать password вручную.

Повторно materialize проект из SOPS:

```bash
"$OPS_ROOT/scripts/database-project-create.sh" my-app
```

Script повторно применит password из encrypted source к PostgreSQL и пересоздаст runtime env files.

После этого recreate только application containers, которые читают env file при container creation.

</details>

<details>
<summary>Application подключается, но migrations получают <code>permission denied</code></summary>

Проверить, какой env file использует migration process.

Migration должен читать:

```text
/opt/apps/<app>/secrets/database-migration.env
```

Обычный runtime:

```text
/opt/apps/<app>/secrets/database-runtime.env
```

Не выдавайте runtime role `CREATE` как workaround.

</details>

<details>
<summary>Runtime application не может работать с таблицами после migration</summary>

Default privileges применяются к objects, созданным именно migrator role.

Если migration tool внутри connection выполняет:

```sql
SET ROLE some_other_role;
```

или objects создаёт другой owner, grants могут отличаться.

Проверить owner проблемной таблицы:

```bash
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -U postgres -d my_app -c '
    SELECT schemaname, tablename, tableowner
    FROM pg_tables
    WHERE schemaname = '\''public'\''
    ORDER BY tablename;
  '
```

Нормальный application migration contract должен создавать objects как `<app>_migrator`.

</details>

<details>
<summary>pgAdmin локально отвечает, но private URL не открывается</summary>

Проверить loopback:

```bash
curl -I "http://127.0.0.1:${PGADMIN_LOCAL_PORT}/"
```

Проверить Serve:

```bash
tailscale serve status
```

Повторно применить:

```bash
sudo tailscale serve \
  --bg \
  --https="$PGADMIN_TAILSCALE_PORT" \
  "http://127.0.0.1:${PGADMIN_LOCAL_PORT}"
```

Если используется restrictive tailnet policy, добавить private allow для `tcp:8444`.

Не создавайте public Caddy route как workaround.

</details>

<details>
<summary>pgAdmin login password из SOPS не подходит</summary>

`PGADMIN_DEFAULT_PASSWORD_FILE` применяется при первоначальном создании pgAdmin user.

Если pgAdmin data directory уже существовал и password был изменён внутри UI, изменение source file само по себе не переписывает существующий account.

Не удалять `/opt/data/database/pgadmin` ради reset без причины.

Сначала проверить pgAdmin logs и выполнить controlled password reset через supported pgAdmin procedure.

</details>

<details>
<summary>Prometheus target <code>platform-postgres</code> DOWN</summary>

Проверить exporter logs:

```bash
"$OPS_ROOT/scripts/database-compose.sh" logs --tail=200 postgres-exporter
```

Проверить membership exporter:

```bash
"$OPS_ROOT/scripts/database-compose.sh" exec -T --user postgres postgres \
  psql -X -U postgres -d postgres -c '
    SELECT pg_has_role('\''postgres_exporter'\'', '\''pg_monitor'\'', '\''MEMBER'\'');
  '
```

Повторно materialize global runtime secrets и recreate exporter:

```bash
"$OPS_ROOT/scripts/database-secrets-apply.sh"
"$OPS_ROOT/scripts/database-compose.sh" \
  up -d --no-deps --force-recreate postgres-exporter
```

</details>

<details>
<summary>Docker не смог создать network <code>database</code></summary>

В актуальной версии главы subnet вручную не выбирается: Docker Engine должен выделить свободный диапазон автоматически.

Проверить существующие Docker networks и address pools:

```bash
docker network ls

docker network inspect $(docker network ls -q) |
jq -r '.[] | .Name as $name | .IPAM.Config[]? | select(.Subnet != null) | "\($name)\t\(.Subnet)"'

sudo jq '."default-address-pools" // "Docker defaults"' /etc/docker/daemon.json 2>/dev/null || true
```

Если Docker сообщает об исчерпании address pools, **не подбирайте subnet наугад**. Сначала проверьте все Docker networks и host routes, затем настройте `default-address-pools` Docker daemon отдельным maintenance-изменением.

</details>

<details>
<summary>PostgreSQL начинает активно использовать swap / VPS упирается в RAM</summary>

Проверить:

```bash
free -h
vmstat 1 10
docker stats --no-stream
```

Не увеличивать первым действием:

```text
shared_buffers
work_mem
max_connections
```

На shared 4 GB VPS сначала:

- проверить application connection pools;
- уменьшить pool max;
- найти долгие queries;
- проверить observability retention;
- посмотреть `pg_stat_activity`;
- только затем менять PostgreSQL tuning.

</details>

<details>
<summary>Нужно дать приложению дополнительный PostgreSQL privilege</summary>

Не выдавать:

```text
SUPERUSER
CREATEDB
CREATEROLE
BYPASSRLS
```

runtime role.

Добавлять только конкретный privilege на конкретный object/schema/function.

Если privilege нужен для migration/DDL — вероятнее всего он должен принадлежать migrator role, а не runtime role.

</details>

---

## 30. Критерии завершения главы

Глава 12 завершена, если одновременно выполнено всё:

```text
[ ] PostgreSQL 18.4 image pinned by digest
[ ] pgAdmin 9.17 image pinned by digest
[ ] postgres_exporter 0.20.1 image pinned by digest
[ ] PostgreSQL data mounted using PostgreSQL 18 /var/lib/postgresql layout
[ ] database Docker network is internal
[ ] database Docker network does not overlap existing networks
[ ] PostgreSQL publishes no host port
[ ] postgres_exporter publishes no host port
[ ] pgAdmin binds only 127.0.0.1:5050
[ ] pgAdmin is reachable through Tailscale Serve :8444
[ ] no public Caddy route exists for pgAdmin
[ ] network superuser postgres login is rejected
[ ] SCRAM-SHA-256 is used for Docker-network clients
[ ] platform_admin is NOCREATEDB/NOCREATEROLE/NOSUPERUSER/NOREPLICATION/NOBYPASSRLS
[ ] postgres_exporter has pg_monitor and no write/admin role
[ ] pg_stat_statements is enabled
[ ] global database credentials are SOPS-encrypted in Git
[ ] plaintext global runtime secrets remain only under /opt/data/database/secrets
[ ] per-project credentials are SOPS-encrypted
[ ] runtime and migrator credentials are separated
[ ] runtime role cannot CREATE tables
[ ] unrelated project databases use separate CONNECT privileges
[ ] database-project-create.sh is idempotent
[ ] database-smoke.sh passes
[ ] Prometheus sees platform-postgres target UP
[ ] PostgreSQL alert rules pass promtool
[ ] PostgreSQL Grafana dashboard JSON is valid
[ ] secret-policy.py passes
[ ] Git working tree is clean after commit/push
```

Главные acceptance tests:

```bash
"$OPS_ROOT/scripts/database-smoke.sh"
"$OPS_ROOT/scripts/database-check.sh"
cd "$OPS_ROOT" && python3 scripts/secret-policy.py
```

---

## 31. Что намеренно не входит в главу 12

Не добавляем:

- public `5432/tcp`;
- public pgAdmin domain;
- PostgreSQL superuser credentials в applications;
- одну database + schema per unrelated project;
- PgBouncer без connection-pressure use case;
- Redis/Valkey без application use case;
- Redis logical DB indexes как project isolation;
- Watchtower auto-updates stateful database;
- automatic PostgreSQL major upgrades;
- HA/replication на одном VPS;
- PITR/WAL archive до backup architecture;
- перенос GlitchTip database в shared cluster;
- automatic destructive database deletion helper;
- database migrations под runtime role.

---

## 32. Что ещё остаётся до действительно законченного production VPS

После текущих Chapters 01–09 + 12 инфраструктура уже закрывает большую часть everyday operational path:

```text
Ubuntu hardening
Docker
Tailscale private administration
Caddy / HTTPS
immutable deploy + rollback contract
GHCR CI / Trivy / SBOM / provenance
Grafana / Prometheus / Loki / Alloy
Telegram alerts
GlitchTip
SOPS + age
shared PostgreSQL platform
pgAdmin
PostgreSQL monitoring
```

Но до финального production baseline остаются важные пункты.

### P0 — off-site backup + verified restore

Это отложенные Chapters 10–11.

Без них потеря VPS всё ещё означает потерю stateful application data.

### P1 — external uptime / dead-man monitoring

Текущие Prometheus, Alertmanager и Blackbox работают **на том же VPS**.

Если VPS полностью выключится, потеряет Internet или Docker daemon не поднимется, локальный monitoring stack также не сможет отправить alert.

Нужен хотя бы один probe **вне VPS**:

```text
external HTTPS uptime monitor
or
remote dead-man/heartbeat service
```

### P1 — database-aware deploy migrations

Текущий deploy contract должен получить явный optional migration phase:

```text
pull immutable image
-> run migration service with <app>_migrator
-> start/recreate runtime with <app>_runtime
-> health check
-> rollback application image if needed
```

Schema migrations должны быть backwards-compatible по expand/contract strategy: rollback container image не обязан уметь автоматически rollback database schema.

### P1 — controlled infrastructure updates + reboot runbook

Нужен финальный operational procedure:

```text
OS security updates
kernel reboot required detection
Docker/Compose update
Caddy update
observability image update
PostgreSQL minor update
reboot
post-reboot acceptance test
```

Автоматически обновлять production containers без smoke checks не нужно.

### P2 — optional PgBouncer

Добавлять только по metrics/connection pressure.

### P2 — optional Valkey

Добавлять только когда конкретный project требует cache/queue/shared ephemeral state.

### P2 — tracing

OpenTelemetry/Tempo имеет смысл после появления приложений с реальной tracing instrumentation.

---

## 33. Технические ориентиры главы

Актуальные official references на момент написания:

```text
PostgreSQL 18 — Managing Databases
https://www.postgresql.org/docs/18/manage-ag-overview.html

PostgreSQL — Versioning Policy
https://www.postgresql.org/support/versioning/

PostgreSQL 18 — pg_hba.conf
https://www.postgresql.org/docs/18/auth-pg-hba-conf.html

PostgreSQL 18 — Resource Consumption
https://www.postgresql.org/docs/18/runtime-config-resource.html

PostgreSQL 18 — pg_stat_statements
https://www.postgresql.org/docs/18/pgstatstatements.html

Official PostgreSQL Docker image
https://hub.docker.com/_/postgres

pgAdmin container deployment
https://www.pgadmin.org/docs/pgadmin4/latest/container_deployment.html

postgres_exporter
https://github.com/prometheus-community/postgres_exporter

Redis SELECT / logical databases
https://redis.io/docs/latest/commands/select/
```

Ключевые design rules этой главы:

```text
separate database per unrelated project
least-privilege roles
runtime != migrator
no network postgres superuser
SCRAM authentication
no public database port
private-only admin UI
immutable runtime images
SOPS encrypted source-of-truth
small connection pools first
monitor before tuning
backup/restore still mandatory
```

---

## 34. Следующая рекомендуемая глава

Так как Chapters 10–11 сейчас отложены, следующий наиболее полезный слой для developer experience:

```text
13 — Database-aware deployment contract:
     automatic migrations,
     runtime/migrator secret injection,
     expand/contract migration rules,
     deploy health checks,
     safe application rollback boundaries
```

После неё CI/CD path станет полностью database-aware:

```text
git push
-> CI
-> immutable image
-> vulnerability scan
-> registry
-> deploy
-> migration
-> application restart
-> health check
-> logs / metrics / errors
```

Off-site backup + tested restore всё равно остаются обязательным P0 перед тем, как считать single-VPS production infrastructure окончательно завершённой.
