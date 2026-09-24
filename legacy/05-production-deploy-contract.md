# Глава 05. Production deploy contract

Эта глава создаёт единый контракт production-деплоя приложений:

- версия приложения задаётся точным Docker image digest;
- Compose-файлы и `deploy.json` хранятся в `/opt/ops`;
- runtime-состояние хранится вне Git в `/opt/apps`;
- приложение не публикует host-порты и подключается к общей сети `edge`;
- Caddy маршрутизирует публичный домен на Docker upstream;
- неудачный релиз автоматически откатывается;
- ручной rollback меняет местами текущий и предыдущий успешные релизы.

Команды главы рассчитаны на Bash-скрипты, но могут запускаться из интерактивного Zsh.

> Не вставляйте в терминал заголовки Markdown, разделители `---` и текст вокруг команд. В терминал копируются только содержимое блоков `bash`.

---

## 1. Загрузить общую конфигурацию

```bash
source /etc/vps-guide/config.env
```

Проверить обязательные значения:

```bash
: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${APPS_ROOT:?APPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"
: "${EDGE_NETWORK:?EDGE_NETWORK is not set}"
```

Создать каталоги:

```bash
sudo install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT/scripts/lib" \
  "$OPS_ROOT/compose/apps" \
  "$OPS_ROOT/compose/_templates" \
  "$OPS_ROOT/docs"

sudo install -d -o root -g root -m 0755 /etc/vps-guide
```

---

## 2. Настроить `.gitignore`

```bash
cat >> "$OPS_ROOT/.gitignore" <<'EOF_GITIGNORE'

# Local environment and secrets
.env
**/.env
!**/.env.example
secrets/

# Runtime deployment state
current.env
previous.env
history.tsv
deploy.lock

# Local backups
*.bak
*.bak.*
EOF_GITIGNORE

sort -u "$OPS_ROOT/.gitignore" -o "$OPS_ROOT/.gitignore"
```

---

## 3. Исправить базовый импорт Caddy

В Compose Caddy уже должен быть смонтирован весь каталог конфигурации:

```yaml
- ${OPS_ROOT}/config/caddy:/etc/caddy:ro
```

Отдельный вложенный mount `/etc/caddy/sites` не нужен.

Удалить его, если он был добавлен:

```bash
CADDY_COMPOSE="$OPS_ROOT/compose/edge/compose.yaml"

sed -i \
  '\#/config/caddy/sites:/etc/caddy/sites:ro#d' \
  "$CADDY_COMPOSE"
```

Импорт сайтов в основном `Caddyfile` должен использовать абсолютный путь:

```bash
CADDYFILE="$OPS_ROOT/config/caddy/Caddyfile"

python3 - "$CADDYFILE" <<'PY_CADDY_IMPORT'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

absolute = "import /etc/caddy/sites/*.caddy"

if absolute not in text:
    updated, count = re.subn(
        r"(?m)^([ \t]*)import[ \t]+sites/\*\.caddy[ \t]*$",
        r"\1import /etc/caddy/sites/*.caddy",
        text,
    )

    if count == 0:
        updated = text.rstrip() + "\n\n" + absolute + "\n"
    elif count != 1:
        raise SystemExit("Expected at most one relative sites import")

    path.write_text(updated, encoding="utf-8")
PY_CADDY_IMPORT

chmod 0644 "$CADDYFILE"
grep -n 'import.*/etc/caddy/sites' "$CADDYFILE"
```

Ожидаемая строка:

```caddyfile
import /etc/caddy/sites/*.caddy
```

---

## 4. Создать генератор платформенной конфигурации

```bash
cat > "$OPS_ROOT/scripts/platform-configure.sh" <<'EOF_PLATFORM_CONFIGURE'
#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env

PLATFORM_ENV="/etc/vps-guide/platform.env"

REGISTRY_HOST="${REGISTRY_HOST:-ghcr.io}"
REGISTRY_OWNER="${REGISTRY_OWNER:-}"
DEPLOY_APPS_ROOT="${DEPLOY_APPS_ROOT:-$OPS_ROOT/compose/apps}"
DEPLOY_STATE_ROOT="${DEPLOY_STATE_ROOT:-$APPS_ROOT}"
DEPLOY_LOCK_TIMEOUT="${DEPLOY_LOCK_TIMEOUT:-300}"
DEPLOY_WAIT_TIMEOUT="${DEPLOY_WAIT_TIMEOUT:-90}"
DEPLOY_HTTP_ATTEMPTS="${DEPLOY_HTTP_ATTEMPTS:-20}"
DEPLOY_HTTP_DELAY="${DEPLOY_HTTP_DELAY:-3}"
DEPLOY_HTTP_TIMEOUT="${DEPLOY_HTTP_TIMEOUT:-5}"
DEPLOY_HISTORY_LIMIT="${DEPLOY_HISTORY_LIMIT:-50}"
DEPLOY_TEST_STACK="${DEPLOY_TEST_STACK:-deploy-test}"
DEPLOY_TEST_DOMAIN="${DEPLOY_TEST_DOMAIN:-deploy-test.$BASE_DOMAIN}"
DEPLOY_TEST_UPSTREAM="${DEPLOY_TEST_UPSTREAM:-deploy-test-web:8080}"
DEPLOY_TEST_SERVICE="${DEPLOY_TEST_SERVICE:-app}"

[[ $EUID -eq 0 ]] || {
  printf 'Run this script through sudo.\n' >&2
  exit 1
}

install -d -o root -g root -m 0755 /etc/vps-guide
install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$DEPLOY_APPS_ROOT" \
  "$DEPLOY_STATE_ROOT"

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

write_export() {
  local name="$1"
  local value="$2"

  printf 'export %s=%q\n' "$name" "$value" >>"$tmp_file"
}

{
  printf '# Managed by %s\n' "$OPS_ROOT/scripts/platform-configure.sh"
  printf '# Contains no passwords, private keys or API tokens.\n'
} >"$tmp_file"

write_export REGISTRY_HOST "$REGISTRY_HOST"
write_export REGISTRY_OWNER "$REGISTRY_OWNER"
write_export DEPLOY_APPS_ROOT "$DEPLOY_APPS_ROOT"
write_export DEPLOY_STATE_ROOT "$DEPLOY_STATE_ROOT"
write_export DEPLOY_LOCK_TIMEOUT "$DEPLOY_LOCK_TIMEOUT"
write_export DEPLOY_WAIT_TIMEOUT "$DEPLOY_WAIT_TIMEOUT"
write_export DEPLOY_HTTP_ATTEMPTS "$DEPLOY_HTTP_ATTEMPTS"
write_export DEPLOY_HTTP_DELAY "$DEPLOY_HTTP_DELAY"
write_export DEPLOY_HTTP_TIMEOUT "$DEPLOY_HTTP_TIMEOUT"
write_export DEPLOY_HISTORY_LIMIT "$DEPLOY_HISTORY_LIMIT"
write_export DEPLOY_TEST_STACK "$DEPLOY_TEST_STACK"
write_export DEPLOY_TEST_DOMAIN "$DEPLOY_TEST_DOMAIN"
write_export DEPLOY_TEST_UPSTREAM "$DEPLOY_TEST_UPSTREAM"
write_export DEPLOY_TEST_SERVICE "$DEPLOY_TEST_SERVICE"

install -o root -g root -m 0644 "$tmp_file" "$PLATFORM_ENV"

printf 'Installed: %s\n' "$PLATFORM_ENV"
printf 'Load it with: source %s\n' "$PLATFORM_ENV"
EOF_PLATFORM_CONFIGURE

chmod 0750 "$OPS_ROOT/scripts/platform-configure.sh"
```

Установить `/etc/vps-guide/platform.env`:

```bash
sudo "$OPS_ROOT/scripts/platform-configure.sh"
source /etc/vps-guide/platform.env
```

Проверить:

```bash
printf '%s\n' \
  "DEPLOY_APPS_ROOT=$DEPLOY_APPS_ROOT" \
  "DEPLOY_STATE_ROOT=$DEPLOY_STATE_ROOT" \
  "DEPLOY_TEST_DOMAIN=$DEPLOY_TEST_DOMAIN" \
  "REGISTRY_HOST=$REGISTRY_HOST" \
  "REGISTRY_OWNER=${REGISTRY_OWNER:-not-configured-yet}"
```

Пустой `REGISTRY_OWNER` допустим, пока образы теста берутся из Docker Hub.

---

## 5. Создать общую библиотеку deployment-скриптов

```bash
cat > "$OPS_ROOT/scripts/lib/app-common.sh" <<'EOF_APP_COMMON'
#!/usr/bin/env bash

# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env
# shellcheck source=/etc/vps-guide/platform.env
source /etc/vps-guide/platform.env

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command is missing: $1"
}

require_file() {
  [[ -f "$1" && ! -L "$1" ]] || die "Required regular file is missing: $1"
}

validate_app_name() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] ||
    die "Invalid application name: $1"
}

validate_digest() {
  [[ "$1" =~ ^[a-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]] ||
    die "Image must be an exact sha256 digest: $1"
}

load_app_contract() {
  APP_NAME="$1"
  validate_app_name "$APP_NAME"

  APP_DIR="$DEPLOY_APPS_ROOT/$APP_NAME"
  COMPOSE_FILE="$APP_DIR/compose.yaml"
  DEPLOY_FILE="$APP_DIR/deploy.json"
  STATE_DIR="$DEPLOY_STATE_ROOT/$APP_NAME/deploy"
  CURRENT_ENV="$STATE_DIR/current.env"
  PREVIOUS_ENV="$STATE_DIR/previous.env"
  HISTORY_FILE="$STATE_DIR/history.tsv"
  LOCK_FILE="$STATE_DIR/deploy.lock"

  require_file "$COMPOSE_FILE"
  require_file "$DEPLOY_FILE"

  local parsed
  parsed="$(
    python3 - "$DEPLOY_FILE" <<'PY'
import json
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))

required = {
    "service": str,
    "policy": str,
    "health_url": str,
    "health_contains": str,
    "wait_timeout_seconds": int,
}

for key, expected_type in required.items():
    if key not in data:
        raise SystemExit(f"Missing deploy.json key: {key}")
    if not isinstance(data[key], expected_type):
        raise SystemExit(f"Invalid type for deploy.json key: {key}")

if data["policy"] not in {"public-app", "private-app"}:
    raise SystemExit("policy must be public-app or private-app")

if data["wait_timeout_seconds"] < 1:
    raise SystemExit("wait_timeout_seconds must be positive")

pairs = {
    "APP_SERVICE": data["service"],
    "APP_POLICY": data["policy"],
    "APP_HEALTH_URL": data["health_url"],
    "APP_HEALTH_CONTAINS": data["health_contains"],
    "APP_WAIT_TIMEOUT": str(data["wait_timeout_seconds"]),
}

for key, value in pairs.items():
    print(f"{key}={shlex.quote(value)}")
PY
  )" || die "Invalid deployment contract: $DEPLOY_FILE"

  eval "$parsed"

  [[ "$APP_SERVICE" =~ ^[a-zA-Z0-9._-]+$ ]] ||
    die "Invalid service name in deploy.json"

  install -d -m 2775 "$STATE_DIR"
  chgrp "$OPS_GROUP" "$STATE_DIR"
}

read_image_from_env() {
  local env_file="$1"
  local value

  [[ -f "$env_file" ]] || return 1

  value="$(
    sed -n 's/^APP_IMAGE=//p' "$env_file" |
      tail -n 1
  )"

  [[ -n "$value" ]] || return 1
  printf '%s\n' "$value"
}

write_release_env() {
  local destination="$1"
  local image="$2"
  local temp_file

  temp_file="$(mktemp "$STATE_DIR/.release.XXXXXX")"
  {
    printf 'APP_IMAGE=%s\n' "$image"
    printf 'APP_RELEASED_AT=%s\n' "$(date --iso-8601=seconds)"
  } >"$temp_file"

  chmod 0640 "$temp_file"
  chgrp "$OPS_GROUP" "$temp_file"
  mv -f "$temp_file" "$destination"
}

install_state_file() {
  local source_file="$1"
  local destination="$2"

  install -m 0640 "$source_file" "$destination"
  chgrp "$OPS_GROUP" "$destination"
}

compose() {
  local env_file="$1"
  shift

  docker compose \
    --project-name "$APP_NAME" \
    --project-directory "$APP_DIR" \
    --file "$COMPOSE_FILE" \
    --env-file "$env_file" \
    "$@"
}

validate_compose_policy() {
  local env_file="$1"
  local rendered_file

  rendered_file="$(mktemp "$STATE_DIR/.compose.XXXXXX")"

  if ! compose "$env_file" config --format json >"$rendered_file"; then
    rm -f "$rendered_file"
    die "Docker Compose validation failed"
  fi

  if ! python3 - "$APP_SERVICE" "$APP_POLICY" "$rendered_file" <<'PY'
import json
import sys
from pathlib import Path

service_name = sys.argv[1]
policy = sys.argv[2]
config_path = Path(sys.argv[3])
config = json.loads(config_path.read_text(encoding="utf-8"))

services = config.get("services", {})
if service_name not in services:
    raise SystemExit(f"Configured service not found: {service_name}")

service = services[service_name]

if policy == "public-app" and service.get("ports"):
    raise SystemExit("public-app must not publish host ports")

if service.get("privileged"):
    raise SystemExit("privileged containers are forbidden")

if service.get("network_mode") == "host":
    raise SystemExit("host network mode is forbidden")
PY
  then
    rm -f "$rendered_file"
    die "Compose production policy failed"
  fi

  rm -f "$rendered_file"
  printf 'Compose production policy passed: %s\n' "$APP_POLICY"
}

http_health_check() {
  local attempts="${1:-$DEPLOY_HTTP_ATTEMPTS}"
  local attempt
  local response

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if response="$(
      curl \
        --fail \
        --silent \
        --show-error \
        --max-time "$DEPLOY_HTTP_TIMEOUT" \
        "$APP_HEALTH_URL" 2>/dev/null
    )"; then
      if [[ -z "$APP_HEALTH_CONTAINS" ]] ||
        grep -Fq -- "$APP_HEALTH_CONTAINS" <<<"$response"; then
        printf 'HTTP health check passed: %s\n' "$APP_HEALTH_URL"
        return 0
      fi
    fi

    sleep "$DEPLOY_HTTP_DELAY"
  done

  printf 'HTTP health check failed after %s attempts: %s\n' \
    "$attempts" \
    "$APP_HEALTH_URL" >&2
  return 1
}

append_history() {
  local action="$1"
  local image="$2"

  printf '%s\t%s\t%s\t%s\n' \
    "$(date --iso-8601=seconds)" \
    "${SUDO_USER:-$USER}" \
    "$action" \
    "$image" >>"$HISTORY_FILE"

  if [[ -f "$HISTORY_FILE" ]]; then
    tail -n "$DEPLOY_HISTORY_LIMIT" "$HISTORY_FILE" \
      >"$HISTORY_FILE.tmp"
    mv -f "$HISTORY_FILE.tmp" "$HISTORY_FILE"
    chmod 0640 "$HISTORY_FILE"
    chgrp "$OPS_GROUP" "$HISTORY_FILE"
  fi
}

acquire_lock() {
  exec 9>"$LOCK_FILE"
  flock -w "$DEPLOY_LOCK_TIMEOUT" 9 ||
    die "Could not acquire deployment lock: $LOCK_FILE"
}

show_compose_ps() {
  local env_file="$1"

  if [[ -f "$env_file" ]]; then
    compose "$env_file" ps || true
  fi
}
EOF_APP_COMMON

chmod 0644 "$OPS_ROOT/scripts/lib/app-common.sh"
```

---

## 6. Создать команды deploy, rollback, health, status и compose

### `app-deploy.sh`

```bash
cat > "$OPS_ROOT/scripts/app-deploy.sh" <<'EOF_APP_DEPLOY'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/app-common.sh
source "$SCRIPT_DIR/lib/app-common.sh"

[[ $# -eq 2 ]] || {
  printf 'Usage: %s APP IMAGE@sha256:DIGEST\n' "$0" >&2
  exit 2
}

require_command docker
require_command curl
require_command flock
require_command python3

APP_NAME="$1"
NEW_IMAGE="$2"

validate_digest "$NEW_IMAGE"
load_app_contract "$APP_NAME"
acquire_lock

candidate_env="$(mktemp "$STATE_DIR/.candidate.XXXXXX")"
old_current="$(mktemp "$STATE_DIR/.current.XXXXXX")"
trap 'rm -f "$candidate_env" "$old_current"' EXIT

had_current=false
if [[ -f "$CURRENT_ENV" ]]; then
  cp -a "$CURRENT_ENV" "$old_current"
  had_current=true
fi

write_release_env "$candidate_env" "$NEW_IMAGE"

printf 'Validating Compose configuration...\n'
validate_compose_policy "$candidate_env"

printf 'Pulling exact image digest...\n'
docker pull "$NEW_IMAGE"

install_state_file "$candidate_env" "$CURRENT_ENV"

printf 'Starting release: %s\n' "$NEW_IMAGE"

deploy_ok=false
if compose "$CURRENT_ENV" \
    up -d --remove-orphans --wait \
    --wait-timeout "$APP_WAIT_TIMEOUT"; then
  if http_health_check; then
    deploy_ok=true
  fi
fi

if [[ "$deploy_ok" == true ]]; then
  if [[ "$had_current" == true ]]; then
    install_state_file "$old_current" "$PREVIOUS_ENV"
  else
    rm -f "$PREVIOUS_ENV"
  fi

  append_history deploy "$NEW_IMAGE"
  printf 'Deploy succeeded: %s\n' "$NEW_IMAGE"
  exit 0
fi

show_compose_ps "$CURRENT_ENV"
printf 'Deploy failed; starting automatic rollback for %s\n' "$APP_NAME" >&2

if [[ "$had_current" == true ]]; then
  install_state_file "$old_current" "$CURRENT_ENV"

  compose "$CURRENT_ENV" \
    up -d --remove-orphans --wait \
    --wait-timeout "$APP_WAIT_TIMEOUT"

  http_health_check ||
    die "Rollback release started, but external health check still fails"

  printf 'Automatic rollback succeeded.\n'
else
  compose "$CURRENT_ENV" down --remove-orphans || true
  rm -f "$CURRENT_ENV"
  printf 'First deploy removed because no previous release exists.\n'
fi

exit 1
EOF_APP_DEPLOY
```

### `app-rollback.sh`

```bash
cat > "$OPS_ROOT/scripts/app-rollback.sh" <<'EOF_APP_ROLLBACK'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/app-common.sh
source "$SCRIPT_DIR/lib/app-common.sh"

[[ $# -eq 1 ]] || {
  printf 'Usage: %s APP\n' "$0" >&2
  exit 2
}

require_command docker
require_command curl
require_command flock
require_command python3

APP_NAME="$1"
load_app_contract "$APP_NAME"
acquire_lock

[[ -f "$CURRENT_ENV" ]] ||
  die "Current successful release is not available for $APP_NAME"

[[ -f "$PREVIOUS_ENV" ]] ||
  die "Previous successful release is not available for $APP_NAME"

old_current="$(mktemp "$STATE_DIR/.current.XXXXXX")"
old_previous="$(mktemp "$STATE_DIR/.previous.XXXXXX")"
trap 'rm -f "$old_current" "$old_previous"' EXIT

cp -a "$CURRENT_ENV" "$old_current"
cp -a "$PREVIOUS_ENV" "$old_previous"

validate_compose_policy "$old_previous"

install_state_file "$old_previous" "$CURRENT_ENV"

install_state_file "$old_current" "$PREVIOUS_ENV"

rollback_image="$(read_image_from_env "$CURRENT_ENV")"

printf 'Starting rollback: %s\n' "$rollback_image"

if compose "$CURRENT_ENV" \
    up -d --remove-orphans --wait \
    --wait-timeout "$APP_WAIT_TIMEOUT" &&
  http_health_check; then
  append_history rollback "$rollback_image"
  printf 'Rollback succeeded: %s\n' "$rollback_image"
  exit 0
fi

printf 'Rollback failed; restoring the release that was active before rollback.\n' >&2

install_state_file "$old_current" "$CURRENT_ENV"

install_state_file "$old_previous" "$PREVIOUS_ENV"

compose "$CURRENT_ENV" \
  up -d --remove-orphans --wait \
  --wait-timeout "$APP_WAIT_TIMEOUT"

http_health_check ||
  die "Original release was restored, but external health check fails"

exit 1
EOF_APP_ROLLBACK
```

### `app-health.sh`

```bash
cat > "$OPS_ROOT/scripts/app-health.sh" <<'EOF_APP_HEALTH'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/app-common.sh
source "$SCRIPT_DIR/lib/app-common.sh"

[[ $# -ge 1 && $# -le 2 ]] || {
  printf 'Usage: %s APP [ATTEMPTS]\n' "$0" >&2
  exit 2
}

require_command curl
require_command python3

APP_NAME="$1"
ATTEMPTS="${2:-$DEPLOY_HTTP_ATTEMPTS}"

[[ "$ATTEMPTS" =~ ^[1-9][0-9]*$ ]] ||
  die "ATTEMPTS must be a positive integer"

load_app_contract "$APP_NAME"

[[ -f "$CURRENT_ENV" ]] ||
  die "No active release for $APP_NAME"

http_health_check "$ATTEMPTS"
EOF_APP_HEALTH
```

### `app-status.sh`

```bash
cat > "$OPS_ROOT/scripts/app-status.sh" <<'EOF_APP_STATUS'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/app-common.sh
source "$SCRIPT_DIR/lib/app-common.sh"

[[ $# -eq 1 ]] || {
  printf 'Usage: %s APP\n' "$0" >&2
  exit 2
}

require_command docker
require_command python3

APP_NAME="$1"
load_app_contract "$APP_NAME"

printf 'Application: %s\n' "$APP_NAME"
printf 'Compose:     %s\n' "$COMPOSE_FILE"
printf 'State:       %s\n' "$STATE_DIR"
printf 'Health URL:  %s\n' "$APP_HEALTH_URL"

if current_image="$(read_image_from_env "$CURRENT_ENV")"; then
  printf 'Current:     %s\n' "$current_image"
else
  printf 'Current:     not deployed\n'
fi

if previous_image="$(read_image_from_env "$PREVIOUS_ENV")"; then
  printf 'Previous:    %s\n' "$previous_image"
else
  printf 'Previous:    not available\n'
fi

printf '\n'

if [[ -f "$CURRENT_ENV" ]]; then
  show_compose_ps "$CURRENT_ENV"
else
  docker compose \
    --project-name "$APP_NAME" \
    --project-directory "$APP_DIR" \
    --file "$COMPOSE_FILE" \
    ps || true
fi

if [[ -s "$HISTORY_FILE" ]]; then
  printf '\nRecent history:\n'
  tail -n 10 "$HISTORY_FILE"
fi
EOF_APP_STATUS
```

### `app-compose.sh`

```bash
cat > "$OPS_ROOT/scripts/app-compose.sh" <<'EOF_APP_COMPOSE'
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/app-common.sh
source "$SCRIPT_DIR/lib/app-common.sh"

[[ $# -ge 2 ]] || {
  printf 'Usage: %s APP COMPOSE_ARGS...\n' "$0" >&2
  exit 2
}

require_command docker
require_command python3

APP_NAME="$1"
shift

load_app_contract "$APP_NAME"

[[ -f "$CURRENT_ENV" ]] ||
  die "No active release for $APP_NAME"

compose "$CURRENT_ENV" "$@"
EOF_APP_COMPOSE
```

Назначить права:

```bash
chmod 0750 \
  "$OPS_ROOT/scripts/app-deploy.sh" \
  "$OPS_ROOT/scripts/app-rollback.sh" \
  "$OPS_ROOT/scripts/app-health.sh" \
  "$OPS_ROOT/scripts/app-status.sh" \
  "$OPS_ROOT/scripts/app-compose.sh"
```

Директива:

```bash
# shellcheck source=lib/app-common.sh
```

перед динамическим `source` обязательна. Благодаря ей ShellCheck не выдаёт ложный `SC1091`.

---

## 7. Создать команды управления Caddy-сайтами

### `caddy-add-site.sh`

```bash
cat > "$OPS_ROOT/scripts/caddy-add-site.sh" <<'EOF_CADDY_ADD'
#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env

[[ $# -eq 2 ]] || {
  printf 'Usage: %s DOMAIN UPSTREAM\n' "$0" >&2
  exit 2
}

DOMAIN="${1,,}"
UPSTREAM="$2"

[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || {
  printf 'Invalid domain: %s\n' "$DOMAIN" >&2
  exit 1
}

[[ "$UPSTREAM" =~ ^[a-zA-Z0-9._-]+:[0-9]{1,5}$ ]] || {
  printf 'Invalid upstream: %s\n' "$UPSTREAM" >&2
  exit 1
}

SITE_DIR="$OPS_ROOT/config/caddy/sites"
SITE_FILE="$SITE_DIR/$DOMAIN.caddy"
BACKUP_FILE="$(mktemp)"
HAD_FILE=false

trap 'rm -f "$BACKUP_FILE"' EXIT

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 "$SITE_DIR"

if [[ -f "$SITE_FILE" ]]; then
  cp -a "$SITE_FILE" "$BACKUP_FILE"
  HAD_FILE=true
fi

cat >"$SITE_FILE" <<EOF_SITE
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

cd "$OPS_ROOT/compose/edge"

if ! docker compose run --rm --no-deps caddy \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  if [[ "$HAD_FILE" == true ]]; then
    install -m 0644 "$BACKUP_FILE" "$SITE_FILE"
  else
    rm -f "$SITE_FILE"
  fi

  printf 'Validation failed; site change reverted.\n' >&2
  exit 1
fi

if ! docker compose exec -T -w /etc/caddy caddy \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  if [[ "$HAD_FILE" == true ]]; then
    install -m 0644 "$BACKUP_FILE" "$SITE_FILE"
  else
    rm -f "$SITE_FILE"
  fi

  docker compose exec -T -w /etc/caddy caddy \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true

  printf 'Reload failed; site change reverted.\n' >&2
  exit 1
fi

printf 'Configured: https://%s -> %s\n' "$DOMAIN" "$UPSTREAM"
EOF_CADDY_ADD
```

### `caddy-remove-site.sh`

Аргументом является **имя файла без `.caddy`**, а не обязательно полный домен.

Например:

- `deploy-test.sasha.host.caddy` удаляется аргументом `deploy-test.sasha.host`;
- legacy-файл `edge-test.caddy` удаляется аргументом `edge-test`.

```bash
cat > "$OPS_ROOT/scripts/caddy-remove-site.sh" <<'EOF_CADDY_REMOVE'
#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env

[[ $# -eq 1 ]] || {
  printf 'Usage: %s SITE_ID\n' "$0" >&2
  printf 'SITE_ID is the filename without the .caddy suffix.\n' >&2
  exit 2
}

SITE_ID="${1%.caddy}"

[[ "$SITE_ID" =~ ^[a-zA-Z0-9._-]+$ ]] || {
  printf 'Invalid Caddy site ID: %s\n' "$SITE_ID" >&2
  exit 1
}

SITE_FILE="$OPS_ROOT/config/caddy/sites/$SITE_ID.caddy"
BACKUP_FILE="$(mktemp)"
trap 'rm -f "$BACKUP_FILE"' EXIT

[[ -f "$SITE_FILE" && ! -L "$SITE_FILE" ]] || {
  printf 'Caddy site not found: %s\n' "$SITE_FILE" >&2
  exit 1
}

cp -a "$SITE_FILE" "$BACKUP_FILE"
rm -f "$SITE_FILE"

cd "$OPS_ROOT/compose/edge"

if ! docker compose run --rm --no-deps caddy \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  install -m 0644 "$BACKUP_FILE" "$SITE_FILE"
  printf 'Validation failed; site restored.\n' >&2
  exit 1
fi

if ! docker compose exec -T -w /etc/caddy caddy \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  install -m 0644 "$BACKUP_FILE" "$SITE_FILE"

  docker compose exec -T -w /etc/caddy caddy \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true

  printf 'Reload failed; site restored.\n' >&2
  exit 1
fi

printf 'Removed Caddy site: %s\n' "$SITE_ID"
EOF_CADDY_REMOVE
```

Назначить права:

```bash
chmod 0750 \
  "$OPS_ROOT/scripts/caddy-add-site.sh" \
  "$OPS_ROOT/scripts/caddy-remove-site.sh"
```

---

## 8. Проверить Bash и ShellCheck

```bash
(
  cd "$OPS_ROOT/scripts"

  bash -n \
    platform-configure.sh \
    app-deploy.sh \
    app-rollback.sh \
    app-health.sh \
    app-status.sh \
    app-compose.sh \
    caddy-add-site.sh \
    caddy-remove-site.sh \
    lib/app-common.sh

  shellcheck -x \
    platform-configure.sh \
    app-deploy.sh \
    app-rollback.sh \
    app-health.sh \
    app-status.sh \
    app-compose.sh \
    caddy-add-site.sh \
    caddy-remove-site.sh \
    lib/app-common.sh
)
```

Проверка должна завершиться без `SC1091`.

---

## 9. Создать тестовое production-приложение

```bash
source /etc/vps-guide/config.env
source /etc/vps-guide/platform.env

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK" \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/site"
```

Создать Compose:

```bash
cat > "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/compose.yaml" <<'EOF_DEPLOY_TEST_COMPOSE'
services:
  app:
    image: ${APP_IMAGE:?Set APP_IMAGE}
    command:
      - httpd
      - -f
      - -p
      - "8080"
      - -h
      - /www

    restart: unless-stopped

    volumes:
      - ./site:/www:ro

    healthcheck:
      test:
        - CMD
        - wget
        - -q
        - -O
        - "-"
        - http://127.0.0.1:8080/health
      interval: 5s
      timeout: 3s
      retries: 6
      start_period: 5s

    security_opt:
      - no-new-privileges=true

    cap_drop:
      - ALL

    read_only: true

    tmpfs:
      - /tmp:size=8m,mode=1777

    pids_limit: 64
    mem_limit: 64m
    cpus: "0.25"

    labels:
      ops.managed-by: docker-compose
      ops.role: production-deploy-test
      ops.host-published: "false"

    networks:
      edge:
        aliases:
          - deploy-test-web

networks:
  edge:
    external: true
    name: ${EDGE_NETWORK:?Set EDGE_NETWORK}
EOF_DEPLOY_TEST_COMPOSE
```

Создать deployment contract:

```bash
cat > "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/deploy.json" <<EOF_DEPLOY_TEST_JSON
{
  "service": "${DEPLOY_TEST_SERVICE}",
  "policy": "public-app",
  "health_url": "https://${DEPLOY_TEST_DOMAIN}/health",
  "health_contains": "deploy-test-ok",
  "wait_timeout_seconds": 60
}
EOF_DEPLOY_TEST_JSON
```

Создать тестовый сайт:

```bash
cat > "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/site/index.html" <<'EOF_DEPLOY_TEST_INDEX'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Production deploy test</title>
</head>
<body>
  <main>
    <h1>Production deploy работает</h1>
    <p>Приложение запущено по точному Docker image digest.</p>
  </main>
</body>
</html>
EOF_DEPLOY_TEST_INDEX

printf 'deploy-test-ok\n' \
  > "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/site/health"
```

Права:

```bash
find "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK" \
  -type d -exec chmod 0755 {} +

chmod 0644 \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/compose.yaml" \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/deploy.json" \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/site/index.html" \
  "$DEPLOY_APPS_ROOT/$DEPLOY_TEST_STACK/site/health"
```

---

## 10. Добавить production-маршрут в Caddy

```bash
"$OPS_ROOT/scripts/caddy-add-site.sh" \
  "$DEPLOY_TEST_DOMAIN" \
  "$DEPLOY_TEST_UPSTREAM"
```

Проверить файл на хосте:

```bash
cat "$OPS_ROOT/config/caddy/sites/$DEPLOY_TEST_DOMAIN.caddy"
```

Проверить, что файл виден внутри контейнера:

```bash
CADDY_CONTAINER="$(
  docker ps \
    --filter "label=com.docker.compose.project=${CADDY_STACK}" \
    --filter "label=com.docker.compose.service=caddy" \
    --format '{{.Names}}' |
  head -n 1
)"

docker exec "$CADDY_CONTAINER" \
  sh -eu -c 'ls -la /etc/caddy/sites && sed -n "1,160p" /etc/caddy/sites/*.caddy'
```

Проверить Caddy:

```bash
docker exec "$CADDY_CONTAINER" \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

В выводе не должно быть:

```text
No files matching import glob pattern
```

---

## 11. Проверить origin до запуска приложения

Проверять Caddy из самого VPS нужно через loopback, а не через публичный IP:

```bash
curl \
  --insecure \
  --silent \
  --show-error \
  --output /dev/null \
  --connect-timeout 5 \
  --resolve "${DEPLOY_TEST_DOMAIN}:443:127.0.0.1" \
  --write-out 'Local Caddy HTTP: %{http_code}\n' \
  "https://${DEPLOY_TEST_DOMAIN}/"
```

До запуска upstream ожидается:

```text
Local Caddy HTTP: 502
```

Код `502` здесь нормален: Caddy работает, но приложение ещё не запущено.

Код `000` означает, что HTTPS listener Caddy не работает.

Публичная проверка до деплоя:

```bash
curl \
  --silent \
  --show-error \
  --output /dev/null \
  --connect-timeout 10 \
  --write-out 'Public HTTP: %{http_code}\n' \
  "https://${DEPLOY_TEST_DOMAIN}/"
```

Ожидается `502`, но не `521`.

---

## 12. Получить два точных image digest

```bash
docker pull busybox:1.37.0
docker pull busybox:1.38.0

BUSYBOX_137_DIGEST="$(
  docker image inspect busybox:1.37.0 \
    --format '{{index .RepoDigests 0}}'
)"

BUSYBOX_138_DIGEST="$(
  docker image inspect busybox:1.38.0 \
    --format '{{index .RepoDigests 0}}'
)"

[[ "$BUSYBOX_137_DIGEST" =~ @sha256:[a-f0-9]{64}$ ]]
[[ "$BUSYBOX_138_DIGEST" =~ @sha256:[a-f0-9]{64}$ ]]

printf '%s\n' \
  "BUSYBOX_137_DIGEST=$BUSYBOX_137_DIGEST" \
  "BUSYBOX_138_DIGEST=$BUSYBOX_138_DIGEST"
```

---

## 13. Выполнить первый релиз

```bash
"$OPS_ROOT/scripts/app-deploy.sh" \
  "$DEPLOY_TEST_STACK" \
  "$BUSYBOX_137_DIGEST"
```

Проверить:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3

curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health"

printf '\n'
```

Ожидается:

```text
deploy-test-ok
```

Первый релиз считается успешным только после внешней HTTP-проверки.

---

## 14. Выполнить второй релиз

```bash
"$OPS_ROOT/scripts/app-deploy.sh" \
  "$DEPLOY_TEST_STACK" \
  "$BUSYBOX_138_DIGEST"
```

Проверить:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3
```

В статусе должны присутствовать:

- `Current` — digest BusyBox `1.38.0`;
- `Previous` — digest BusyBox `1.37.0`.

---

## 15. Проверить ручной rollback

Rollback запускается только после двух успешных релизов:

```bash
"$OPS_ROOT/scripts/app-rollback.sh" "$DEPLOY_TEST_STACK"
```

Проверить:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3

curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'
```

После rollback:

- `Current` должен снова указывать на BusyBox `1.37.0`;
- `Previous` должен указывать на BusyBox `1.38.0`.

История:

```bash
column -t -s $'\t' \
  "$DEPLOY_STATE_ROOT/$DEPLOY_TEST_STACK/deploy/history.tsv"
```

---

## 16. Удалить legacy smoke и edge-test

Сначала удалить Caddy site, и только затем удалять переменные и Compose-проект.

Legacy-файл называется `edge-test.caddy`, поэтому аргумент — `edge-test`:

```bash
if [[ -f "$OPS_ROOT/config/caddy/sites/edge-test.caddy" ]]; then
  "$OPS_ROOT/scripts/caddy-remove-site.sh" edge-test
fi
```

После успешного reload остановить старые проекты:

```bash
if [[ -f "$OPS_ROOT/compose/edge-test/compose.yaml" ]]; then
  docker compose \
    --file "$OPS_ROOT/compose/edge-test/compose.yaml" \
    --project-directory "$OPS_ROOT/compose/edge-test" \
    down --remove-orphans
fi

if [[ -f "$OPS_ROOT/compose/_smoke/compose.yaml" ]]; then
  docker compose \
    --file "$OPS_ROOT/compose/_smoke/compose.yaml" \
    --project-directory "$OPS_ROOT/compose/_smoke" \
    down --remove-orphans
fi

rm -rf -- \
  "$OPS_ROOT/compose/edge-test" \
  "$OPS_ROOT/compose/_smoke"
```

Удалить legacy-переменные из edge Compose и env-файлов:

```bash
python3 - \
  "$OPS_ROOT/compose/edge/compose.yaml" \
  "$OPS_ROOT/compose/edge/.env" \
  "$OPS_ROOT/compose/edge/.env.example" <<'PY_REMOVE_EDGE_TEST'
from pathlib import Path
import sys

compose_path, env_path, example_path = map(Path, sys.argv[1:])

compose = compose_path.read_text(encoding="utf-8")
compose = "\n".join(
    line
    for line in compose.splitlines()
    if "EDGE_TEST_DOMAIN:" not in line
    and "EDGE_TEST_UPSTREAM:" not in line
) + "\n"
compose_path.write_text(compose, encoding="utf-8")

for path in (env_path, example_path):
    if not path.exists():
        continue

    content = "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("EDGE_TEST_DOMAIN=")
        and not line.startswith("EDGE_TEST_UPSTREAM=")
    ) + "\n"

    path.write_text(content, encoding="utf-8")
PY_REMOVE_EDGE_TEST
```

Проверить конфигурацию **до** пересоздания контейнера:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose config --quiet

docker compose run --rm --no-deps caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Только после успешной validation:

```bash
docker compose \
  up -d --force-recreate --remove-orphans \
  --wait --wait-timeout 60

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile

docker compose ps
```

Проверить, что Caddy не находится в restart-loop:

```bash
docker ps --filter name=edge-caddy-1 \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

docker logs --tail 100 edge-caddy-1
```

После cleanup production-приложение должно остаться доступным:

```bash
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3
```

---

## 17. Финальная проверка production contract

```bash
source /etc/vps-guide/config.env
source /etc/vps-guide/platform.env

"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3

docker ps --format \
  'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

sudo ss -lntup | grep -E ':(80|443)\b'
sudo systemctl --failed
```

Дополнительно:

```bash
curl \
  --insecure \
  --fail \
  --silent \
  --show-error \
  --resolve "${DEPLOY_TEST_DOMAIN}:443:127.0.0.1" \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'

curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'
```

---

## 18. Обновить README инфраструктуры

Внешний блок использует четыре обратные кавычки. Благодаря этому тройные Markdown-fence внутри heredoc отображаются корректно и не закрывают блок инструкции раньше времени.

````bash
cat > "$OPS_ROOT/README.md" <<'EOF_OPS_README'
# VPS operations repository

## Layout

- `compose/edge/` — global Caddy edge
- `compose/apps/` — production application Compose projects
- `compose/_templates/` — reference templates
- `config/` — versioned service configuration
- `scripts/` — operational scripts
- `scripts/lib/` — shared shell libraries
- `docs/` — local runbooks and architecture notes
- `secrets/` — never committed

## Application contract

Versioned:

```text
/opt/ops/compose/apps/<app>/compose.yaml
/opt/ops/compose/apps/<app>/deploy.json
```

Runtime state:

```text
/opt/apps/<app>/deploy/current.env
/opt/apps/<app>/deploy/previous.env
/opt/apps/<app>/deploy/history.tsv
/opt/apps/<app>/deploy/deploy.lock
```

Persistent data:

```text
/opt/data/<app>/
```

## Commands

```bash
/opt/ops/scripts/app-deploy.sh APP IMAGE@sha256:DIGEST
/opt/ops/scripts/app-rollback.sh APP
/opt/ops/scripts/app-status.sh APP
/opt/ops/scripts/app-health.sh APP
/opt/ops/scripts/app-compose.sh APP logs --tail=100 SERVICE
```

Production does not build application source code. CI builds and scans images; the VPS pulls an exact image digest.
EOF_OPS_README
````

Проверить файл:

```bash
sed -n '1,220p' "$OPS_ROOT/README.md"
```

---

## 19. Git-фиксация

Удалить локальные резервные копии. Они не должны попадать в репозиторий:

```bash
find "$OPS_ROOT/compose/edge" \
  -maxdepth 1 \
  -type f \
  -name '*.bak.*' \
  -print \
  -delete
```

Если backup уже отслеживается Git:

```bash
git -C "$OPS_ROOT" rm --ignore-unmatch \
  'compose/edge/compose.yaml.bak.'*
```

Зафиксировать удаления старых проектов:

```bash
git -C "$OPS_ROOT" rm -r --ignore-unmatch \
  compose/edge-test \
  compose/_smoke
```

Добавлять файлы нужно явно, без `git add -A`:

```bash
git -C "$OPS_ROOT" add \
  .gitignore \
  README.md \
  compose/edge/compose.yaml \
  compose/edge/.env.example \
  compose/apps/deploy-test \
  config/caddy/Caddyfile \
  config/caddy/sites \
  scripts/platform-configure.sh \
  scripts/lib/app-common.sh \
  scripts/app-deploy.sh \
  scripts/app-rollback.sh \
  scripts/app-health.sh \
  scripts/app-status.sh \
  scripts/app-compose.sh \
  scripts/caddy-add-site.sh \
  scripts/caddy-remove-site.sh
```

Проверки перед commit:

```bash
git -C "$OPS_ROOT" diff --cached --stat
git -C "$OPS_ROOT" diff --cached --check

if git -C "$OPS_ROOT" diff --cached --name-only |
  grep -E '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|.*\.bak\..*)$'; then
  printf 'Runtime env or backup unexpectedly staged\n' >&2
  exit 1
fi
```

Commit:

```bash
git -C "$OPS_ROOT" commit \
  -m 'Add digest-based production deploy contract'
```

Проверить чистоту рабочего дерева:

```bash
git -C "$OPS_ROOT" status --short
```

---

## 20. Критерии завершения главы

Глава считается завершённой только когда одновременно выполняются все условия:

1. `shellcheck` проходит без `SC1091`.
2. Caddy имеет статус `Up ... (healthy)`, а не `Restarting`.
3. В Caddy отсутствует предупреждение о пустом `sites/*.caddy`.
4. Локальный и публичный `/health` возвращают `deploy-test-ok`.
5. Первый и второй digest-релизы успешно завершились.
6. Rollback вернул первый digest.
7. `history.tsv` содержит операции `deploy`, `deploy`, `rollback`.
8. Runtime-файлы и backup-файлы не отслеживаются Git.
9. `git status --short` пуст.
10. `systemctl --failed` не показывает failed units.

### Диагностика кодов

- `Local Caddy HTTP: 000` — Caddy не принимает локальное HTTPS-соединение.
- `Local Caddy HTTP: 502` — Caddy работает, но upstream отсутствует или недоступен.
- локально `200`, публично `521` — проверять состояние Caddy, DNS origin и лишние `AAAA`-записи.
- контейнер приложения `healthy`, но внешний health-check падает — сначала проверять Caddy и публичный маршрут, а не приложение.
