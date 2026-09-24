# Глава 07. Observability: Grafana, Prometheus, Loki, Alloy и production alerts

Эта глава добавляет централизованную наблюдаемость поверх инфраструктуры, завершённой в главе 06:

- Prometheus собирает host/container/service metrics;
- node_exporter отдаёт метрики Ubuntu host;
- cAdvisor отдаёт метрики Docker containers;
- Blackbox Exporter проверяет публичные HTTPS endpoints и TLS certificates;
- Grafana Alloy собирает Docker stdout/stderr logs;
- Loki хранит и индексирует logs с ограниченным retention;
- Grafana показывает metrics и logs в одном private UI;
- Alertmanager отправляет firing/resolved alerts в Telegram;
- Grafana публикуется **только внутри Tailscale**, через Tailscale Serve;
- Prometheus, Loki, Alertmanager и Alloy не публикуются в Internet;
- Docker socket не монтируется в Alloy напрямую;
- все persistent data остаются вне Git в `/opt/data/observability`;
- все secrets остаются вне Git;
- все несекретные server-specific variables продолжают храниться в едином `$HOME/config.env`;
- upstream images используются только по exact digest `@sha256:...`.

> Команды рассчитаны на Ubuntu 24.04 после успешно завершённой главы 06.
>
> Не вставляйте в терминал заголовки Markdown, разделители `---`, поясняющий текст и строки ожидаемого вывода. В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, не переходите к следующему номеру шага, пока причина не устранена.

---

## 0. Что именно строим

```text
Docker containers
 stdout/stderr
      |
      v
Docker Engine socket
      |
      | read-only API subset
      v
socket-proxy ---- internal docker-api network ---- Grafana Alloy
                                                  |
                                                  | Loki push API
                                                  v
                                                Loki
                                                  |
                                                  +--------------------+
                                                                       |
Ubuntu host -> node_exporter -> Prometheus --------------------------> Grafana
Docker      -> cAdvisor ------> Prometheus ----------------------------+
HTTPS sites -> blackbox ------> Prometheus ----------------------------+
                                  |
                                  | alert rules
                                  v
                             Alertmanager
                                  |
                                  v
                               Telegram

Laptop/PC -> Tailscale -> HTTPS :8443 -> Tailscale Serve
                                      -> 127.0.0.1:3000 -> Grafana

Internet -> Caddy :80/:443 -> public applications
Internet -X-> Grafana / Prometheus / Loki / Alertmanager / Alloy
```

Для одного VPS `2 vCPU / 4 GB RAM / 60 GB` используется **single-node observability stack**.

В этой главе намеренно не добавляются:

- Tempo;
- OpenTelemetry traces;
- GlitchTip;
- PostgreSQL monitoring;
- backup monitoring;
- Kubernetes-oriented components.

Они будут добавляться только после стабилизации базовых metrics/logs/alerts.

---

## 1. Проверить checkpoint главы 06

Загрузить единую конфигурацию:

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"
: "${DEPLOY_TEST_STACK:?DEPLOY_TEST_STACK is not set}"
: "${DEPLOY_TEST_DOMAIN:?DEPLOY_TEST_DOMAIN is not set}"
```

Проверить пользователя:

```bash
[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run this chapter as %s, not as %s\n' \
    "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}
```

Git repository должен быть чистым:

```bash
test -z "$(git -C "$OPS_ROOT" status --porcelain)" || {
  printf 'ERROR: %s has uncommitted changes\n' "$OPS_ROOT" >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

git -C "$OPS_ROOT" status --short
git -C "$OPS_ROOT" log -5 --oneline
```

Проверить GitHub remote:

```bash
git -C "$OPS_ROOT" remote get-url origin
git -C "$OPS_ROOT" ls-remote --exit-code origin refs/heads/main >/dev/null
```

Проверить, что local `main` синхронизирован с `origin/main`:

```bash
git -C "$OPS_ROOT" fetch --quiet origin main

LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"

[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ\n' >&2
  printf 'local:  %s\nremote: %s\n' "$LOCAL_SHA" "$REMOTE_SHA" >&2
  exit 1
}
```

Проверить production deploy contract:

```bash
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3

curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'
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

Проверить host:

```bash
sudo systemctl --failed

df -h /
free -h
```

На этом VPS перед установкой observability желательно иметь не менее `10 GB` свободного места:

```bash
FREE_GIB="$(df -BG --output=avail / | tail -n 1 | tr -dc '0-9')"

(( FREE_GIB >= 10 )) || {
  printf 'ERROR: less than 10 GiB free on /: %s GiB\n' "$FREE_GIB" >&2
  exit 1
}

printf 'Free disk: %s GiB\n' "$FREE_GIB"
```

### Исправленная secret/runtime проверка из главы 06

В финале главы 06 использовался PCRE-фрагмент `(?:...)` вместе с обычным `grep -E`. GNU ERE не поддерживает non-capturing group `(?:...)`, поэтому такая проверка могла вывести warning и не дать ожидаемую гарантию.

Повторить проверку с корректным ERE:

```bash
if git -C "$OPS_ROOT" ls-files |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|config\.json|.*\.bak(\..*)?)$'; then
  printf 'ERROR: suspicious runtime/credential/backup file is tracked\n' >&2
  exit 1
fi

printf 'Tracked runtime/credential check passed.\n'
```

Проверить staged files той же исправленной регуляркой:

```bash
if git -C "$OPS_ROOT" \
    diff --cached --diff-filter=ACMR --name-only |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|config\.json|.*\.bak(\..*)?)$'; then
  printf 'ERROR: runtime, credential or backup file is staged\n' >&2
  exit 1
fi

printf 'Staged runtime/credential check passed.\n'
```

> Ошибка `zsh: read-only variable: status` из теста главы 06 также относится только к тексту старой команды: в Zsh имя `status` зарезервировано. Persistent state сервера она не меняет. В новых скриптах используется `exit_code`.

Не продолжать, пока все проверки этого раздела не проходят.

---

## 2. Зафиксировать observability defaults и exact image digests

Создать versioned configure script:

````bash
cat > "$OPS_ROOT/scripts/chapter-07-configure.sh" <<'EOF_CH07_CONFIG'
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
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

command -v docker >/dev/null
command -v jq >/dev/null
command -v python3 >/dev/null
command -v tailscale >/dev/null

docker network inspect "$OBSERVABILITY_NETWORK" >/dev/null

OPS_GID="$(getent group "$OPS_GROUP" | cut -d: -f3)"

[[ "$OPS_GID" =~ ^[0-9]+$ ]] || {
  printf 'ERROR: cannot resolve GID for group %s\n' "$OPS_GROUP" >&2
  exit 1
}

OBSERVABILITY_SUBNET="$(
  docker network inspect "$OBSERVABILITY_NETWORK" \
    --format '{{(index .IPAM.Config 0).Subnet}}'
)"

OBSERVABILITY_GATEWAY="$(
  docker network inspect "$OBSERVABILITY_NETWORK" \
    --format '{{(index .IPAM.Config 0).Gateway}}'
)"

[[ "$OBSERVABILITY_SUBNET" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] || {
  printf 'ERROR: unexpected observability subnet: %s\n' \
    "$OBSERVABILITY_SUBNET" >&2
  exit 1
}

[[ "$OBSERVABILITY_GATEWAY" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  printf 'ERROR: unexpected observability gateway: %s\n' \
    "$OBSERVABILITY_GATEWAY" >&2
  exit 1
}

TAILSCALE_DNS_NAME="$(
  tailscale status --json |
    jq -r '.Self.DNSName // empty' |
    sed 's/\.$//'
)"

[[ -n "$TAILSCALE_DNS_NAME" ]] || {
  printf 'ERROR: Tailscale DNS name was not found\n' >&2
  exit 1
}

OBSERVABILITY_STACK="observability"
OBSERVABILITY_ROOT="$OPS_ROOT/compose/$OBSERVABILITY_STACK"
OBSERVABILITY_CONFIG_ROOT="$OPS_ROOT/config/$OBSERVABILITY_STACK"
OBSERVABILITY_DATA_ROOT="$DATA_ROOT/$OBSERVABILITY_STACK"
OBSERVABILITY_SECRETS_ROOT="$OBSERVABILITY_DATA_ROOT/secrets"

GRAFANA_TAILSCALE_PORT="8443"
GRAFANA_ADMIN_USER="$ADMIN_USER"
GRAFANA_URL="https://${TAILSCALE_DNS_NAME}:${GRAFANA_TAILSCALE_PORT}"

PROMETHEUS_RETENTION_TIME="15d"
PROMETHEUS_RETENTION_SIZE="6GB"
LOKI_RETENTION_PERIOD="336h"

GRAFANA_TAG="grafana/grafana:13.1.1"
PROMETHEUS_TAG="prom/prometheus:v3.11.3"
LOKI_TAG="grafana/loki:3.7.4"
ALLOY_TAG="grafana/alloy:v1.18.0"
ALERTMANAGER_TAG="prom/alertmanager:v0.32.1"
NODE_EXPORTER_TAG="prom/node-exporter:v1.11.1"
CADVISOR_TAG="ghcr.io/google/cadvisor:v0.60.5"
BLACKBOX_EXPORTER_TAG="prom/blackbox-exporter:v0.28.0"
DOCKER_SOCKET_PROXY_TAG="ghcr.io/tecnativa/docker-socket-proxy:v0.5.0"

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
    printf 'ERROR: exact digest was not resolved for %s\n' "$tag" >&2
    printf 'Resolved value: %s\n' "$image_ref" >&2
    exit 1
  }

  printf '%s\n' "$image_ref"
}

GRAFANA_IMAGE="$(resolve_image "$GRAFANA_TAG")"
PROMETHEUS_IMAGE="$(resolve_image "$PROMETHEUS_TAG")"
LOKI_IMAGE="$(resolve_image "$LOKI_TAG")"
ALLOY_IMAGE="$(resolve_image "$ALLOY_TAG")"
ALERTMANAGER_IMAGE="$(resolve_image "$ALERTMANAGER_TAG")"
NODE_EXPORTER_IMAGE="$(resolve_image "$NODE_EXPORTER_TAG")"
CADVISOR_IMAGE="$(resolve_image "$CADVISOR_TAG")"
BLACKBOX_EXPORTER_IMAGE="$(resolve_image "$BLACKBOX_EXPORTER_TAG")"
DOCKER_SOCKET_PROXY_IMAGE="$(resolve_image "$DOCKER_SOCKET_PROXY_TAG")"

python3 - \
  "$VPS_GUIDE_CONFIG" \
  "$OPS_GID" \
  "$OBSERVABILITY_SUBNET" \
  "$OBSERVABILITY_GATEWAY" \
  "$TAILSCALE_DNS_NAME" \
  "$OBSERVABILITY_STACK" \
  "$OBSERVABILITY_ROOT" \
  "$OBSERVABILITY_CONFIG_ROOT" \
  "$OBSERVABILITY_DATA_ROOT" \
  "$OBSERVABILITY_SECRETS_ROOT" \
  "$GRAFANA_TAILSCALE_PORT" \
  "$GRAFANA_ADMIN_USER" \
  "$GRAFANA_URL" \
  "$PROMETHEUS_RETENTION_TIME" \
  "$PROMETHEUS_RETENTION_SIZE" \
  "$LOKI_RETENTION_PERIOD" \
  "$GRAFANA_TAG" \
  "$PROMETHEUS_TAG" \
  "$LOKI_TAG" \
  "$ALLOY_TAG" \
  "$ALERTMANAGER_TAG" \
  "$NODE_EXPORTER_TAG" \
  "$CADVISOR_TAG" \
  "$BLACKBOX_EXPORTER_TAG" \
  "$DOCKER_SOCKET_PROXY_TAG" \
  "$GRAFANA_IMAGE" \
  "$PROMETHEUS_IMAGE" \
  "$LOKI_IMAGE" \
  "$ALLOY_IMAGE" \
  "$ALERTMANAGER_IMAGE" \
  "$NODE_EXPORTER_IMAGE" \
  "$CADVISOR_IMAGE" \
  "$BLACKBOX_EXPORTER_IMAGE" \
  "$DOCKER_SOCKET_PROXY_IMAGE" <<'PY_CONFIG_ENV'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
keys = [
    "OPS_GID",
    "OBSERVABILITY_SUBNET",
    "OBSERVABILITY_GATEWAY",
    "TAILSCALE_DNS_NAME",
    "OBSERVABILITY_STACK",
    "OBSERVABILITY_ROOT",
    "OBSERVABILITY_CONFIG_ROOT",
    "OBSERVABILITY_DATA_ROOT",
    "OBSERVABILITY_SECRETS_ROOT",
    "GRAFANA_TAILSCALE_PORT",
    "GRAFANA_ADMIN_USER",
    "GRAFANA_URL",
    "PROMETHEUS_RETENTION_TIME",
    "PROMETHEUS_RETENTION_SIZE",
    "LOKI_RETENTION_PERIOD",
    "GRAFANA_TAG",
    "PROMETHEUS_TAG",
    "LOKI_TAG",
    "ALLOY_TAG",
    "ALERTMANAGER_TAG",
    "NODE_EXPORTER_TAG",
    "CADVISOR_TAG",
    "BLACKBOX_EXPORTER_TAG",
    "DOCKER_SOCKET_PROXY_TAG",
    "GRAFANA_IMAGE",
    "PROMETHEUS_IMAGE",
    "LOKI_IMAGE",
    "ALLOY_IMAGE",
    "ALERTMANAGER_IMAGE",
    "NODE_EXPORTER_IMAGE",
    "CADVISOR_IMAGE",
    "BLACKBOX_EXPORTER_IMAGE",
    "DOCKER_SOCKET_PROXY_IMAGE",
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
        "# OBSERVABILITY — Grafana / Prometheus / Loki / Alloy",
        "# =============================================================================",
    ])

    for key in missing:
        out.append(f"export {key}={shlex.quote(values[key])}")

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY_CONFIG_ENV

chmod 0600 "$VPS_GUIDE_CONFIG"
bash -n "$VPS_GUIDE_CONFIG"

printf '\nObservability configuration saved to %s\n' \
  "$VPS_GUIDE_CONFIG"
printf 'Network:  %s %s gateway=%s\n' \
  "$OBSERVABILITY_NETWORK" \
  "$OBSERVABILITY_SUBNET" \
  "$OBSERVABILITY_GATEWAY"
printf 'Grafana:  %s\n' "$GRAFANA_URL"
printf 'Prometheus retention: %s / %s\n' \
  "$PROMETHEUS_RETENTION_TIME" \
  "$PROMETHEUS_RETENTION_SIZE"
printf 'Loki retention: %s\n' "$LOKI_RETENTION_PERIOD"
EOF_CH07_CONFIG

chmod 0750 "$OPS_ROOT/scripts/chapter-07-configure.sh"
````

Проверить script:

```bash
bash -n "$OPS_ROOT/scripts/chapter-07-configure.sh"
shellcheck -x "$OPS_ROOT/scripts/chapter-07-configure.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/chapter-07-configure.sh"
```

Заново загрузить config:

```bash
source "$HOME/config.env"
```

Проверить основные значения:

```bash
printf '%s\n' \
  "OBSERVABILITY_ROOT=$OBSERVABILITY_ROOT" \
  "OBSERVABILITY_DATA_ROOT=$OBSERVABILITY_DATA_ROOT" \
  "OBSERVABILITY_SUBNET=$OBSERVABILITY_SUBNET" \
  "OBSERVABILITY_GATEWAY=$OBSERVABILITY_GATEWAY" \
  "GRAFANA_URL=$GRAFANA_URL" \
  "PROMETHEUS_RETENTION_TIME=$PROMETHEUS_RETENTION_TIME" \
  "PROMETHEUS_RETENTION_SIZE=$PROMETHEUS_RETENTION_SIZE" \
  "LOKI_RETENTION_PERIOD=$LOKI_RETENTION_PERIOD"
```

Проверить exact image refs:

```bash
for variable in \
  GRAFANA_IMAGE \
  PROMETHEUS_IMAGE \
  LOKI_IMAGE \
  ALLOY_IMAGE \
  ALERTMANAGER_IMAGE \
  NODE_EXPORTER_IMAGE \
  CADVISOR_IMAGE \
  BLACKBOX_EXPORTER_IMAGE \
  DOCKER_SOCKET_PROXY_IMAGE; do

  value="$(printenv "$variable")"

  [[ "$value" =~ '@sha256:'[a-f0-9]{64}'$' ]] || {
    printf 'ERROR: %s is not digest-pinned: %s\n' \
      "$variable" "$value" >&2
    exit 1
  }

done

printf 'All observability images are digest-pinned.\n'
```

> Проверка использует `printenv`, поэтому одинаково работает из текущей Zsh-сессии и из Bash.

---

## 3. Перевести оставшиеся operational scripts на единый `config.env`

После главы 06 production deployment scripts уже читают `$HOME/config.env`. Если сервер проходил более раннюю редакцию глав, отдельные operational scripts всё ещё могут содержать прямой `source /etc/vps-guide/config.env`. В этой главе мы приводим к единой схеме:

- `docker-ensure-networks.sh`;
- `tailscale-inventory.sh`;
- `caddy-remove-site.sh` — idempotent migration, если в нём осталась legacy-загрузка.

Перезаписать `docker-ensure-networks.sh`:

````bash
cat > "$OPS_ROOT/scripts/docker-ensure-networks.sh" <<'EOF_DOCKER_NETWORKS'
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

: "${EDGE_NETWORK:?EDGE_NETWORK is not set}"
: "${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}"
: "${OBSERVABILITY_SUBNET:?OBSERVABILITY_SUBNET is not set}"
: "${OBSERVABILITY_GATEWAY:?OBSERVABILITY_GATEWAY is not set}"

ensure_edge_network() {
  if docker network inspect "$EDGE_NETWORK" >/dev/null 2>&1; then
    return
  fi

  docker network create \
    --driver bridge \
    "$EDGE_NETWORK" >/dev/null

  printf 'Created network: %s\n' "$EDGE_NETWORK"
}

ensure_observability_network() {
  local current_subnet
  local current_gateway

  if ! docker network inspect "$OBSERVABILITY_NETWORK" >/dev/null 2>&1; then
    docker network create \
      --driver bridge \
      --subnet "$OBSERVABILITY_SUBNET" \
      --gateway "$OBSERVABILITY_GATEWAY" \
      "$OBSERVABILITY_NETWORK" >/dev/null

    printf 'Created network: %s\n' "$OBSERVABILITY_NETWORK"
    return
  fi

  current_subnet="$(
    docker network inspect "$OBSERVABILITY_NETWORK" \
      --format '{{(index .IPAM.Config 0).Subnet}}'
  )"

  current_gateway="$(
    docker network inspect "$OBSERVABILITY_NETWORK" \
      --format '{{(index .IPAM.Config 0).Gateway}}'
  )"

  [[ "$current_subnet" == "$OBSERVABILITY_SUBNET" ]] || {
    printf 'ERROR: %s subnet mismatch\n' "$OBSERVABILITY_NETWORK" >&2
    printf 'expected: %s\nactual:   %s\n' \
      "$OBSERVABILITY_SUBNET" "$current_subnet" >&2
    exit 1
  }

  [[ "$current_gateway" == "$OBSERVABILITY_GATEWAY" ]] || {
    printf 'ERROR: %s gateway mismatch\n' "$OBSERVABILITY_NETWORK" >&2
    printf 'expected: %s\nactual:   %s\n' \
      "$OBSERVABILITY_GATEWAY" "$current_gateway" >&2
    exit 1
  }
}

ensure_edge_network
ensure_observability_network

printf 'Docker networks are ready.\n'
EOF_DOCKER_NETWORKS

chmod 0750 "$OPS_ROOT/scripts/docker-ensure-networks.sh"
````

Перезаписать `tailscale-inventory.sh`:

````bash
cat > "$OPS_ROOT/scripts/tailscale-inventory.sh" <<'EOF_TS_INVENTORY'
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

printf '## Time\n'
date --iso-8601=seconds

printf '\n## Service\n'
systemctl is-enabled tailscaled.service
systemctl is-active tailscaled.service

printf '\n## Version and status\n'
tailscale version
tailscale status

printf '\n## Addresses\n'
tailscale ip -4
tailscale ip -6
ip -brief address show tailscale0

printf '\n## Serve\n'
tailscale serve status || true

printf '\n## Network check\n'
tailscale netcheck

printf '\n## Firewall\n'
sudo ufw status numbered
EOF_TS_INVENTORY

chmod 0750 "$OPS_ROOT/scripts/tailscale-inventory.sh"
````

Idempotent migration для `caddy-remove-site.sh`: если script уже использует `$HOME/config.env`, блок ничего не меняет. Если осталась legacy-загрузка, она заменяется на текущую схему.

```bash
python3 - "$OPS_ROOT/scripts/caddy-remove-site.sh" <<'PY_CADDY_CONFIG'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

legacy = """# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env
"""

current = """VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"
"""

if 'source "$VPS_GUIDE_CONFIG"' in text:
    print("caddy-remove-site.sh already uses unified config.env")
elif legacy in text:
    path.write_text(text.replace(legacy, current, 1), encoding="utf-8")
    print("caddy-remove-site.sh migrated to unified config.env")
else:
    raise SystemExit(
        "ERROR: caddy-remove-site.sh has an unexpected config loader; inspect it before continuing"
    )
PY_CADDY_CONFIG
```

Проверить scripts:

```bash
bash -n \
  "$OPS_ROOT/scripts/docker-ensure-networks.sh" \
  "$OPS_ROOT/scripts/tailscale-inventory.sh" \
  "$OPS_ROOT/scripts/caddy-remove-site.sh"

shellcheck -x \
  "$OPS_ROOT/scripts/docker-ensure-networks.sh" \
  "$OPS_ROOT/scripts/tailscale-inventory.sh" \
  "$OPS_ROOT/scripts/caddy-remove-site.sh"
```

Проверить networks:

```bash
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

Проверить, что активные operational scripts больше не source старую конфигурацию:

```bash
if grep -R -nE \
    '^[[:space:]]*(source|\.)[[:space:]]+/etc/vps-guide/' \
    "$OPS_ROOT/scripts" \
    --exclude='chapter-06-configure.sh'; then
  printf 'ERROR: active script still sources legacy /etc/vps-guide config\n' >&2
  exit 1
fi

printf 'Active scripts use the current config scheme.\n'
```

Старые файлы `/etc/vps-guide/*` пока можно оставить как inert legacy leftovers. Они не являются источником конфигурации новых глав.

---

## 4. Создать каталоги observability и выставить permissions

Создать versioned directories:

```bash
install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2775 \
  "$OBSERVABILITY_ROOT" \
  "$OBSERVABILITY_CONFIG_ROOT" \
  "$OBSERVABILITY_CONFIG_ROOT/prometheus" \
  "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules" \
  "$OBSERVABILITY_CONFIG_ROOT/loki" \
  "$OBSERVABILITY_CONFIG_ROOT/alloy" \
  "$OBSERVABILITY_CONFIG_ROOT/alertmanager" \
  "$OBSERVABILITY_CONFIG_ROOT/blackbox" \
  "$OBSERVABILITY_CONFIG_ROOT/grafana" \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/provisioning" \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/provisioning/datasources" \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/provisioning/dashboards" \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards"
```

Создать runtime data directories:

```bash
install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2770 \
  "$OBSERVABILITY_DATA_ROOT" \
  "$OBSERVABILITY_DATA_ROOT/grafana" \
  "$OBSERVABILITY_DATA_ROOT/prometheus" \
  "$OBSERVABILITY_DATA_ROOT/loki" \
  "$OBSERVABILITY_DATA_ROOT/alertmanager" \
  "$OBSERVABILITY_DATA_ROOT/alloy"
```

Alloy image работает как непривилегированный UID/GID `473:473`. Создать writable storage path заранее; supplemental group `$OPS_GROUP` остаётся общей operational group:

```bash
sudo install -d \
  -o 473 \
  -g "$OPS_GROUP" \
  -m 2770 \
  "$OBSERVABILITY_DATA_ROOT/alloy/data"
```

Secrets directory:

```bash
install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0750 \
  "$OBSERVABILITY_SECRETS_ROOT"
```

Проверить:

```bash
stat -c '%A %U:%G %n' \
  "$OBSERVABILITY_ROOT" \
  "$OBSERVABILITY_CONFIG_ROOT" \
  "$OBSERVABILITY_DATA_ROOT" \
  "$OBSERVABILITY_SECRETS_ROOT"
```

Ожидаемая модель:

```text
/opt/ops/...                       versioned configuration
/opt/data/observability/...        persistent runtime data
/opt/data/observability/secrets    runtime-only secrets
```

Persistent data и secrets в Git не добавляются.

---

## 5. Создать helper для Grafana/Telegram secrets

Grafana admin password генерируется локально криптографически стойким random generator.

Для Alertmanager используется отдельный Telegram bot. Token и chat ID хранятся только в `/opt/data/observability/secrets`.

Создать helper:

````bash
cat > "$OPS_ROOT/scripts/observability-secrets.sh" <<'EOF_OBS_SECRETS'
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

: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}"
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"

command -v curl >/dev/null
command -v jq >/dev/null
command -v openssl >/dev/null

telegram_api() {
  local method="$1"
  shift

  curl \
    --config - \
    "$@" <<EOF_TELEGRAM_CURL
url = "https://api.telegram.org/bot${token}/${method}"
fail
silent
show-error
max-time = 15
EOF_TELEGRAM_CURL
}

install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0750 \
  "$OBSERVABILITY_SECRETS_ROOT"

GRAFANA_PASSWORD_FILE="$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password"
TELEGRAM_TOKEN_FILE="$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token"
TELEGRAM_CHAT_FILE="$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id"

if [[ ! -s "$GRAFANA_PASSWORD_FILE" ]]; then
  umask 077
  openssl rand -base64 36 | tr -d '\n' > "$GRAFANA_PASSWORD_FILE"
  printf '\n' >> "$GRAFANA_PASSWORD_FILE"
fi

chown "$ADMIN_USER:$OPS_GROUP" "$GRAFANA_PASSWORD_FILE"
chmod 0640 "$GRAFANA_PASSWORD_FILE"

printf 'Grafana admin password is ready.\n'

if [[ -s "$TELEGRAM_TOKEN_FILE" && -s "$TELEGRAM_CHAT_FILE" ]]; then
  printf 'Telegram secrets already exist. Validating them...\n'

  token="$(tr -d '\r\n' < "$TELEGRAM_TOKEN_FILE")"
  chat_id="$(tr -d '\r\n' < "$TELEGRAM_CHAT_FILE")"
else
  printf '\nCreate a dedicated Telegram bot with @BotFather.\n'
  printf 'Use /newbot, finish bot creation, then paste its token below.\n\n'

  read -r -s -p 'Telegram bot token: ' token
  printf '\n'

  [[ "$token" =~ ^[0-9]+:[A-Za-z0-9_-]{20,}$ ]] || {
    printf 'ERROR: token format is invalid\n' >&2
    exit 1
  }

  bot_json="$(
    telegram_api getMe
  )"

  [[ "$(jq -r '.ok' <<< "$bot_json")" == "true" ]] || {
    printf 'ERROR: Telegram getMe failed\n' >&2
    exit 1
  }

  bot_username="$(jq -r '.result.username' <<< "$bot_json")"

  printf 'Bot validated: @%s\n' "$bot_username"
  printf 'Open this bot in Telegram and send it /start or any message.\n'
  read -r -p 'After sending the message, press Enter here... ' _

  updates_json="$(
    telegram_api getUpdates \
      --get \
      --data-urlencode 'limit=100'
  )"

  chat_id="$(
    jq -r '
      .result
      | reverse
      | map(.message.chat // .channel_post.chat // empty)
      | .[0].id // empty
    ' <<< "$updates_json"
  )"

  [[ "$chat_id" =~ ^-?[0-9]+$ ]] || {
    printf 'ERROR: chat ID was not discovered.\n' >&2
    printf 'Send a new message directly to @%s and rerun the script.\n' \
      "$bot_username" >&2
    exit 1
  }

  umask 077
  printf '%s\n' "$token" > "$TELEGRAM_TOKEN_FILE"
  printf '%s\n' "$chat_id" > "$TELEGRAM_CHAT_FILE"

  chown "$ADMIN_USER:$OPS_GROUP" \
    "$TELEGRAM_TOKEN_FILE" \
    "$TELEGRAM_CHAT_FILE"

  chmod 0640 \
    "$TELEGRAM_TOKEN_FILE" \
    "$TELEGRAM_CHAT_FILE"
fi

reply="$(
  telegram_api sendMessage \
    --request POST \
    --data-urlencode "chat_id=${chat_id}" \
    --data-urlencode \
      "text=Observability notifications configured on ${SERVER_HOSTNAME}."
)"

[[ "$(jq -r '.ok' <<< "$reply")" == "true" ]] || {
  printf 'ERROR: Telegram test message failed\n' >&2
  exit 1
}

printf 'Telegram test message sent successfully.\n'

stat -c '%A %U:%G %n' \
  "$GRAFANA_PASSWORD_FILE" \
  "$TELEGRAM_TOKEN_FILE" \
  "$TELEGRAM_CHAT_FILE"
EOF_OBS_SECRETS

chmod 0750 "$OPS_ROOT/scripts/observability-secrets.sh"
````

Static checks:

```bash
bash -n "$OPS_ROOT/scripts/observability-secrets.sh"
shellcheck -x "$OPS_ROOT/scripts/observability-secrets.sh"
```

Запустить helper:

```bash
"$OPS_ROOT/scripts/observability-secrets.sh"
```

В Telegram должно прийти сообщение:

```text
Observability notifications configured on server.
```

Проверить permissions без вывода содержимого secrets:

```bash
stat -c '%A %U:%G %n' \
  "$OBSERVABILITY_SECRETS_ROOT" \
  "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id"
```

Secret files должны иметь mode `0640`; directory — `0750`.

---

## 6. Создать Loki configuration

Для одного VPS используется:

- single-process Loki;
- TSDB index;
- filesystem object store;
- replication factor `1`;
- retention `14 days`;
- compactor;
- ограниченная ingestion rate.

Loki не имеет собственного authentication layer. Поэтому его HTTP port публикуется только на `127.0.0.1`, а внутри Docker доступен только observability stack.

Создать config:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/loki/loki.yml" <<EOF_LOKI
---
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  graceful_shutdown_timeout: 30s

common:
  path_prefix: /loki
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/index_cache
  filesystem:
    directory: /loki/chunks

limits_config:
  retention_period: ${LOKI_RETENTION_PERIOD}
  max_query_lookback: ${LOKI_RETENTION_PERIOD}
  ingestion_rate_mb: 2
  ingestion_burst_size_mb: 4
  per_stream_rate_limit: 1MB
  per_stream_rate_limit_burst: 2MB

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 20
  delete_request_store: filesystem

analytics:
  reporting_enabled: false
EOF_LOKI
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/loki/loki.yml"
```

---

## 7. Создать Blackbox Exporter configuration

Blackbox Exporter нужен для end-to-end проверки публичного HTTPS route:

```text
DNS -> Internet -> Caddy -> application -> /health
```

Он также отдаёт срок действия TLS certificate.

Создать config:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/blackbox/blackbox.yml" <<'EOF_BLACKBOX'
---
modules:
  https_2xx:
    prober: http
    timeout: 10s
    http:
      method: GET
      preferred_ip_protocol: ip4
      ip_protocol_fallback: true
      fail_if_not_ssl: true
      valid_http_versions:
        - HTTP/1.1
        - HTTP/2.0
      tls_config:
        insecure_skip_verify: false
EOF_BLACKBOX
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/blackbox/blackbox.yml"
```

---

## 8. Создать Prometheus alert rules

Создать rules:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml" <<'EOF_PROM_RULES'
---
groups:
  - name: vps-host
    interval: 30s
    rules:
      - alert: PrometheusTargetDown
        expr: up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Prometheus target is down"
          description: "Target {{ $labels.job }} / {{ $labels.instance }} has been down for more than 2 minutes."

      - alert: RootFilesystemUsageHigh
        expr: |
          100 * (
            1 -
            node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
            /
            node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
          ) > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Root filesystem usage is above 80%"
          description: "Root filesystem usage on {{ $labels.instance }} is {{ $value | printf \"%.1f\" }}%."

      - alert: RootFilesystemUsageCritical
        expr: |
          100 * (
            1 -
            node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
            /
            node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
          ) > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Root filesystem usage is above 90%"
          description: "Root filesystem usage on {{ $labels.instance }} is {{ $value | printf \"%.1f\" }}%."

      - alert: RootInodeUsageHigh
        expr: |
          100 * (
            1 -
            node_filesystem_files_free{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
            /
            node_filesystem_files{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}
          ) > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Root filesystem inode usage is above 80%"
          description: "Root inode usage on {{ $labels.instance }} is {{ $value | printf \"%.1f\" }}%."

      - alert: HostMemoryUsageHigh
        expr: |
          100 * (
            1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
          ) > 90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Host memory usage is above 90%"
          description: "Memory usage on {{ $labels.instance }} is {{ $value | printf \"%.1f\" }}%."

      - alert: HostCPUUsageHigh
        expr: |
          100 * (
            1 - avg without (cpu) (
              rate(node_cpu_seconds_total{mode="idle"}[5m])
            )
          ) > 90
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Host CPU usage is above 90%"
          description: "CPU usage on {{ $labels.instance }} is {{ $value | printf \"%.1f\" }}%."

      - alert: HostOOMKillDetected
        expr: increase(node_vmstat_oom_kill[10m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Linux OOM killer was triggered"
          description: "At least one OOM kill was detected on {{ $labels.instance }} during the last 10 minutes."

  - name: public-endpoints
    interval: 30s
    rules:
      - alert: PublicEndpointDown
        expr: probe_success{job="blackbox-https"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Public HTTPS endpoint is down"
          description: "Probe failed for {{ $labels.instance }} for more than 2 minutes."

      - alert: TLSCertificateExpiringSoon
        expr: |
          (
            probe_ssl_earliest_cert_expiry{job="blackbox-https"} - time()
          ) / 86400 < 14
          and
          probe_success{job="blackbox-https"} == 1
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "TLS certificate expires in less than 14 days"
          description: "TLS certificate for {{ $labels.instance }} expires soon."
EOF_PROM_RULES
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml"
```

---

## 9. Создать Prometheus configuration

Prometheus собирает:

- собственные metrics;
- node_exporter;
- cAdvisor;
- Loki;
- Alloy;
- Alertmanager;
- Blackbox Exporter;
- public HTTPS probe.

Для cAdvisor сохраняется только небольшой набор container metrics, чтобы не раздувать TSDB на 4 GB VPS.

Создать config:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/prometheus/prometheus.yml" <<EOF_PROMETHEUS
---
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s
  external_labels:
    host: "${SERVER_HOSTNAME}"

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets:
          - prometheus:9090

  - job_name: node
    static_configs:
      - targets:
          - "${OBSERVABILITY_GATEWAY}:9100"
        labels:
          instance: "${SERVER_HOSTNAME}"

  - job_name: cadvisor
    static_configs:
      - targets:
          - cadvisor:8080
        labels:
          instance: "${SERVER_HOSTNAME}"
    metric_relabel_configs:
      - source_labels:
          - __name__
        regex: 'container_(cpu_usage_seconds_total|memory_working_set_bytes|memory_usage_bytes|network_receive_bytes_total|network_transmit_bytes_total|fs_usage_bytes|fs_limit_bytes|last_seen|start_time_seconds)'
        action: keep

  - job_name: loki
    static_configs:
      - targets:
          - loki:3100

  - job_name: alloy
    static_configs:
      - targets:
          - alloy:12345

  - job_name: alertmanager
    static_configs:
      - targets:
          - alertmanager:9093

  - job_name: blackbox-exporter
    static_configs:
      - targets:
          - blackbox-exporter:9115

  - job_name: blackbox-https
    metrics_path: /probe
    params:
      module:
        - https_2xx
    static_configs:
      - targets:
          - "https://${DEPLOY_TEST_DOMAIN}/health"
    relabel_configs:
      - source_labels:
          - __address__
        target_label: __param_target
      - source_labels:
          - __param_target
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
EOF_PROMETHEUS
````

Permissions:

```bash
chmod 0644 \
  "$OBSERVABILITY_CONFIG_ROOT/prometheus/prometheus.yml" \
  "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml"
```

---

## 10. Создать Alertmanager configuration

Telegram token и chat ID не записываются в YAML. Alertmanager читает их из Compose secrets files.

Создать config:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/alertmanager/alertmanager.yml" <<'EOF_ALERTMANAGER'
---
global:
  resolve_timeout: 5m

route:
  receiver: telegram
  group_by:
    - alertname
    - instance
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: telegram
    telegram_configs:
      - bot_token_file: /run/secrets/telegram_bot_token
        chat_id_file: /run/secrets/telegram_chat_id
        send_resolved: true
        parse_mode: HTML
EOF_ALERTMANAGER
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/alertmanager/alertmanager.yml"
```

---

## 11. Создать Grafana Alloy configuration

Alloy подключается не к `/var/run/docker.sock`, а к isolated socket proxy:

```text
Alloy -> tcp://socket-proxy:2375 -> selected read-only Docker API endpoints
```

Log labels ограничены низкокардинальными полями:

- `host`;
- `source`;
- `container`;
- `compose_project`;
- `compose_service`.

Создать config:

````bash
cat > "$OBSERVABILITY_CONFIG_ROOT/alloy/config.alloy" <<EOF_ALLOY
logging {
  level  = "info"
  format = "logfmt"
}

discovery.docker "local" {
  host             = "tcp://socket-proxy:2375"
  refresh_interval = "15s"
}

discovery.relabel "docker_logs" {
  targets = []

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(.*)"
    target_label  = "container"
  }

  rule {
    source_labels = ["__meta_docker_container_label_com_docker_compose_project"]
    target_label  = "compose_project"
  }

  rule {
    source_labels = ["__meta_docker_container_label_com_docker_compose_service"]
    target_label  = "compose_service"
  }
}

loki.source.docker "local" {
  host             = "tcp://socket-proxy:2375"
  targets          = discovery.docker.local.targets
  refresh_interval = "15s"
  labels = {
    host   = "${SERVER_HOSTNAME}",
    source = "docker",
  }
  relabel_rules = discovery.relabel.docker_logs.rules
  forward_to    = [loki.write.local.receiver]
}

loki.write "local" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
EOF_ALLOY
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_CONFIG_ROOT/alloy/config.alloy"
```

---

## 12. Создать Grafana provisioning

### Datasources

Создать Prometheus + Loki datasources:

````bash
cat > \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/provisioning/datasources/datasources.yml" <<'EOF_GRAFANA_DS'
---
apiVersion: 1

prune: true

datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      httpMethod: POST
      timeInterval: 15s

  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
EOF_GRAFANA_DS
````

### Dashboard provider

```bash
cat > \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/provisioning/dashboards/providers.yml" <<'EOF_GRAFANA_PROVIDER'
---
apiVersion: 1

providers:
  - name: vps-guide
    orgId: 1
    folder: Infrastructure
    type: file
    disableDeletion: true
    editable: false
    updateIntervalSeconds: 30
    options:
      path: /etc/grafana/dashboards
      foldersFromFilesStructure: false
EOF_GRAFANA_PROVIDER
```

### Базовый VPS dashboard

Создать dashboard:

````bash
cat > \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards/vps-overview.json" <<EOF_GRAFANA_DASHBOARD
{
  "annotations": {
    "list": []
  },
  "editable": false,
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
        "defaults": {
          "max": 100,
          "min": 0,
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "expr": "100 * (1 - avg(rate(node_cpu_seconds_total{instance=\"${SERVER_HOSTNAME}\",mode=\"idle\"}[5m])))",
          "refId": "A"
        }
      ],
      "title": "Host CPU usage",
      "type": "gauge"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "max": 100,
          "min": 0,
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 8,
        "y": 0
      },
      "id": 2,
      "options": {
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "expr": "100 * (1 - node_memory_MemAvailable_bytes{instance=\"${SERVER_HOSTNAME}\"} / node_memory_MemTotal_bytes{instance=\"${SERVER_HOSTNAME}\"})",
          "refId": "A"
        }
      ],
      "title": "Host memory usage",
      "type": "gauge"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "max": 100,
          "min": 0,
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 0
      },
      "id": 3,
      "options": {
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "expr": "100 * (1 - node_filesystem_avail_bytes{instance=\"${SERVER_HOSTNAME}\",mountpoint=\"/\",fstype!~\"tmpfs|overlay|squashfs\"} / node_filesystem_size_bytes{instance=\"${SERVER_HOSTNAME}\",mountpoint=\"/\",fstype!~\"tmpfs|overlay|squashfs\"})",
          "refId": "A"
        }
      ],
      "title": "Root filesystem usage",
      "type": "gauge"
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
        "x": 0,
        "y": 8
      },
      "id": 4,
      "targets": [
        {
          "expr": "node_load1{instance=\"${SERVER_HOSTNAME}\"}",
          "legendFormat": "load1",
          "refId": "A"
        },
        {
          "expr": "node_load5{instance=\"${SERVER_HOSTNAME}\"}",
          "legendFormat": "load5",
          "refId": "B"
        },
        {
          "expr": "node_load15{instance=\"${SERVER_HOSTNAME}\"}",
          "legendFormat": "load15",
          "refId": "C"
        }
      ],
      "title": "Load average",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "id": 5,
      "targets": [
        {
          "expr": "sum by (name) (rate(container_cpu_usage_seconds_total{name!=\"\"}[5m])) * 100",
          "legendFormat": "{{name}}",
          "refId": "A"
        }
      ],
      "title": "Container CPU",
      "type": "timeseries"
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
        "x": 0,
        "y": 16
      },
      "id": 6,
      "targets": [
        {
          "expr": "sum by (name) (container_memory_working_set_bytes{name!=\"\"})",
          "legendFormat": "{{name}}",
          "refId": "A"
        }
      ],
      "title": "Container memory",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "loki",
        "uid": "loki"
      },
      "gridPos": {
        "h": 12,
        "w": 12,
        "x": 12,
        "y": 16
      },
      "id": 7,
      "options": {
        "dedupStrategy": "none",
        "enableLogDetails": true,
        "prettifyLogMessage": false,
        "showCommonLabels": false,
        "showLabels": false,
        "showTime": true,
        "sortOrder": "Descending",
        "wrapLogMessage": true
      },
      "targets": [
        {
          "expr": "{source=\"docker\"}",
          "refId": "A"
        }
      ],
      "title": "Docker logs",
      "type": "logs"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 39,
  "tags": ["vps", "provisioned"],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-6h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "browser",
  "title": "VPS Overview",
  "uid": "vps-overview",
  "version": 1,
  "weekStart": ""
}
EOF_GRAFANA_DASHBOARD
````

Permissions:

```bash
find "$OBSERVABILITY_CONFIG_ROOT/grafana" \
  -type f \
  -exec chmod 0644 {} +
```

Проверить JSON:

```bash
jq empty \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards/vps-overview.json"
```

---

## 13. Создать production Compose stack

Особенности stack:

- только Grafana получает loopback port `127.0.0.1:3000` для Tailscale Serve;
- Prometheus/Loki/Alertmanager/Alloy также bind только на loopback для SSH diagnostics;
- node_exporter слушает только Docker bridge gateway `OBSERVABILITY_GATEWAY`, а не public interface;
- cAdvisor не публикует host port;
- Blackbox Exporter не публикует host port;
- socket proxy находится в отдельной `internal: true` network;
- только socket proxy получает Docker socket;
- proxy разрешает только нужные Docker read endpoints: containers/events/info/networks/ping/version;
- `NETWORKS=1` нужен Alloy `discovery.docker` для вычисления Docker network labels;
- `POST=0` запрещает write operations через proxy;
- privileged mode ограничен двумя высокодоверенными инфраструктурными компонентами: socket proxy — согласно upstream deployment model для доступа к Docker socket, cAdvisor — для host/container metrics;
- Alloy запускается как UID/GID `473:473`, а `/var/lib/alloy` является отдельным writable bind mount;
- socket proxy сохраняет read-only root filesystem, но получает writable tmpfs `/tmp` для generated HAProxy config;
- resource limits рассчитаны на VPS с 4 GB RAM.

Создать Compose:

````bash
cat > "$OBSERVABILITY_ROOT/compose.yaml" <<'EOF_OBS_COMPOSE'
---
name: observability

services:
  socket-proxy:
    image: ${DOCKER_SOCKET_PROXY_IMAGE:?DOCKER_SOCKET_PROXY_IMAGE is not set}
    restart: unless-stopped
    environment:
      CONTAINERS: "1"
      EVENTS: "1"
      INFO: "1"
      NETWORKS: "1"
      PING: "1"
      VERSION: "1"
      POST: "0"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - docker-api
    read_only: true
    tmpfs:
      - /tmp:size=16m,mode=1777
      - /run:size=16m,mode=0755
      - /var/lib/haproxy:size=16m,mode=0755
    privileged: true
    pids_limit: 64
    mem_limit: 64m
    cpus: 0.15

  loki:
    image: ${LOKI_IMAGE:?LOKI_IMAGE is not set}
    restart: unless-stopped
    command:
      - -config.file=/etc/loki/loki.yml
    group_add:
      - "${OPS_GID:?OPS_GID is not set}"
    volumes:
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/loki/loki.yml:/etc/loki/loki.yml:ro
      - ${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}/loki:/loki
    ports:
      - 127.0.0.1:3100:3100
    networks:
      - observability
    read_only: true
    tmpfs:
      - /tmp:size=32m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 512m
    cpus: 0.60
    stop_grace_period: 60s

  alloy:
    image: ${ALLOY_IMAGE:?ALLOY_IMAGE is not set}
    restart: unless-stopped
    user: "473:473"
    command:
      - run
      - --server.http.listen-addr=0.0.0.0:12345
      - --storage.path=/var/lib/alloy/data
      - /etc/alloy/config.alloy
    group_add:
      - "${OPS_GID:?OPS_GID is not set}"
    volumes:
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/alloy/config.alloy:/etc/alloy/config.alloy:ro
      - ${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}/alloy:/var/lib/alloy:rw
    ports:
      - 127.0.0.1:12345:12345
    networks:
      - observability
      - docker-api
    read_only: true
    tmpfs:
      - /tmp:size=32m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 256m
    cpus: 0.35
    depends_on:
      - socket-proxy
      - loki

  node-exporter:
    image: ${NODE_EXPORTER_IMAGE:?NODE_EXPORTER_IMAGE is not set}
    restart: unless-stopped
    command:
      - --path.rootfs=/host
      - --web.listen-address=${OBSERVABILITY_GATEWAY:?OBSERVABILITY_GATEWAY is not set}:9100
      - --no-collector.timex
    network_mode: host
    pid: host
    volumes:
      - /:/host:ro,rslave
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 96m
    cpus: 0.20

  cadvisor:
    image: ${CADVISOR_IMAGE:?CADVISOR_IMAGE is not set}
    restart: unless-stopped
    command:
      - --docker_only=true
      - --housekeeping_interval=15s
    privileged: true
    devices:
      - /dev/kmsg:/dev/kmsg
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker:/var/lib/docker:ro
      - /dev/disk:/dev/disk:ro
    networks:
      - observability
    pids_limit: 256
    mem_limit: 256m
    cpus: 0.35

  blackbox-exporter:
    image: ${BLACKBOX_EXPORTER_IMAGE:?BLACKBOX_EXPORTER_IMAGE is not set}
    restart: unless-stopped
    command:
      - --config.file=/etc/blackbox/blackbox.yml
    volumes:
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/blackbox/blackbox.yml:/etc/blackbox/blackbox.yml:ro
    networks:
      - observability
    read_only: true
    tmpfs:
      - /tmp:size=16m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 96m
    cpus: 0.20

  alertmanager:
    image: ${ALERTMANAGER_IMAGE:?ALERTMANAGER_IMAGE is not set}
    restart: unless-stopped
    command:
      - --config.file=/etc/alertmanager/alertmanager.yml
      - --storage.path=/alertmanager
    group_add:
      - "${OPS_GID:?OPS_GID is not set}"
    volumes:
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - ${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}/alertmanager:/alertmanager
    secrets:
      - telegram_bot_token
      - telegram_chat_id
    ports:
      - 127.0.0.1:9093:9093
    networks:
      - observability
    read_only: true
    tmpfs:
      - /tmp:size=16m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 128m
    cpus: 0.20
    stop_grace_period: 30s

  prometheus:
    image: ${PROMETHEUS_IMAGE:?PROMETHEUS_IMAGE is not set}
    restart: unless-stopped
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=${PROMETHEUS_RETENTION_TIME:?PROMETHEUS_RETENTION_TIME is not set}
      - --storage.tsdb.retention.size=${PROMETHEUS_RETENTION_SIZE:?PROMETHEUS_RETENTION_SIZE is not set}
      - --web.listen-address=0.0.0.0:9090
    group_add:
      - "${OPS_GID:?OPS_GID is not set}"
    volumes:
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/prometheus/rules:/etc/prometheus/rules:ro
      - ${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}/prometheus:/prometheus
    ports:
      - 127.0.0.1:9090:9090
    networks:
      - observability
    read_only: true
    tmpfs:
      - /tmp:size=32m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 512m
    cpus: 0.60
    stop_grace_period: 60s
    depends_on:
      - alertmanager
      - node-exporter
      - cadvisor
      - blackbox-exporter
      - loki
      - alloy

  grafana:
    image: ${GRAFANA_IMAGE:?GRAFANA_IMAGE is not set}
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER is not set}
      GF_SECURITY_ADMIN_PASSWORD__FILE: /run/secrets/grafana_admin_password
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_USERS_ALLOW_ORG_CREATE: "false"
      GF_AUTH_ANONYMOUS_ENABLED: "false"
      GF_SECURITY_COOKIE_SECURE: "true"
      GF_SECURITY_COOKIE_SAMESITE: strict
      GF_SECURITY_DISABLE_GRAVATAR: "true"
      GF_SNAPSHOTS_EXTERNAL_ENABLED: "false"
      GF_ANALYTICS_REPORTING_ENABLED: "false"
      GF_ANALYTICS_CHECK_FOR_UPDATES: "false"
      GF_UPDATE_CHECKER_ENABLED: "false"
      GF_SERVER_ROOT_URL: ${GRAFANA_URL:?GRAFANA_URL is not set}
      GF_LOG_MODE: console
    group_add:
      - "${OPS_GID:?OPS_GID is not set}"
    volumes:
      - ${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}/grafana:/var/lib/grafana
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/grafana/provisioning:/etc/grafana/provisioning:ro
      - ${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}/grafana/dashboards:/etc/grafana/dashboards:ro
    secrets:
      - grafana_admin_password
    ports:
      - 127.0.0.1:3000:3000
    networks:
      - observability
    read_only: true
    tmpfs:
      - /tmp:size=64m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 384m
    cpus: 0.50
    stop_grace_period: 30s
    depends_on:
      - prometheus
      - loki

networks:
  observability:
    external: true
    name: ${OBSERVABILITY_NETWORK:?OBSERVABILITY_NETWORK is not set}

  docker-api:
    internal: true

secrets:
  grafana_admin_password:
    file: ${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}/grafana_admin_password

  telegram_bot_token:
    file: ${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}/telegram_bot_token

  telegram_chat_id:
    file: ${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}/telegram_chat_id
EOF_OBS_COMPOSE
````

Permissions:

```bash
chmod 0644 "$OBSERVABILITY_ROOT/compose.yaml"
```

---

## 14. Создать wrapper для observability Compose

Не зависеть от текущего working directory и не терять variables после новой SSH-сессии.

Создать script:

````bash
cat > "$OPS_ROOT/scripts/observability-compose.sh" <<'EOF_OBS_COMPOSE_WRAPPER'
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

: "${OBSERVABILITY_ROOT:?OBSERVABILITY_ROOT is not set}"
: "${OBSERVABILITY_STACK:?OBSERVABILITY_STACK is not set}"

exec docker compose \
  --project-name "$OBSERVABILITY_STACK" \
  --project-directory "$OBSERVABILITY_ROOT" \
  --file "$OBSERVABILITY_ROOT/compose.yaml" \
  "$@"
EOF_OBS_COMPOSE_WRAPPER

chmod 0750 "$OPS_ROOT/scripts/observability-compose.sh"
````

Проверить:

```bash
bash -n "$OPS_ROOT/scripts/observability-compose.sh"
shellcheck -x "$OPS_ROOT/scripts/observability-compose.sh"
```

---

## 15. Выполнить static validation до первого запуска

Загрузить config:

```bash
source "$HOME/config.env"
```

### Compose

```bash
"$OPS_ROOT/scripts/observability-compose.sh" config --quiet
```

Проверить, что все service images являются digest refs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" config --images |
while IFS= read -r image_ref; do
  [[ "$image_ref" =~ @sha256:[a-f0-9]{64}$ ]] || {
    printf 'ERROR: mutable image in resolved Compose config: %s\n' \
      "$image_ref" >&2
    exit 1
  }
done

printf 'Resolved Compose images are immutable.\n'
```

### Prometheus

```bash
docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus:/etc/prometheus:ro" \
  "$PROMETHEUS_IMAGE" \
  check config /etc/prometheus/prometheus.yml
```

Отдельно проверить rules:

```bash
docker run --rm \
  --entrypoint=/bin/promtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/prometheus/rules:/rules:ro" \
  "$PROMETHEUS_IMAGE" \
  check rules /rules/vps.yml
```

### Loki

```bash
docker run --rm \
  -v "$OBSERVABILITY_CONFIG_ROOT/loki/loki.yml:/etc/loki/loki.yml:ro" \
  "$LOKI_IMAGE" \
  -config.file=/etc/loki/loki.yml \
  -verify-config=true
```

### Alloy

```bash
docker run --rm \
  -v "$OBSERVABILITY_CONFIG_ROOT/alloy/config.alloy:/etc/alloy/config.alloy:ro" \
  "$ALLOY_IMAGE" \
  validate /etc/alloy/config.alloy
```

### Alertmanager

```bash
docker run --rm \
  --entrypoint=/bin/amtool \
  -v "$OBSERVABILITY_CONFIG_ROOT/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
  -v "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token:/run/secrets/telegram_bot_token:ro" \
  -v "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id:/run/secrets/telegram_chat_id:ro" \
  "$ALERTMANAGER_IMAGE" \
  check-config /etc/alertmanager/alertmanager.yml
```

### Grafana dashboard JSON

```bash
jq empty \
  "$OBSERVABILITY_CONFIG_ROOT/grafana/dashboards/vps-overview.json"
```

### Bash scripts

```bash
bash -n \
  "$OPS_ROOT/scripts/chapter-07-configure.sh" \
  "$OPS_ROOT/scripts/docker-ensure-networks.sh" \
  "$OPS_ROOT/scripts/tailscale-inventory.sh" \
  "$OPS_ROOT/scripts/observability-secrets.sh" \
  "$OPS_ROOT/scripts/observability-compose.sh"

shellcheck -x \
  "$OPS_ROOT/scripts/chapter-07-configure.sh" \
  "$OPS_ROOT/scripts/docker-ensure-networks.sh" \
  "$OPS_ROOT/scripts/tailscale-inventory.sh" \
  "$OPS_ROOT/scripts/observability-secrets.sh" \
  "$OPS_ROOT/scripts/observability-compose.sh"
```

Не запускать stack, пока static validation не проходит полностью.

---

## 16. Запустить observability stack

Убедиться, что networks существуют:

```bash
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

Разрешить **только observability containers** обращаться к host `node_exporter` на bridge gateway. Listener при этом остаётся привязан только к `$OBSERVABILITY_GATEWAY`, поэтому public interface порт `9100` не получает:

```bash
sudo ufw allow in \
  from "$OBSERVABILITY_SUBNET" \
  to "$OBSERVABILITY_GATEWAY" \
  port 9100 \
  proto tcp \
  comment 'Prometheus to node_exporter'
```

Проверить правило:

```bash
sudo ufw status numbered |
grep -F 'Prometheus to node_exporter'
```

Не использовать `ufw allow 9100/tcp`: source должен оставаться ограничен Docker observability subnet.

Pull exact digests:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" pull
```

Запустить:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" up -d --remove-orphans
```

Показать состояние:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" ps
```

Подождать, пока persistent services стартуют:

```bash
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:9090/-/ready >/dev/null && \
     curl --fail --silent http://127.0.0.1:3100/ready >/dev/null && \
     curl --fail --silent http://127.0.0.1:9093/-/ready >/dev/null && \
     curl --fail --silent http://127.0.0.1:3000/api/health >/dev/null; then
    printf 'Core observability services are ready.\n'
    break
  fi

  if (( attempt == 30 )); then
    printf 'ERROR: observability stack did not become ready\n' >&2
    "$OPS_ROOT/scripts/observability-compose.sh" ps >&2
    exit 1
  fi

  sleep 2
done
```

Проверить Alloy HTTP endpoint. Success message печатается только после успешного HTTP request:

```bash
if curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:12345/ \
  >/dev/null; then

  printf 'Alloy HTTP endpoint is reachable.\n'
else
  printf 'ERROR: Alloy HTTP endpoint is unavailable.\n' >&2
  "$OPS_ROOT/scripts/observability-compose.sh" \
    logs --tail=100 alloy >&2
  exit 1
fi
```

---

## 17. Проверить Prometheus targets

Подождать два scrape intervals:

```bash
sleep 35
```

Получить active targets:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:9090/api/v1/targets |
jq -r '
  .data.activeTargets[]
  | [
      .labels.job,
      (.labels.instance // "-"),
      .health,
      (.lastError // "")
    ]
  | @tsv
' |
column -t -s $'\t'
```

Автоматически остановиться, если хотя бы один target не `up`:

```bash
DOWN_TARGETS="$(
  curl \
    --fail \
    --silent \
    --show-error \
    http://127.0.0.1:9090/api/v1/targets |
  jq '[.data.activeTargets[] | select(.health != "up")] | length'
)"

[[ "$DOWN_TARGETS" == "0" ]] || {
  printf 'ERROR: %s Prometheus target(s) are not up\n' \
    "$DOWN_TARGETS" >&2
  exit 1
}

printf 'All Prometheus targets are up.\n'
```

Проверить node exporter:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=node_uname_info' \
  http://127.0.0.1:9090/api/v1/query |
jq -e '.data.result | length > 0' >/dev/null

printf 'Host metrics are present.\n'
```

Проверить cAdvisor:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=container_memory_working_set_bytes{name!=""}' \
  http://127.0.0.1:9090/api/v1/query |
jq -e '.data.result | length > 0' >/dev/null

printf 'Container metrics are present.\n'
```

Проверить HTTPS probe:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode \
    "query=probe_success{job=\"blackbox-https\",instance=\"https://${DEPLOY_TEST_DOMAIN}/health\"}" \
  http://127.0.0.1:9090/api/v1/query |
jq -e '.data.result[0].value[1] == "1"' >/dev/null

printf 'Public HTTPS probe is successful.\n'
```

Проверить срок TLS certificate:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode \
    "query=(probe_ssl_earliest_cert_expiry{job=\"blackbox-https\"}-time())/86400" \
  http://127.0.0.1:9090/api/v1/query |
jq -r '.data.result[] | "TLS days remaining: \(.value[1] | tonumber | floor)"'
```

---

## 18. Проверить Docker logs в Loki

Дать Alloy время обнаружить containers:

```bash
sleep 20
```

Проверить Loki labels:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:3100/loki/api/v1/labels |
jq -e '.data | index("source") != null' >/dev/null

printf 'Loki source label exists.\n'
```

Проверить, что из observability containers реально пришли logs:

```bash
NOW_NS="$(date +%s%N)"
START_NS="$(( NOW_NS - 300000000000 ))"

LOG_COUNT="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode "query={source=\"docker\",compose_project=\"${OBSERVABILITY_STACK}\"}" \
    --data-urlencode "start=$START_NS" \
    --data-urlencode "end=$NOW_NS" \
    --data-urlencode 'limit=100' \
    http://127.0.0.1:3100/loki/api/v1/query_range |
  jq '[.data.result[].values[]] | length'
)"

(( LOG_COUNT > 0 )) || {
  printf 'ERROR: no Docker logs found in Loki\n' >&2
  exit 1
}

printf 'Docker log entries found in Loki: %s\n' "$LOG_COUNT"
```

Показать несколько последних lines:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode "query={source=\"docker\",compose_project=\"${OBSERVABILITY_STACK}\"}" \
  --data-urlencode "start=$START_NS" \
  --data-urlencode "end=$NOW_NS" \
  --data-urlencode 'limit=10' \
  --data-urlencode 'direction=backward' \
  http://127.0.0.1:3100/loki/api/v1/query_range |
jq -r '.data.result[].values[][1]' |
head -n 10
```

---

## 19. Проверить Grafana provisioning локально

Grafana health:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:3000/api/health |
jq
```

Загрузить password только в текущую shell variable:

```bash
GRAFANA_ADMIN_PASSWORD="$(
  tr -d '\r\n' < \
    "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password"
)"
```

Проверить datasources через API:

```bash
curl --config - <<EOF_GRAFANA_DATASOURCES |
fail
silent
show-error
user = "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"
url = "http://127.0.0.1:3000/api/datasources"
EOF_GRAFANA_DATASOURCES
jq -e '
  map(.uid)
  | (index("prometheus") != null and index("loki") != null)
' >/dev/null

printf 'Grafana datasources are provisioned.\n'
```

Проверить dashboard:

```bash
curl \
  --config - \
  --get \
  --data-urlencode 'query=VPS Overview' <<EOF_GRAFANA_SEARCH |
fail
silent
show-error
user = "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"
url = "http://127.0.0.1:3000/api/search"
EOF_GRAFANA_SEARCH
jq -e 'map(select(.uid == "vps-overview")) | length == 1' >/dev/null

printf 'VPS Overview dashboard is provisioned.\n'
```

Удалить password variable из shell:

```bash
unset GRAFANA_ADMIN_PASSWORD
```

---

## 20. Настроить private Grafana access через Tailscale Serve

Grafana остаётся на:

```text
127.0.0.1:3000
```

Tailscale Serve публикует его только внутри tailnet на `8443/tcp`.

Проверить target:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:3000/api/health >/dev/null
```

Включить persistent Serve:

```bash
sudo tailscale serve \
  --bg \
  --https="$GRAFANA_TAILSCALE_PORT" \
  http://127.0.0.1:3000
```

Проверить Serve state:

```bash
tailscale serve status
```

Показать URL:

```bash
printf 'Grafana URL: %s\n' "$GRAFANA_URL"
```

### Если в главе 03 была вручную включена restrictive Tailscale policy

В optional policy главы 03 разрешался только SSH. Тогда в текущей policy нужно разрешить также Grafana Serve port:

```text
ip: ["tcp:22", "tcp:8443"]
```

Не заменяйте существующую tailnet policy целиком этим фрагментом. Добавьте `tcp:8443` в уже существующий grant для вашего admin identity/server tag и проверьте policy в Tailscale Admin Console перед сохранением.

При default personal tailnet policy отдельное изменение не требуется.

### Проверить вход в Grafana

Показать username:

```bash
printf 'Grafana user: %s\n' "$GRAFANA_ADMIN_USER"
```

Generated password хранится только в runtime secret file:

```text
/opt/data/observability/secrets/grafana_admin_password
```

Получите его вручную только в момент входа и **не вставляйте значение в сохраняемые console logs, issue или chat**. После первого входа пароль можно сменить в Grafana и синхронно обновить operational secret.

Открыть на своём компьютере URL из:

```bash
printf '%s\n' "$GRAFANA_URL"
```

После входа должен существовать folder:

```text
Infrastructure
```

и dashboard:

```text
VPS Overview
```

Не создавайте публичный `grafana.<domain>` route в Caddy.

---

## 21. Проверить Telegram alert end-to-end

Создать test alert напрямую через Alertmanager API. Он нужен только для проверки notification path и автоматически истечёт через две минуты.

```bash
STARTS_AT="$(date --utc --iso-8601=seconds)"
ENDS_AT="$(date --utc --iso-8601=seconds --date='+2 minutes')"

jq -n \
  --arg starts_at "$STARTS_AT" \
  --arg ends_at "$ENDS_AT" \
  --arg instance "$SERVER_HOSTNAME" \
  '[
    {
      labels: {
        alertname: "VPSGuideTestAlert",
        severity: "warning",
        instance: $instance
      },
      annotations: {
        summary: "VPS Guide observability test alert",
        description: "Alertmanager -> Telegram delivery test"
      },
      startsAt: $starts_at,
      endsAt: $ends_at
    }
  ]' |
curl \
  --fail \
  --silent \
  --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data-binary @- \
  http://127.0.0.1:9093/api/v2/alerts
```

Через `group_wait: 30s` в Telegram должен прийти firing alert.

Проверить Alertmanager API:

```bash
sleep 35

curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:9093/api/v2/alerts |
jq -e \
  'map(select(.labels.alertname == "VPSGuideTestAlert")) | length >= 1' \
  >/dev/null

printf 'Test alert exists in Alertmanager.\n'
```

Примерно через две минуты test alert завершится и, так как `send_resolved: true`, Telegram должен получить resolved notification.

---

## 22. Создать единый runtime health-check script

Создать script:

````bash
cat > "$OPS_ROOT/scripts/observability-check.sh" <<'EOF_OBS_CHECK'
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
: "${OBSERVABILITY_GATEWAY:?OBSERVABILITY_GATEWAY is not set}"
: "${OBSERVABILITY_STACK:?OBSERVABILITY_STACK is not set}"

printf '## Compose\n'
"$OPS_ROOT/scripts/observability-compose.sh" ps

for service in socket-proxy alloy; do
  container_id="$(
    "$OPS_ROOT/scripts/observability-compose.sh" ps -q "$service"
  )"

  [[ -n "$container_id" ]] || {
    printf 'ERROR: %s container was not found\n' "$service" >&2
    exit 1
  }

  [[ "$(docker inspect --format '{{.State.Running}}' "$container_id")" == "true" ]] || {
    printf 'ERROR: %s container is not running\n' "$service" >&2
    docker logs --tail=100 "$container_id" >&2 || true
    exit 1
  }
done

printf '\n## Readiness\n'
curl --fail --silent --show-error http://127.0.0.1:9090/-/ready
printf '\n'
curl --fail --silent --show-error http://127.0.0.1:3100/ready
printf '\n'
curl --fail --silent --show-error http://127.0.0.1:9093/-/ready
printf '\n'
curl --fail --silent --show-error http://127.0.0.1:3000/api/health | jq

printf '\n## Prometheus targets\n'
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:9090/api/v1/targets |
jq -r '
  .data.activeTargets[]
  | [
      .labels.job,
      (.labels.instance // "-"),
      .health,
      (.lastError // "")
    ]
  | @tsv
' |
column -t -s $'\t'

DOWN_TARGETS="$(
  curl \
    --fail \
    --silent \
    --show-error \
    http://127.0.0.1:9090/api/v1/targets |
  jq '[.data.activeTargets[] | select(.health != "up")] | length'
)"

[[ "$DOWN_TARGETS" == "0" ]] || {
  printf 'ERROR: %s Prometheus target(s) are down\n' \
    "$DOWN_TARGETS" >&2
  exit 1
}

printf '\n## Docker -> Alloy -> Loki\n'
NOW_NS="$(date +%s%N)"
START_NS="$(( NOW_NS - 600000000000 ))"

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
    --data-urlencode 'limit=100' \
    --data-urlencode 'direction=backward' \
    http://127.0.0.1:3100/loki/api/v1/query_range |
  jq '[.data.result[].values[]] | length'
)"

(( LOG_COUNT > 0 )) || {
  printf 'ERROR: Docker logs are absent from Loki; check socket-proxy and Alloy\n' >&2
  "$OPS_ROOT/scripts/observability-compose.sh" logs --tail=100 socket-proxy alloy >&2
  exit 1
}

printf 'Docker log pipeline is working: %s recent entries found.\n' \
  "$LOG_COUNT"

printf '\n## Listening ports\n'
sudo ss -lntp |
  grep -E ':(3000|3100|8443|9090|9093|9100|12345)\b' || true

printf '\n## Docker resource snapshot\n'
docker stats --no-stream \
  --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}'

printf '\nObservability check passed.\n'
EOF_OBS_CHECK

chmod 0750 "$OPS_ROOT/scripts/observability-check.sh"
````

Static checks:

```bash
bash -n "$OPS_ROOT/scripts/observability-check.sh"
shellcheck -x "$OPS_ROOT/scripts/observability-check.sh"
```

Запустить:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
```

---

## 23. Проверить network exposure

Публичными остаются Caddy ports `80/tcp`, `443/tcp`, `443/udp`.

Observability host listeners должны быть следующими:

```text
127.0.0.1:3000    Grafana
127.0.0.1:3100    Loki
127.0.0.1:9090    Prometheus
127.0.0.1:9093    Alertmanager
127.0.0.1:12345   Alloy UI
<observability-gateway>:9100  node_exporter
```

Проверить:

```bash
sudo ss -lntp |
  grep -E ':(3000|3100|9090|9093|9100|12345)\b'
```

Автоматически проверить loopback services:

```bash
for port in 3000 3100 9090 9093 12345; do
  if sudo ss -lntH "sport = :$port" |
    awk '{print $4}' |
    grep -Ev '^127\.0\.0\.1:' >/dev/null; then
    printf 'ERROR: port %s is listening outside IPv4 loopback\n' \
      "$port" >&2
    exit 1
  fi
done

printf 'Loopback observability ports are isolated.\n'
```

Проверить node_exporter bind:

```bash
NODE_EXPORTER_LISTENER="$(
  sudo ss -lntH 'sport = :9100' |
    awk '{print $4}' |
    head -n 1
)"

[[ "$NODE_EXPORTER_LISTENER" == "${OBSERVABILITY_GATEWAY}:9100" ]] || {
  printf 'ERROR: unexpected node_exporter listener: %s\n' \
    "$NODE_EXPORTER_LISTENER" >&2
  exit 1
}

printf 'node_exporter is bound only to %s\n' \
  "$OBSERVABILITY_GATEWAY"
```

Проверить, что cAdvisor и Blackbox не публикуют host ports:

```bash
for service in cadvisor blackbox-exporter; do
  container_id="$(
    "$OPS_ROOT/scripts/observability-compose.sh" ps -q "$service"
  )"

  [[ -n "$container_id" ]] || {
    printf 'ERROR: %s container was not found\n' "$service" >&2
    exit 1
  }

  docker inspect "$container_id" |
    jq -e '.[0].HostConfig.PortBindings | length == 0' \
      >/dev/null || {
        printf 'ERROR: %s publishes a host port\n' "$service" >&2
        exit 1
      }
done

printf 'cAdvisor and Blackbox have no host ports.\n'
```

Проверить firewall:

```bash
sudo ufw status numbered
```

Для `9100/tcp` допустимо только созданное этой главой узкое правило:

```text
<OBSERVABILITY_GATEWAY>:9100/tcp ALLOW FROM <OBSERVABILITY_SUBNET>
```

Не добавлять unrestricted UFW rules для `3000`, `3100`, `9090`, `9093`, `9100`, `12345` или `8443`.

Tailscale Serve обслуживается Tailscale и не требует публичного UFW allow rule.

---

## 24. Проверить Docker socket isolation

Найти containers, которые непосредственно имеют mount `/var/run/docker.sock`:

```bash
docker inspect $(docker ps -q) |
jq -r '
  .[]
  | select(
      any(
        .Mounts[]?;
        .Source == "/var/run/docker.sock"
      )
    )
  | .Name
' |
sed 's#^/##'
```

В observability stack должен появиться только:

```text
observability-socket-proxy-1
```

Alloy не должен иметь direct socket mount:

```bash
ALLOY_CONTAINER_ID="$(
  "$OPS_ROOT/scripts/observability-compose.sh" ps -q alloy
)"

if docker inspect "$ALLOY_CONTAINER_ID" |
  jq -e '
    .[0].Mounts
    | any(.Source == "/var/run/docker.sock")
  ' >/dev/null; then
  printf 'ERROR: Alloy has direct Docker socket access\n' >&2
  exit 1
fi

printf 'Alloy has no direct Docker socket mount.\n'
```

Проверить isolated `docker-api` network:

```bash
SOCKET_NETWORK="$(
  docker inspect \
    "$("$OPS_ROOT/scripts/observability-compose.sh" ps -q socket-proxy)" |
  jq -r '.[0].NetworkSettings.Networks | keys[] | select(test("docker-api"))'
)"

docker network inspect "$SOCKET_NETWORK" |
jq -e '.[0].Internal == true' >/dev/null

printf 'Docker API proxy network is internal.\n'
```

---

## 25. Проверить retention и persistent storage

Prometheus flags:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" exec -T prometheus \
  /bin/prometheus --version
```

Проверить running command:

```bash
docker inspect \
  "$("$OPS_ROOT/scripts/observability-compose.sh" ps -q prometheus)" |
jq -r '.[0].Args[]' |
grep -E '^--storage\.tsdb\.retention\.(time|size)='
```

Должны присутствовать:

```text
--storage.tsdb.retention.time=15d
--storage.tsdb.retention.size=6GB
```

Проверить Loki retention config:

```bash
grep -E \
  'retention_period:|retention_enabled:|delete_request_store:' \
  "$OBSERVABILITY_CONFIG_ROOT/loki/loki.yml"
```

Проверить persistent directories:

```bash
sudo du -sh \
  "$OBSERVABILITY_DATA_ROOT/grafana" \
  "$OBSERVABILITY_DATA_ROOT/prometheus" \
  "$OBSERVABILITY_DATA_ROOT/loki" \
  "$OBSERVABILITY_DATA_ROOT/alertmanager" \
  "$OBSERVABILITY_DATA_ROOT/alloy"
```

Проверить filesystem:

```bash
df -h "$OBSERVABILITY_DATA_ROOT"
```

---

## 26. Обновить README инфраструктуры

Добавить/обновить observability section идемпотентно:

````bash
python3 - "$OPS_ROOT/README.md" <<'PY_README_OBSERVABILITY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

begin = "<!-- BEGIN OBSERVABILITY -->"
end = "<!-- END OBSERVABILITY -->"

section = r'''<!-- BEGIN OBSERVABILITY -->
## Observability

Stack:

```text
Prometheus      metrics storage and alert rules
node_exporter   Ubuntu host metrics
cAdvisor        Docker container metrics
Blackbox        public HTTPS/TLS probes
Grafana Alloy   Docker log collection
Loki            log storage
Grafana         metrics/log visualization
Alertmanager    Telegram notifications
```

Versioned configuration:

```text
/opt/ops/compose/observability/compose.yaml
/opt/ops/config/observability/
```

Persistent runtime data:

```text
/opt/data/observability/
```

Runtime-only secrets:

```text
/opt/data/observability/secrets/
```

Grafana is bound to `127.0.0.1:3000` and exposed only inside the tailnet through Tailscale Serve. Prometheus, Loki, Alertmanager and Alloy diagnostic ports are loopback-only.

Docker logs reach Alloy through a read-only Docker socket proxy on an isolated internal network. Alloy does not mount `/var/run/docker.sock` directly.

Prometheus retention is bounded by time and size. Loki retention is enforced by the compactor.
<!-- END OBSERVABILITY -->'''

pattern = re.compile(
    re.escape(begin) + r".*?" + re.escape(end),
    flags=re.DOTALL,
)

if pattern.search(text):
    text = pattern.sub(section, text, count=1)
else:
    text = text.rstrip() + "\n\n" + section + "\n"

path.write_text(text, encoding="utf-8")
PY_README_OBSERVABILITY
````

Проверить:

```bash
grep -n -A45 -B2 \
  'BEGIN OBSERVABILITY' \
  "$OPS_ROOT/README.md"
```

---

## 27. Проверить изменения перед Git commit

Показать status:

```bash
git -C "$OPS_ROOT" status --short
```

Добавить только versioned infrastructure:

```bash
git -C "$OPS_ROOT" add \
  compose/observability \
  config/observability \
  scripts/chapter-07-configure.sh \
  scripts/docker-ensure-networks.sh \
  scripts/tailscale-inventory.sh \
  scripts/caddy-remove-site.sh \
  scripts/observability-secrets.sh \
  scripts/observability-compose.sh \
  scripts/observability-check.sh \
  README.md
```

Проверить staged diff:

```bash
git -C "$OPS_ROOT" diff --cached --stat
git -C "$OPS_ROOT" diff --cached --check
git -C "$OPS_ROOT" diff --cached --name-status
```

Проверить, что runtime/secrets не staged:

```bash
if git -C "$OPS_ROOT" \
    diff --cached --diff-filter=ACMR --name-only |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|config\.json|.*\.bak(\..*)?|grafana_admin_password|telegram_bot_token|telegram_chat_id)$'; then
  printf 'ERROR: runtime or secret file is staged\n' >&2
  exit 1
fi

printf 'No runtime/secret files are staged.\n'
```

Проверить отсутствие token-like content в staged diff:

```bash
if git -C "$OPS_ROOT" diff --cached |
  grep -E \
    '[0-9]{6,}:[A-Za-z0-9_-]{20,}'; then
  printf 'ERROR: possible Telegram bot token in staged diff\n' >&2
  exit 1
fi

printf 'No Telegram token pattern found in staged diff.\n'
```

---

## 28. Выполнить финальную runtime validation

Запустить full check:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
```

Проверить production app:

```bash
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3
```

Проверить Caddy:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Проверить failed systemd units:

```bash
sudo systemctl --failed
```

Проверить disk/memory:

```bash
free -h
df -h /
docker stats --no-stream
```

На 4 GB VPS после запуска stack не должно происходить swap thrashing или OOM kills.

Проверить kernel OOM messages текущей boot session:

```bash
sudo journalctl -k -b \
  --grep='Out of memory\|Killed process' \
  --no-pager || true
```

Если вывод пустой — OOM events в текущей boot session не найдены.

---

## 29. Git-фиксация главы 07

Создать commit:

```bash
git -C "$OPS_ROOT" commit \
  -m 'Add production observability stack'
```

Push:

```bash
git -C "$OPS_ROOT" push origin main
```

Проверить remote branch:

```bash
git -C "$OPS_ROOT" fetch --quiet origin main

LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"

[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local and remote main differ\n' >&2
  exit 1
}

printf 'GitHub main is synchronized: %s\n' "$LOCAL_SHA"
```

Проверить clean tree:

```bash
test -z "$(git -C "$OPS_ROOT" status --porcelain)" || {
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

printf 'Git tree is clean.\n'
```

---

## 30. Финальный inventory

```bash
printf '## Containers\n'
docker ps --format \
  'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

printf '\n## Observability\n'
"$OPS_ROOT/scripts/observability-check.sh"

printf '\n## Tailscale\n'
tailscale serve status
printf 'Grafana: %s\n' "$GRAFANA_URL"

printf '\n## Production app\n'
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"

printf '\n## Failed systemd units\n'
sudo systemctl --failed

printf '\n## Git\n'
git -C "$OPS_ROOT" status --short
git -C "$OPS_ROOT" log -3 --oneline
```

---

## 31. Критерии завершения главы

Глава считается завершённой, если выполняются все условия:

- `observability` Compose stack запущен;
- `socket-proxy` и Alloy находятся в state `running`, без restart loop;
- все images в resolved Compose config имеют exact `@sha256:` digest;
- Prometheus отвечает `ready`;
- Loki отвечает `ready`;
- Alertmanager отвечает `ready`;
- Grafana `/api/health` отвечает успешно;
- все Prometheus targets имеют state `up`;
- `node_uname_info` присутствует;
- cAdvisor container metrics присутствуют;
- Blackbox probe `https://<deploy-test>/health` равен `1`;
- TLS expiry metric присутствует;
- Alloy отправляет Docker logs в Loki;
- Loki query возвращает logs из observability containers;
- Grafana автоматически видит Prometheus и Loki datasources;
- dashboard `VPS Overview` provisioned;
- Grafana доступна через Tailscale Serve;
- Grafana не имеет публичного Caddy route;
- Telegram test alert доставлен;
- Prometheus retention ограничен `15d` и `6GB`;
- Loki retention ограничен `336h`;
- Docker socket непосредственно mounted только в socket proxy среди observability services;
- Alloy не имеет direct Docker socket mount;
- socket proxy network имеет `Internal=true`;
- Grafana/Prometheus/Loki/Alertmanager/Alloy host ports bind только на loopback;
- node_exporter bind только на Docker observability gateway, а UFW разрешает `9100/tcp` только от observability subnet;
- cAdvisor и Blackbox не публикуют host ports;
- runtime data находятся в `/opt/data/observability`;
- Grafana/Telegram secrets находятся в `/opt/data/observability/secrets` и не tracked Git;
- active operational scripts не source `/etc/vps-guide/config.env`;
- production deploy-test по-прежнему healthy;
- Caddy config valid;
- `systemctl --failed` пуст;
- Git tree чистый;
- local `main` совпадает с `origin/main`.

---

## 32. Диагностика типовых ошибок

### `chapter-07-configure.sh`: image pull возвращает `unauthorized`

Для public Docker Hub images authentication не требуется.

Если ошибка относится к `ghcr.io/google/cadvisor`, сначала проверить обычный anonymous pull:

```bash
DOCKER_CONFIG_TMP="$(mktemp -d)"

DOCKER_CONFIG="$DOCKER_CONFIG_TMP" \
  docker pull ghcr.io/google/cadvisor:v0.60.5

rm -rf "$DOCKER_CONFIG_TMP"
```

Если public pull работает, а обычный pull нет, проверить текущий Docker config/auth configuration.

Не удаляйте working GHCR credential главы 06 без необходимости.

### `docker compose config`: variable is not set

Заново загрузить config:

```bash
source "$HOME/config.env"
```

Проверить:

```bash
zsh -lic '
  printf "%s\n" \
    "$OBSERVABILITY_ROOT" \
    "$GRAFANA_IMAGE" \
    "$PROMETHEUS_IMAGE" \
    "$LOKI_IMAGE"
'
```

Если пусто — повторно выполнить:

```bash
"$OPS_ROOT/scripts/chapter-07-configure.sh"
```

### `node` target DOWN / connection refused на `:9100`

Проверить node_exporter:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" ps node-exporter
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=100 node-exporter
```

Проверить bind:

```bash
sudo ss -lntp 'sport = :9100'
printf '%s\n' "$OBSERVABILITY_GATEWAY"
```

Listener должен быть:

```text
<OBSERVABILITY_GATEWAY>:9100
```

Проверить network gateway:

```bash
docker network inspect "$OBSERVABILITY_NETWORK" |
jq -r '.[0].IPAM.Config[0].Gateway'
```

Если gateway изменился, не исправляйте `config.env` вручную вслепую. Сначала выясните, почему external `observability` network была пересоздана.

### `cadvisor` не запускается с `/dev/kmsg`

Проверить:

```bash
ls -l /dev/kmsg
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 cadvisor
```

На обычном Ubuntu VPS `/dev/kmsg` существует.

Если provider/kernel намеренно не предоставляет `/dev/kmsg`, удалить только `devices: /dev/kmsg:/dev/kmsg` из cAdvisor service и повторить static/runtime checks. Не добавляйте дополнительные privileged mounts наугад.

### Prometheus target `cadvisor` DOWN

Проверить service DNS из Prometheus network через временный curl container запрещено не требуется. Сначала:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" ps cadvisor
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 cadvisor
```

Проверить network membership:

```bash
docker inspect \
  "$("$OPS_ROOT/scripts/observability-compose.sh" ps -q cadvisor)" |
jq '.[0].NetworkSettings.Networks'
```

### Loki не стартует после изменения config

Проверить config до restart:

```bash
docker run --rm \
  -v "$OBSERVABILITY_CONFIG_ROOT/loki/loki.yml:/etc/loki/loki.yml:ro" \
  "$LOKI_IMAGE" \
  -config.file=/etc/loki/loki.yml \
  -verify-config=true
```

Затем logs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 loki
```

Не удаляйте `/opt/data/observability/loki` для «лечения» config error.

### Loki работает, но logs отсутствуют

Проверить Alloy:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 alloy
```

Проверить socket proxy:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 socket-proxy
```

Проверить Alloy config:

```bash
docker run --rm \
  -v "$OBSERVABILITY_CONFIG_ROOT/alloy/config.alloy:/etc/alloy/config.alloy:ro" \
  "$ALLOY_IMAGE" \
  validate /etc/alloy/config.alloy
```

Проверить Loki labels:

```bash
curl -fsS http://127.0.0.1:3100/loki/api/v1/labels | jq
```

Не монтируйте Docker socket напрямую в Alloy как быстрый workaround. Сначала исправьте socket-proxy/discovery path.

### Socket proxy отвечает `403`

Это ожидаемо для Docker API endpoints, которые не разрешены environment policy proxy.

Для текущего Alloy Docker discovery нужны read operations по containers/events/info/**networks**/version/ping. В Compose должны присутствовать:

```yaml
CONTAINERS: "1"
EVENTS: "1"
INFO: "1"
NETWORKS: "1"
PING: "1"
VERSION: "1"
POST: "0"
```

Если в Alloy logs есть `error while computing network labels` + `403 Forbidden`, в socket-proxy отсутствует `NETWORKS=1`.

`POST` намеренно отключён. Не включайте `POST=1` для устранения log collection problem.

### Grafana container получает `permission denied` для `/var/lib/grafana`

Проверить data directory:

```bash
stat -c '%A %U:%G %n' \
  "$OBSERVABILITY_DATA_ROOT/grafana"
```

Проверить supplemental group внутри container:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" exec -T grafana id
```

В groups должен присутствовать numeric `OPS_GID`.

Исправить host directory, не использовать `chmod 777`:

```bash
sudo chown "$ADMIN_USER:$OPS_GROUP" \
  "$OBSERVABILITY_DATA_ROOT/grafana"

sudo chmod 2770 \
  "$OBSERVABILITY_DATA_ROOT/grafana"
```

### Alloy уходит в restart loop с `mkdir /var/lib/alloy/data: permission denied`

Проверить Compose:

```bash
grep -n -A35 '^  alloy:' "$OBSERVABILITY_ROOT/compose.yaml"
```

Нужны одновременно:

```yaml
user: "473:473"
command:
  - --storage.path=/var/lib/alloy/data
volumes:
  - ${OBSERVABILITY_DATA_ROOT}/alloy:/var/lib/alloy:rw
```

Проверить host storage:

```bash
stat -c '%A %u:%g %n' \
  "$OBSERVABILITY_DATA_ROOT/alloy" \
  "$OBSERVABILITY_DATA_ROOT/alloy/data"
```

Исправлять права через operational group, не через `chmod 777`:

```bash
sudo chown "$ADMIN_USER:$OPS_GROUP" \
  "$OBSERVABILITY_DATA_ROOT/alloy"
sudo chmod 2770 \
  "$OBSERVABILITY_DATA_ROOT/alloy"
sudo install -d \
  -o 473 \
  -g "$OPS_GROUP" \
  -m 2770 \
  "$OBSERVABILITY_DATA_ROOT/alloy/data"
```

### Prometheus/Loki/Alertmanager не могут писать persistent data

Проверить соответствующий directory:

```bash
stat -c '%A %U:%G %n' \
  "$OBSERVABILITY_DATA_ROOT/prometheus" \
  "$OBSERVABILITY_DATA_ROOT/loki" \
  "$OBSERVABILITY_DATA_ROOT/alertmanager" \
  "$OBSERVABILITY_DATA_ROOT/alloy"
```

Ожидается group-writable setgid directory `2770` для `$OPS_GROUP`.

Не использовать `chmod -R 777`.

### Telegram helper не находит chat ID

Убедиться, что после создания bot вы открыли именно нового bot и отправили ему сообщение `/start`.

Повторить:

```bash
rm -f \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id"

"$OPS_ROOT/scripts/observability-secrets.sh"
```

Grafana password при этом не изменится.

### Telegram test message приходит, а Prometheus alerts нет

Проверить Prometheus rules:

```bash
curl -fsS \
  http://127.0.0.1:9090/api/v1/rules |
jq '.data.groups[] | {name, rules: [.rules[].name]}'
```

Проверить Alertmanager discovery:

```bash
curl -fsS \
  http://127.0.0.1:9090/api/v1/alertmanagers |
jq
```

Проверить Alertmanager logs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 alertmanager
```

### `PublicEndpointDown` firing сразу после запуска

Проверить endpoint напрямую:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health"
```

Проверить результат Blackbox probe в Prometheus:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=probe_success{job="blackbox-https"}' \
  http://127.0.0.1:9090/api/v1/query |
jq '.data.result[] | {instance: .metric.instance, value: .value[1]}'
```

Для подробной диагностики смотреть Blackbox logs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" logs --tail=200 blackbox-exporter
```

### Grafana открывается локально, но `GRAFANA_URL` недоступен

Проверить Serve:

```bash
tailscale serve status
```

Повторно применить:

```bash
sudo tailscale serve \
  --bg \
  --https="$GRAFANA_TAILSCALE_PORT" \
  http://127.0.0.1:3000
```

Если используется restrictive tailnet access policy, разрешить `tcp:8443` для нужного admin identity/server tag.

Не создавайте публичный Caddy route как workaround.

Если браузер показывает `ERR_TUNNEL_CONNECTION_FAILED`, а Tailscale Serve status корректный, сначала проверить browser/system proxy. Быстрая проверка с клиентского компьютера — открыть URL в браузере без proxy либо выполнить `curl --noproxy "*"` к `GRAFANA_URL`. Если другой браузер открывает Grafana, VPS/Tailscale менять не нужно.

### Grafana login не принимает generated password

Проверить, что container был создан после secret file:

```bash
stat -c '%y %n' \
  "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password"

"$OPS_ROOT/scripts/observability-compose.sh" ps grafana
```

Если Grafana database уже была и admin password был изменён внутри UI, `GF_SECURITY_ADMIN_PASSWORD__FILE` не перезаписывает существующего пользователя при каждом restart.

Для текущей новой установки сначала использовать password из secret file. После ручной смены password внутри Grafana обновить operational secret deliberately; не удалять Grafana database.

### VPS начал активно использовать swap

Проверить:

```bash
free -h
vmstat 1 10
docker stats --no-stream
```

Посмотреть top memory containers:

```bash
docker stats --no-stream \
  --format '{{.MemUsage}}\t{{.Name}}' |
sort -hr
```

На этом VPS не увеличивать retention и не добавлять Tempo/GlitchTip до выяснения memory pressure.

Не отключайте resource limits для observability stack.

### Disk быстро растёт

Проверить:

```bash
sudo du -sh \
  "$OBSERVABILITY_DATA_ROOT"/* |
sort -h

df -h /
```

Prometheus ограничен `15d` и `6GB`.

Loki ограничен `14 days`, но filesystem storage не имеет отдельного hard byte quota. При неожиданно большом log volume сначала уменьшить noisy application logs/retention, а не увеличивать disk thresholds.

---

## 33. Что намеренно не входит в главу 07

### Tempo / distributed tracing

Сначала metrics/logs должны стабильно отвечать на вопросы:

```text
работает ли сервис;
когда он сломался;
что происходило с CPU/RAM/disk;
какие container logs были перед ошибкой;
какой public endpoint недоступен.
```

Tempo и OpenTelemetry добавляются позже, когда появятся приложения с осмысленной instrumentation.

### GlitchTip

Error tracking — следующий самостоятельный слой. Он не заменяет Loki и не должен мешать первичной настройке observability.

### PostgreSQL exporter

На текущем этапе production PostgreSQL ещё не является общей platform dependency. DB metrics будут добавляться вместе с database layer/application contract.

### Backup age alert

Backup system ещё не создан. Alert `backup older than 24h` появится одновременно с restic/database dump contract, чтобы не создавать fake metric.

### Container restart alert для любого будущего container

cAdvisor хорошо показывает running resource metrics, но универсальный expected-state alert по произвольным Compose projects без inventory source ненадёжен. В следующих главах application inventory/deploy metadata будет использоваться для service-specific availability alerts.

### Публичный Grafana domain

Не создаётся намеренно. Grafana остаётся private admin UI через Tailscale.

### Self-hosted Prometheus/Loki high availability

На одном VPS HA невозможно: отказ VPS выключит и workload, и monitoring. Off-host alerting/backup будет отдельным слоем.

---

## 34. Актуальные технические ориентиры

Версии, зафиксированные этой главой на `2026-08-07`:

```text
Grafana OSS           13.1.1
Prometheus            3.11.3
Loki                  3.7.4
Grafana Alloy         1.18.0
Alertmanager          0.32.1
node_exporter         1.11.1
cAdvisor              0.60.5
Blackbox Exporter     0.28.0
docker-socket-proxy   0.5.0
```

Tag используется только на этапе controlled resolution. После выполнения `chapter-07-configure.sh` Compose получает exact `repository@sha256:digest`.

Официальные/первичные references:

- Grafana Docker configuration: https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/
- Grafana provisioning: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Prometheus configuration: https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- Prometheus alerting rules: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Alertmanager configuration: https://prometheus.io/docs/alerting/latest/configuration/
- node_exporter container deployment: https://github.com/prometheus/node_exporter
- Blackbox Exporter: https://github.com/prometheus/blackbox_exporter
- cAdvisor: https://github.com/google/cadvisor
- Loki Docker installation: https://grafana.com/docs/loki/latest/setup/install/docker/
- Loki TSDB: https://grafana.com/docs/loki/latest/operations/storage/tsdb/
- Loki retention: https://grafana.com/docs/loki/latest/operations/storage/retention/
- Grafana Alloy Docker logs: https://grafana.com/docs/alloy/latest/monitor/monitor-docker-containers/
- `loki.source.docker`: https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/
- Alloy validate: https://grafana.com/docs/alloy/latest/reference/cli/validate/
- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Docker socket proxy: https://github.com/Tecnativa/docker-socket-proxy

После завершения этой главы сервер получает полноценный первый observability layer: **host metrics + container metrics + public probes + centralized logs + private dashboards + Telegram alerts**.
