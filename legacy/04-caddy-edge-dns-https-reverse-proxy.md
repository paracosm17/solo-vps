# Глава 4. Caddy: DNS, HTTPS и reverse proxy

> **Цель:** развернуть единый публичный edge-прокси, настроить DNS и automatic HTTPS, затем подключить Docker-приложение без публикации его внутреннего порта.

> **Результат:** только Caddy принимает внешний трафик на `80/tcp`, `443/tcp` и `443/udp`. Приложения доступны ему по DNS-именам в Docker-сети `edge`; сертификаты автоматически выпускаются и продлеваются.

---

## 1. Почему выбран Caddy

Для одного VPS с Docker Compose, несколькими доменами и небольшими self-hosted-сервисами Caddy даёт минимальную операционную сложность:

- automatic HTTPS встроен и не требует отдельного Certbot;
- конфигурация сайта обычно занимает несколько строк;
- Docker socket не нужен;
- reload выполняется без остановки текущих соединений;
- поддерживаются HTTP/1.1, HTTP/2 и HTTP/3;
- JSON access logs можно позднее отправить в Loki через Grafana Alloy.

Caddy не является WAF и не заменяет защиту приложения, Cloudflare, ModSecurity или специализированный API gateway.

### Краткое сравнение альтернатив

| Решение | Основное назначение | Когда выбирать вместо Caddy |
|---|---|---|
| **Nginx** | Универсальный web server, proxy, cache | Нужны знакомые Nginx-модули, сложный cache или существующая Nginx-экспертиза |
| **Traefik** | Динамическое обнаружение Docker/Kubernetes-сервисов | Десятки часто меняющихся сервисов и label-driven deployment; требуется аккуратно защищать доступ к Docker API |
| **BunkerWeb** | Nginx/ModSecurity + WAF | Подтверждена необходимость OWASP CRS и готовность обслуживать false positives |
| **HAProxy** | Высоконагруженный L4/L7 load balancer | Сложная TCP/HTTP-балансировка, health routing, несколько backend-узлов |
| **Pingora** | Framework для собственной proxy-платформы на Rust | Требуется программировать нестандартный proxy, а не настроить готовый edge |
| **Apache HTTP Server** | Web server, `.htaccess`, legacy-приложения | Приложение зависит от Apache-модулей или `.htaccess` |
| **APISIX / Kong** | API gateway, plugins, auth, governance | Появилась отдельная API-platform с централизованными политиками |
| **KrakenD** | API aggregation и Backend-for-Frontend | Нужна агрегация и трансформация API, а не обычный web edge |
| **Hiawatha** | Лёгкий security-oriented web server | Осознанно выбрана его меньшая экосистема |
| **Angie** | Nginx-compatible high-load proxy | Требуется Nginx-совместимость и специфические возможности Angie |

Для сценария «один VPS + Docker Compose + несколько доменов + автоматический HTTPS» используется Caddy.

---

## 2. Архитектура edge-слоя

```text
Internet / Cloudflare
        │
        ├── 80/tcp   HTTP, ACME HTTP-01, redirect
        ├── 443/tcp  HTTPS, HTTP/1.1, HTTP/2
        └── 443/udp  HTTP/3
                 │
                 ▼
          Caddy container
                 │
          Docker network: edge
                 │
          edge-test-web:8080
```

Правила:

- только Caddy публикует `80/443`;
- web frontend приложения подключается к external-сети `edge` без host port;
- DB, Redis и workers остаются во внутренней сети приложения;
- Caddy не получает `/var/run/docker.sock`;
- конфигурация хранится в `/opt/ops/config/caddy`;
- сертификаты и ACME state хранятся в `/opt/data/caddy`;
- административные UI остаются приватными через Tailscale.

---

## 3. Настроить DNS

В DNS-панели создать запись:

```text
Type:   A
Name:   edge-test
Value:  публичный IPv4 VPS из ServerIp
Proxy:  DNS only на время первого выпуска сертификата
TTL:    Auto
```

Не создавайте `AAAA`, пока VPS действительно не имеет рабочего публичного IPv6 и Caddy не слушает его.

Если используется Cloudflare, на первом запуске оставьте серую тучу **DNS only**. Тогда публичный resolver возвращает origin IP, а ACME challenge приходит напрямую к Caddy. После успешного выпуска сертификата proxy можно включить и выбрать режим **Full (strict)**.

Проверить запись:

```bash
dig +short A "$EDGE_TEST_DOMAIN" @1.1.1.1
```

Результат должен совпадать с `$SERVER_PUBLIC_IPV4` до включения Cloudflare Proxy.

---

## 4. Подготовить сеть и каталоги

Убедиться, что external-сеть существует:

```bash
"$OPS_ROOT/scripts/docker-ensure-networks.sh"
```

Создать каталоги с правами, подходящими для hardened-контейнеров. Caddy и тестовый Nginx должны иметь возможность проходить по parent directories и читать bind-mounted файлы:

```bash
sudo install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 0755 \
  "$OPS_ROOT/config/caddy" \
  "$OPS_ROOT/config/caddy/sites" \
  "$OPS_ROOT/compose/edge" \
  "$OPS_ROOT/compose/edge-test" \
  "$OPS_ROOT/compose/edge-test/site"

sudo install -d -o root -g root -m 0755 \
  "$DATA_ROOT/caddy" \
  "$DATA_ROOT/caddy/data" \
  "$DATA_ROOT/caddy/config"
```

Конфигурационные каталоги имеют `0755`, файлы далее получают `0644`. Секреты в них не хранятся. Локальные `.env` получают `0600` и не добавляются в Git.

---

## 5. Создать Compose-стек Caddy

```bash
cat > "$OPS_ROOT/compose/edge/compose.yaml" <<'EOF_CADDY_COMPOSE'
name: ${COMPOSE_PROJECT_NAME:-edge}

services:
  caddy:
    image: ${CADDY_IMAGE:?Set CADDY_IMAGE}
    restart: unless-stopped

    ports:
      - "${CADDY_BIND_IPV4:-0.0.0.0}:80:80/tcp"
      - "${CADDY_BIND_IPV4:-0.0.0.0}:443:443/tcp"
      - "${CADDY_BIND_IPV4:-0.0.0.0}:443:443/udp"

    environment:
      CADDY_ACME_EMAIL: ${CADDY_ACME_EMAIL:?Set CADDY_ACME_EMAIL}
      EDGE_TEST_DOMAIN: ${EDGE_TEST_DOMAIN:?Set EDGE_TEST_DOMAIN}
      EDGE_TEST_UPSTREAM: ${EDGE_TEST_UPSTREAM:?Set EDGE_TEST_UPSTREAM}

    volumes:
      - type: bind
        source: ${OPS_ROOT:?Set OPS_ROOT}/config/caddy
        target: /etc/caddy
        read_only: true
      - type: bind
        source: ${DATA_ROOT:?Set DATA_ROOT}/caddy/data
        target: /data
      - type: bind
        source: ${DATA_ROOT:?Set DATA_ROOT}/caddy/config
        target: /config

    networks:
      - edge

    security_opt:
      - no-new-privileges=true

    cap_drop:
      - ALL

    read_only: true

    tmpfs:
      - /tmp:size=32m,mode=1777
      - /run:size=8m,mode=0755

    pids_limit: 256
    mem_limit: ${CADDY_MEMORY_LIMIT:-256m}
    cpus: ${CADDY_CPU_LIMIT:-0.50}

    labels:
      ops.managed-by: docker-compose
      ops.role: edge

networks:
  edge:
    external: true
    name: ${EDGE_NETWORK:?Set EDGE_NETWORK}
EOF_CADDY_COMPOSE

cat > "$OPS_ROOT/compose/edge/.env" <<EOF_CADDY_ENV
COMPOSE_PROJECT_NAME=${CADDY_STACK}
CADDY_IMAGE=${CADDY_IMAGE}
CADDY_BIND_IPV4=${CADDY_BIND_IPV4}
CADDY_MEMORY_LIMIT=${CADDY_MEMORY_LIMIT}
CADDY_CPU_LIMIT=${CADDY_CPU_LIMIT}
CADDY_ACME_EMAIL=${CADDY_ACME_EMAIL}
EDGE_TEST_DOMAIN=${EDGE_TEST_DOMAIN}
EDGE_TEST_UPSTREAM=${EDGE_TEST_UPSTREAM}
EDGE_NETWORK=${EDGE_NETWORK}
OPS_ROOT=${OPS_ROOT}
DATA_ROOT=${DATA_ROOT}
EOF_CADDY_ENV

cat > "$OPS_ROOT/compose/edge/.env.example" <<'EOF_CADDY_ENV_EXAMPLE'
COMPOSE_PROJECT_NAME=edge
CADDY_IMAGE=caddy:2.11.4-alpine
CADDY_BIND_IPV4=0.0.0.0
CADDY_MEMORY_LIMIT=256m
CADDY_CPU_LIMIT=0.50
CADDY_ACME_EMAIL=admin@example.com
EDGE_TEST_DOMAIN=edge-test.example.com
EDGE_TEST_UPSTREAM=edge-test-web:8080
EDGE_NETWORK=edge
OPS_ROOT=/opt/ops
DATA_ROOT=/opt/data
EOF_CADDY_ENV_EXAMPLE

chmod 0600 "$OPS_ROOT/compose/edge/.env"
chmod 0644 \
  "$OPS_ROOT/compose/edge/compose.yaml" \
  "$OPS_ROOT/compose/edge/.env.example"
```

---

## 6. Создать Caddyfile

```bash
cat > "$OPS_ROOT/config/caddy/Caddyfile" <<'EOF_CADDYFILE'
{
	email {$CADDY_ACME_EMAIL}
	admin localhost:2019

	log {
		output stdout
		format json
		level INFO
	}
}

(common) {
	log {
		output stdout
		format json
	}

	encode zstd gzip

	header {
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		-Server
	}
}

import /etc/caddy/sites/*.caddy
EOF_CADDYFILE

cat > "$OPS_ROOT/config/caddy/sites/edge-test.caddy" <<'EOF_EDGE_SITE'
{$EDGE_TEST_DOMAIN} {
	import common
	reverse_proxy {$EDGE_TEST_UPSTREAM}
}
EOF_EDGE_SITE

find "$OPS_ROOT/config/caddy" -type d -exec chmod 0755 {} +
find "$OPS_ROOT/config/caddy" -type f -exec chmod 0644 {} +
```

Файлы уже записаны в формате `caddy fmt`; отдельное форматирование перед первым запуском не требуется.

---

## 7. Создать тестовый backend без публичного порта

Nginx запускается как UID/GID `101:101`, поэтому parent directories и read-only файлы должны быть доступны на чтение.

```bash
cat > "$OPS_ROOT/compose/edge-test/nginx.conf" <<'EOF_NGINX'
worker_processes auto;
pid /tmp/nginx.pid;

error_log /dev/stderr notice;

events {
    worker_connections 1024;
}

http {
    access_log /dev/stdout;

    client_body_temp_path /tmp/client_temp;
    proxy_temp_path       /tmp/proxy_temp;
    fastcgi_temp_path     /tmp/fastcgi_temp;
    uwsgi_temp_path       /tmp/uwsgi_temp;
    scgi_temp_path        /tmp/scgi_temp;

    server {
        listen 8080;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;
    }
}
EOF_NGINX

cat > "$OPS_ROOT/compose/edge-test/site/index.html" <<'EOF_INDEX'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Edge is ready</title>
</head>
<body>
  <main>
    <h1>Caddy edge работает</h1>
  </main>
</body>
</html>
EOF_INDEX

cat > "$OPS_ROOT/compose/edge-test/compose.yaml" <<'EOF_EDGE_TEST_COMPOSE'
name: ${COMPOSE_PROJECT_NAME:-edge-test}

services:
  web:
    image: ${EDGE_TEST_IMAGE:-nginx:alpine}
    restart: unless-stopped
    user: "101:101"

    command:
      - nginx
      - -g
      - daemon off;

    expose:
      - "8080"

    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./site:/usr/share/nginx/html:ro

    networks:
      edge:
        aliases:
          - edge-test-web

    security_opt:
      - no-new-privileges=true

    cap_drop:
      - ALL

    read_only: true

    tmpfs:
      - /tmp:size=32m,mode=1777

    pids_limit: 128
    mem_limit: 128m
    cpus: "0.25"

    healthcheck:
      test:
        - CMD-SHELL
        - wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s

    labels:
      ops.managed-by: docker-compose
      ops.host-published: "false"

networks:
  edge:
    external: true
    name: ${EDGE_NETWORK:?Set EDGE_NETWORK}
EOF_EDGE_TEST_COMPOSE

cat > "$OPS_ROOT/compose/edge-test/.env" <<EOF_EDGE_TEST_ENV
COMPOSE_PROJECT_NAME=${EDGE_TEST_STACK}
EDGE_TEST_IMAGE=${EDGE_TEST_IMAGE}
EDGE_NETWORK=${EDGE_NETWORK}
EOF_EDGE_TEST_ENV

cat > "$OPS_ROOT/compose/edge-test/.env.example" <<'EOF_EDGE_TEST_ENV_EXAMPLE'
COMPOSE_PROJECT_NAME=edge-test
EDGE_TEST_IMAGE=nginx:alpine
EDGE_NETWORK=edge
EOF_EDGE_TEST_ENV_EXAMPLE

chmod 0644 \
  "$OPS_ROOT/compose/edge-test/nginx.conf" \
  "$OPS_ROOT/compose/edge-test/site/index.html" \
  "$OPS_ROOT/compose/edge-test/compose.yaml" \
  "$OPS_ROOT/compose/edge-test/.env.example"
chmod 0600 "$OPS_ROOT/compose/edge-test/.env"
find "$OPS_ROOT/compose/edge-test" -type d -exec chmod 0755 {} +
```

`expose` не публикует порт на VPS. Backend доступен только контейнерам сети `edge`.

---

## 8. Проверить конфигурацию до запуска

```bash
cd "$OPS_ROOT/compose/edge"
docker compose config --quiet

docker compose run --rm --no-deps caddy \
  caddy validate \
    --config /etc/caddy/Caddyfile \
    --adapter caddyfile

cd "$OPS_ROOT/compose/edge-test"
docker compose config --quiet
```

---

## 9. Открыть публичные порты

```bash
sudo ufw allow 80/tcp comment 'Caddy HTTP and ACME'
sudo ufw allow 443/tcp comment 'Caddy HTTPS'
sudo ufw allow 443/udp comment 'Caddy HTTP3'
```

Docker создаёт собственные NAT-правила, поэтому публичные контейнерные порты всегда проверяются через `ss` и `docker ps`, а не только через UFW.

---

## 10. Первый запуск

Сначала запустить backend:

```bash
cd "$OPS_ROOT/compose/edge-test"
docker compose pull
docker compose up -d --remove-orphans
```

Затем Caddy:

```bash
cd "$OPS_ROOT/compose/edge"
docker compose pull
docker compose up -d --remove-orphans
```

Caddy автоматически зарегистрирует ACME-аккаунт, выполнит challenge и сохранит сертификат в `/opt/data/caddy/data`.

---

## 11. Проверить HTTPS и reverse proxy

Проверить origin напрямую, обходя DNS proxy:

```bash
curl \
  --resolve "$EDGE_TEST_DOMAIN:443:$SERVER_PUBLIC_IPV4" \
  --fail \
  --silent \
  --show-error \
  --head \
  "https://$EDGE_TEST_DOMAIN/"
```

Проверить публичный URL:

```bash
curl --fail --silent --show-error \
  "https://$EDGE_TEST_DOMAIN/" \
  | grep -F 'Caddy edge работает'
```

После успешного выпуска сертификата в Cloudflare можно включить оранжевую тучу и установить:

```text
SSL/TLS → Overview → Encryption mode → Full (strict)
```

После включения proxy публичный `dig` будет возвращать IP Cloudflare, а не origin VPS. Для проверки origin продолжайте использовать `curl --resolve`.

---

## 12. Шаблон будущего публичного приложения

Создать каталог с правильным владельцем до записи файлов:

```bash
sudo install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2775 \
  "$OPS_ROOT/compose/_templates/public-app"
```

```bash
cat > "$OPS_ROOT/compose/_templates/public-app/compose.yaml" <<'EOF_PUBLIC_APP'
name: ${COMPOSE_PROJECT_NAME:?Set COMPOSE_PROJECT_NAME}

services:
  app:
    image: ${APP_IMAGE:?Set APP_IMAGE}
    restart: unless-stopped

    expose:
      - "${APP_INTERNAL_PORT:?Set APP_INTERNAL_PORT}"

    networks:
      edge:
        aliases:
          - "${APP_UPSTREAM_ALIAS:?Set APP_UPSTREAM_ALIAS}"
      app-internal:

    security_opt:
      - no-new-privileges=true

    pids_limit: ${APP_PIDS_LIMIT:-256}
    mem_limit: ${APP_MEMORY_LIMIT:-512m}
    cpus: ${APP_CPU_LIMIT:-1.00}

    labels:
      ops.managed-by: docker-compose
      ops.host-published: "false"

networks:
  edge:
    external: true
    name: ${EDGE_NETWORK:?Set EDGE_NETWORK}

  app-internal:
    internal: true
EOF_PUBLIC_APP

cat > "$OPS_ROOT/compose/_templates/public-app/.env.example" <<'EOF_PUBLIC_APP_ENV'
COMPOSE_PROJECT_NAME=myapp
APP_IMAGE=ghcr.io/owner/myapp:1.0.0
APP_INTERNAL_PORT=8000
APP_UPSTREAM_ALIAS=myapp-web
APP_PIDS_LIMIT=256
APP_MEMORY_LIMIT=512m
APP_CPU_LIMIT=1.00
EDGE_NETWORK=edge
EOF_PUBLIC_APP_ENV

chmod 0664 \
  "$OPS_ROOT/compose/_templates/public-app/compose.yaml" \
  "$OPS_ROOT/compose/_templates/public-app/.env.example"
```

Только HTTP frontend подключается к `edge`. DB и Redis остаются в `app-internal`.

---

## 13. Добавление нового Caddy site

Создать скрипт, который принимает конкретные значения аргументами, проверяет конфигурацию и делает reload:

```bash
cat > "$OPS_ROOT/scripts/caddy-add-site.sh" <<'EOF_ADD_SITE'
#!/usr/bin/env bash
set -Eeuo pipefail

source /etc/vps-guide/config.env

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s DOMAIN UPSTREAM\n' "$0" >&2
  printf 'Example: %s app.example.com app-web:8000\n' "$0" >&2
  exit 2
fi

DOMAIN="${1,,}"
UPSTREAM="$2"
SITE_DIR="$OPS_ROOT/config/caddy/sites"
SITE_FILE="$SITE_DIR/$DOMAIN.caddy"
TEMP_FILE="$(mktemp)"
BACKUP_FILE=""
trap 'rm -f "$TEMP_FILE"' EXIT

python3 - "$DOMAIN" "$UPSTREAM" <<'PY'
import re
import sys

domain, upstream = sys.argv[1:]
if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
    raise SystemExit(f"Invalid domain: {domain}")
if not re.fullmatch(r"[a-zA-Z0-9_.-]+:[0-9]{1,5}", upstream):
    raise SystemExit(f"Invalid upstream: {upstream}")
PY

cat > "$TEMP_FILE" <<EOF_SITE
$DOMAIN {
\timport common
\treverse_proxy $UPSTREAM
}
EOF_SITE

if [[ -e "$SITE_FILE" ]]; then
  BACKUP_FILE="$SITE_FILE.backup.$(date +%F-%H%M%S)"
  cp -a "$SITE_FILE" "$BACKUP_FILE"
fi

install -m 0644 "$TEMP_FILE" "$SITE_FILE"

cd "$OPS_ROOT/compose/edge"
if ! docker compose run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  if [[ -n "$BACKUP_FILE" ]]; then
    mv "$BACKUP_FILE" "$SITE_FILE"
  else
    rm -f "$SITE_FILE"
  fi
  printf 'Validation failed; previous configuration restored.\n' >&2
  exit 1
fi

if ! docker compose exec -T -w /etc/caddy caddy \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  if [[ -n "$BACKUP_FILE" ]]; then
    mv "$BACKUP_FILE" "$SITE_FILE"
  else
    rm -f "$SITE_FILE"
  fi

  docker compose exec -T -w /etc/caddy caddy \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true

  printf 'Reload failed; previous configuration restored.\n' >&2
  exit 1
fi

[[ -z "$BACKUP_FILE" ]] || rm -f "$BACKUP_FILE"
printf 'Configured: https://%s -> %s\n' "$DOMAIN" "$UPSTREAM"
EOF_ADD_SITE

chmod 0750 "$OPS_ROOT/scripts/caddy-add-site.sh"
```

Пример после создания DNS-записи и запуска приложения:

```bash
"$OPS_ROOT/scripts/caddy-add-site.sh" \
  app.example.com \
  app-web:8000
```

Замените примерные значения на реальные. Не создавайте каталог или файл с буквальным именем placeholder.

---

## 14. Эксплуатация Caddy

### Безопасный reload после изменения конфигурации

```bash
cd "$OPS_ROOT/compose/edge"

docker compose run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

docker compose exec -T -w /etc/caddy caddy \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

### Обновление image

Тег закреплён в общей конфигурации. Обновление выполняется осознанно: сначала изменить `CaddyImage` в Windows `config.ps1`, повторно экспортировать Linux env и обновить `/etc/vps-guide/config.env`, затем пересоздать локальный `.env` стека или изменить его вручную.

После изменения версии:

```bash
cd "$OPS_ROOT/compose/edge"
docker compose pull
docker compose up -d --remove-orphans
docker compose logs --since=5m caddy
```

### Резервная копия TLS state

До внедрения restic можно создать локальный архив:

```bash
sudo install -d -o root -g "$OPS_GROUP" -m 2770 "$BACKUPS_ROOT/caddy"

sudo tar \
  --create \
  --gzip \
  --file "$BACKUPS_ROOT/caddy/caddy-state-$(date +%F-%H%M%S).tar.gz" \
  -C "$DATA_ROOT/caddy" \
  data config
```

Каталог `/opt/data/caddy` содержит ACME account, сертификаты и ключи и должен входить в регулярные зашифрованные резервные копии.

---

## 15. Git-фиксация

```bash
git -C "$OPS_ROOT" add \
  compose/edge/compose.yaml \
  compose/edge/.env.example \
  compose/edge-test/compose.yaml \
  compose/edge-test/.env.example \
  compose/edge-test/nginx.conf \
  compose/edge-test/site/index.html \
  compose/_templates/public-app \
  config/caddy \
  scripts/caddy-add-site.sh

git -C "$OPS_ROOT" commit -m 'Configure Caddy edge and automatic HTTPS'
```

Проверить, что локальные env-файлы игнорируются:

```bash
git -C "$OPS_ROOT" check-ignore -v \
  compose/edge/.env \
  compose/edge-test/.env
```

---

## 16. Финальная проверка

```bash
cd "$OPS_ROOT/compose/edge"
docker compose ps
docker compose exec -T caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

cd "$OPS_ROOT/compose/edge-test"
docker compose ps

curl -fsS "https://$EDGE_TEST_DOMAIN/" \
  | grep -F 'Caddy edge работает'

sudo ss -lntup | grep -E ':(80|443)\b'
```

---

# Диагностика и типичные проблемы

## A. `open /etc/caddy/Caddyfile: permission denied`

При `cap_drop: ALL` контейнер не должен зависеть от capability обхода файловых прав. Проверить весь путь:

```bash
namei -l "$OPS_ROOT/config/caddy/Caddyfile"
```

Исправить read-only конфигурацию:

```bash
sudo find "$OPS_ROOT/config/caddy" -type d -exec chmod 0755 {} +
sudo find "$OPS_ROOT/config/caddy" -type f -exec chmod 0644 {} +
```

## B. Edge-test получает `403 Permission denied`

Проверить путь к странице:

```bash
namei -l "$OPS_ROOT/compose/edge-test/site/index.html"
```

Исправить:

```bash
sudo find "$OPS_ROOT/compose/edge-test" -type d -exec chmod 0755 {} +
sudo chmod 0644 \
  "$OPS_ROOT/compose/edge-test/nginx.conf" \
  "$OPS_ROOT/compose/edge-test/site/index.html"

cd "$OPS_ROOT/compose/edge-test"
docker compose up -d --force-recreate --remove-orphans
```

## C. `install` или `cat > file` возвращает `Permission denied`

Каталог мог быть создан через `sudo` с владельцем `root`. Назначить владельца конкретному рабочему каталогу:

```bash
sudo chown -R "$ADMIN_USER:$OPS_GROUP" \
  "$OPS_ROOT/compose/_templates/public-app"
sudo chmod -R g+rwX "$OPS_ROOT/compose/_templates/public-app"
sudo find "$OPS_ROOT/compose/_templates/public-app" -type d -exec chmod g+s {} +
```

Не применяйте `chown -R` ко всему `/opt/data` без знания UID/GID работающих сервисов.

## D. DNS показывает IP Cloudflare вместо VPS

Это штатно для записи в режиме **Proxied**. Проверка равенства `dig` и origin IP применима только к **DNS only**.

Origin проверяется так:

```bash
curl \
  --resolve "$EDGE_TEST_DOMAIN:443:$SERVER_PUBLIC_IPV4" \
  --head \
  "https://$EDGE_TEST_DOMAIN/"
```

## E. ACME `tls-alpn-01` завершается ошибкой за Cloudflare

Cloudflare принимает TLS раньше Caddy, поэтому TLS-ALPN challenge может не дойти до origin. Для первого выпуска переведите запись в DNS only. Caddy также может переключиться на HTTP-01, но прямой DNS упрощает диагностику.

После успешной строки:

```text
certificate obtained successfully
```

можно включить proxy и Full (strict).

## F. `openssl s_client` показывает wildcard-сертификат Cloudflare

При обычном подключении к proxied hostname команда проверяет edge-сертификат Cloudflare, а не origin Caddy. Для origin использовать `openssl` с публичным IP VPS:

```bash
openssl s_client \
  -connect "$SERVER_PUBLIC_IPV4:443" \
  -servername "$EDGE_TEST_DOMAIN" \
  </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

## G. `docker compose port web 8080` не показывает адрес

У backend используется `expose`, а не `ports`. Это ожидаемо. Проверить из самого контейнера:

```bash
cd "$OPS_ROOT/compose/edge-test"
docker compose exec -T web wget -qO- http://127.0.0.1:8080/
```

На host порт `8080` не должен слушаться:

```bash
sudo ss -lntp | grep ':8080\b' || echo 'Port 8080 is not published'
```

## H. Caddyfile не отформатирован

Проверить diff без изменения read-only mount:

```bash
cd "$OPS_ROOT/compose/edge"
docker compose run --rm --no-deps caddy \
  caddy fmt --diff /etc/caddy/Caddyfile
```

Основной Caddyfile этой главы уже отформатирован. Не используйте `--overwrite` внутри контейнера, когда `/etc/caddy` подключён read-only.

## I. Ошибка `502 Bad Gateway`

Проверить membership и DNS alias:

```bash
docker network inspect "$EDGE_NETWORK" \
  | jq '.[0].Containers | to_entries | map(.value.Name)'

cd "$OPS_ROOT/compose/edge"
docker compose exec -T caddy \
  wget -qO- "http://$EDGE_TEST_UPSTREAM/"
```

Caddy и frontend должны находиться в одной сети `edge`, а upstream должен слушать указанный внутренний порт.

## J. Новые ошибки Caddy

```bash
cd "$OPS_ROOT/compose/edge"
docker compose logs --since=10m caddy \
  | rg '"level":"(error|panic|fatal)"' \
  || echo 'Новых критических ошибок Caddy нет'
```

Запросы к `/.env`, `/.git/HEAD`, `wp-login.php` и другим известным путям — обычное автоматическое сканирование интернета. Ответ `404` означает, что файл не раскрыт.

## K. HTTP/3 сообщает о маленьком UDP receive buffer

Сообщение quic-go о невозможности увеличить UDP buffer обычно не блокирует HTTP/1.1, HTTP/2 или базовую работу HTTP/3. Настройку host sysctl следует делать отдельно после измерения нагрузки, а не как обязательную часть первого запуска.

## L. Проверка bind mounts

```bash
caddy_id="$(docker compose -f "$OPS_ROOT/compose/edge/compose.yaml" ps -q caddy)"
docker inspect "$caddy_id" \
  | jq '.[0].Mounts | map({Source, Destination, RW})'
```

Ожидается:

- `/etc/caddy` — `RW: false`;
- `/data` и `/config` — `RW: true`.

---

## Официальная документация

- Caddy automatic HTTPS: https://caddyserver.com/docs/automatic-https
- Caddy reverse_proxy: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- Caddy Docker image: https://hub.docker.com/_/caddy
- Caddy command line: https://caddyserver.com/docs/command-line
- Docker bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Cloudflare proxy status: https://developers.cloudflare.com/dns/proxy-status/
- Cloudflare Full (strict): https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
