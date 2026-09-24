# Глава 10. Production backups: restic, off-site S3, PostgreSQL dump, retention и monitoring

Эта глава добавляет к single-VPS инфраструктуре полноценный **encrypted off-site backup layer**.

После выполнения главы:

- `restic` установлен фиксированной версией с проверкой SHA-256;
- backup repository находится **вне VPS** в приватном S3-compatible object storage;
- repository зашифрован отдельным случайным restic password;
- S3 credentials и restic password хранятся в Git только через SOPS;
- plaintext runtime credentials доступны только `root` с mode `0600`;
- GlitchTip PostgreSQL сохраняется через консистентный `pg_dump -Fc`, а не копированием live PGDATA;
- Grafana SQLite state сохраняется через SQLite online backup API, а не копированием live `grafana.db`;
- `/opt/ops`, `/opt/apps`, важные `/opt/data`, Caddy ACME state, SSH/SOPS recovery material и системная конфигурация входят в backup;
- high-churn/reconstructable observability runtime state и plaintext runtime secrets исключены;
- ежедневный backup запускается systemd timer;
- retention и `prune` запускаются отдельным weekly maintenance timer;
- repository регулярно проверяется через `restic check --read-data-subset`;
- локальный `flock` и `restic --retry-lock` не позволяют backup/maintenance конфликтовать друг с другом;
- Prometheus получает timestamp последнего успешного backup через node_exporter textfile collector;
- Alertmanager отправляет Telegram alert при failed backup, failed maintenance или слишком старом backup;
- первый off-site snapshot создаётся вручную до включения timers;
- в Git попадают только scripts/config/systemd units и encrypted `backup.enc.yaml`.

> Команды рассчитаны на Ubuntu 24.04 после успешно завершённой главы 09.
>
> В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, **не переходите к следующему номеру шага**, пока причина не устранена.
>
> В этой главе backup **не считается проверенным disaster recovery**. Полный restore на чистую директорию и runbook восстановления VPS будут выполнены в главе 11.

---

## 0. Что именно строим

```text
                               GitHub private repository
                                         |
                                         | encrypted only
                                         v
/opt/ops/secrets/backup.enc.yaml ---- SOPS + age
                                         |
                                         | decrypt only on VPS
                                         v
/opt/data/backups/secrets/ -------- root:root 0700
├── repository --------------------- 0600
├── password ----------------------- 0600
├── aws_access_key_id -------------- 0600
├── aws_secret_access_key ---------- 0600
└── aws_default_region ------------- 0600
                                         |
                                         v
                                  restic wrapper
                                         |
                    +--------------------+--------------------+
                    |                                         |
                    v                                         v
             daily backup                              weekly maintenance
                    |                                         |
                    | pg_dump -Fc                             | forget --prune
                    | Grafana SQLite backup                  | repository check
                    | files/config/state                      |
                    v                                         v
             encrypted snapshot  ----------------------> off-site S3
                    |
                    v
        node_exporter textfile metrics
                    |
                    v
          Prometheus -> Alertmanager -> Telegram
```

Главный принцип:

```text
Git repository != backup
same VPS disk   != backup
Docker volume   != backup
restic snapshot on remote storage = backup copy
successful restore                  = verified backup
```

### Что намеренно не копируем как live filesystem

PostgreSQL data directory:

```text
/opt/data/error-tracking/postgres
```

не копируется напрямую.

Вместо него каждый backup создаёт:

```text
/opt/backups/staging/current/databases/glitchtip.dump
```

через `pg_dump -Fc` внутри текущего PostgreSQL container.

Также не отправляем off-site текущие Prometheus/Loki/Alloy runtime databases. Для VPS с 60 GB диска это высокочастотные, reconstructable данные, которые резко увеличивают churn и стоимость backup без сопоставимой recovery-ценности.

Live Grafana data directory также не копируется вслепую. Вместо этого каждый backup создаёт консистентную SQLite-копию:

```text
/opt/backups/staging/current/databases/grafana.db
```

через Python `sqlite3.Connection.backup()`, после чего выполняет `PRAGMA integrity_check`.

Versioned observability configuration уже хранится в `/opt/ops` и входит в backup.

---

## 1. Выполнить preflight главы 10

Загрузить текущую конфигурацию:

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${BACKUPS_ROOT:?BACKUPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
```

Создать временный preflight script вне Git repository:

````bash
PREFLIGHT_SCRIPT="$(mktemp)"
chmod 0700 "$PREFLIGHT_SCRIPT"

cat > "$PREFLIGHT_SCRIPT" <<'EOF_CH10_PREFLIGHT'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT DATA_ROOT BACKUPS_ROOT ADMIN_USER OPS_GROUP \
  SERVER_HOSTNAME GITHUB_REMOTE \
  ERROR_TRACKING_ROOT ERROR_TRACKING_STACK \
  OBSERVABILITY_ROOT OBSERVABILITY_STACK \
  SOPS_AGE_KEY_FILE SOPS_CONFIG \
  SOPS_OBSERVABILITY_FILE SOPS_ERROR_TRACKING_FILE SOPS_REGISTRY_FILE; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s, not as %s\n' "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}

for command in \
  curl docker flock git jq python3 sha256sum sops systemctl; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

[[ -d "$OPS_ROOT/.git" ]] || {
  printf 'ERROR: %s is not a Git repository\n' "$OPS_ROOT" >&2
  exit 1
}

[[ -z "$(git -C "$OPS_ROOT" status --porcelain)" ]] || {
  printf 'ERROR: %s has uncommitted changes\n' "$OPS_ROOT" >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

[[ "$(git -C "$OPS_ROOT" remote get-url origin)" == "$GITHUB_REMOTE" ]] || {
  printf 'ERROR: origin differs from GITHUB_REMOTE\n' >&2
  exit 1
}

git -C "$OPS_ROOT" fetch --quiet origin main
LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"

[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ\n' >&2
  printf 'local:  %s\nremote: %s\n' "$LOCAL_SHA" "$REMOTE_SHA" >&2
  exit 1
}

for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE" \
  "$SOPS_AGE_KEY_FILE"; do
  [[ -s "$file" ]] || {
    printf 'ERROR: required SOPS/age file is missing: %s\n' "$file" >&2
    exit 1
  }
done

export SOPS_AGE_KEY_FILE SOPS_CONFIG
for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  sops decrypt --output-type json "$file" >/dev/null
 done

for project in "$OBSERVABILITY_STACK" "$ERROR_TRACKING_STACK"; do
  ids="$({
    docker ps \
      --filter "label=com.docker.compose.project=$project" \
      --format '{{.ID}}'
  })"

  [[ -n "$ids" ]] || {
    printf 'ERROR: Docker Compose project is not running: %s\n' "$project" >&2
    exit 1
  }
done

POSTGRES_ID="$(
  docker compose \
    --project-name "$ERROR_TRACKING_STACK" \
    --project-directory "$ERROR_TRACKING_ROOT" \
    --file "$ERROR_TRACKING_ROOT/compose.yaml" \
    ps -q postgres
)"

[[ -n "$POSTGRES_ID" ]] || {
  printf 'ERROR: GlitchTip PostgreSQL container not found\n' >&2
  exit 1
}

[[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$POSTGRES_ID")" == "healthy" ]] || {
  printf 'ERROR: GlitchTip PostgreSQL is not healthy\n' >&2
  exit 1
}

printf 'Chapter 10 preflight passed: %s\n' "$LOCAL_SHA"
EOF_CH10_PREFLIGHT

"$PREFLIGHT_SCRIPT"
PREFLIGHT_STATUS=$?

rm -f -- "$PREFLIGHT_SCRIPT"
unset PREFLIGHT_SCRIPT

if [[ "$PREFLIGHT_STATUS" -ne 0 ]]; then
  printf 'ERROR: Chapter 10 preflight failed. Исправьте ошибку выше и повторите шаг 1.\n' >&2
  unset PREFLIGHT_STATUS
  false
else
  unset PREFLIGHT_STATUS
fi
````

Ожидаемая последняя строка:

```text
Chapter 10 preflight passed: <git-commit-sha>
```

---

## 2. Подготовить off-site S3 bucket

Нужен **отдельный bucket у внешнего object-storage provider**. Bucket не должен находиться на этом VPS.

Создать bucket со следующими параметрами:

| Параметр | Требование |
| --- | --- |
| Public access | disabled |
| Bucket purpose | только backups этого VPS |
| Encryption at rest provider-side | enabled, если provider поддерживает |
| Versioning | enabled, если provider поддерживает |
| Object Lock / Compliance Lock | **не включать** для этого repository |
| Access key | отдельный key, scoped только к backup bucket |
| Permanent version deletion | deny для VPS key, если provider разделяет обычный delete и purge old versions |
| S3 API | HTTPS only |

Для следующего шага подготовить пять значений:

```text
S3 endpoint host     например: s3.example-provider.com
S3 bucket name       например: my-vps-backups
S3 region            например: eu-central-1
S3 access key ID
S3 secret access key
```

Не вставляйте access key в `config.env`, shell history, Compose `.env` или Git plaintext.

Если provider поддерживает versioning, желательно оставлять non-current object versions минимум 30 дней и не выдавать VPS credential право на их безвозвратное удаление. Тогда обычный restic prune продолжает работать с current objects, а provider-side versions дают дополнительное окно восстановления после ошибочного/вредоносного delete.

> Restic `forget --prune` должен удалять устаревшие repository objects, поэтому provider-side immutable Object Lock в default workflow не включаем. Если нужен append-only/ransomware-resistant repository с отдельным maintenance credential — это отдельная более строгая схема и не должна смешиваться с обычным automated prune.

---

## 3. Установить фиксированную версию restic

В этой главе фиксируем:

```text
restic 0.19.1
```

Официальный release опубликован 2026-07-05.

Installer:

- определяет `amd64`/`arm64`;
- скачивает exact release artifact с GitHub;
- проверяет pinned SHA-256;
- распаковывает через Python `bz2`, без `curl | sh`;
- устанавливает binary как `/usr/local/bin/restic` с `root:root 0755`;
- проверяет фактическую версию.

````bash
cat > "$OPS_ROOT/scripts/chapter-10-install-restic.sh" <<'EOF_CH10_INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail

RESTIC_VERSION="0.19.1"
HTTPS_SCHEME="https"
GITHUB_HOST="github.com"

for command in curl dpkg install mktemp python3 sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

case "$(dpkg --print-architecture)" in
  amd64)
    RESTIC_ARCH="amd64"
    RESTIC_SHA256="f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c"
    ;;
  arm64)
    RESTIC_ARCH="arm64"
    RESTIC_SHA256="a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465"
    ;;
  *)
    printf 'ERROR: unsupported architecture: %s\n' "$(dpkg --print-architecture)" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT INT TERM

ARCHIVE="$TMP_DIR/restic.bz2"
BINARY="$TMP_DIR/restic"
URL="${HTTPS_SCHEME}://${GITHUB_HOST}/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_${RESTIC_ARCH}.bz2"

curl \
  --proto '=https' \
  --tlsv1.2 \
  --fail \
  --silent \
  --show-error \
  --location \
  --retry 3 \
  --retry-all-errors \
  --connect-timeout 15 \
  --max-time 300 \
  --output "$ARCHIVE" \
  "$URL"

printf '%s  %s\n' "$RESTIC_SHA256" "$ARCHIVE" | sha256sum --check --status || {
  printf 'ERROR: restic SHA-256 verification failed\n' >&2
  exit 1
}

python3 - "$ARCHIVE" "$BINARY" <<'PY_DECOMPRESS'
from pathlib import Path
import bz2
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

with bz2.open(src, "rb") as source, dst.open("wb") as target:
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        target.write(chunk)
PY_DECOMPRESS

chmod 0755 "$BINARY"
sudo install -o root -g root -m 0755 "$BINARY" /usr/local/bin/restic

ACTUAL_VERSION="$(restic version | awk '{print $2}')"
[[ "$ACTUAL_VERSION" == "$RESTIC_VERSION" ]] || {
  printf 'ERROR: installed restic version=%s expected=%s\n' \
    "$ACTUAL_VERSION" "$RESTIC_VERSION" >&2
  exit 1
}

printf 'restic %s installed successfully.\n' "$ACTUAL_VERSION"
EOF_CH10_INSTALL

chmod 0750 "$OPS_ROOT/scripts/chapter-10-install-restic.sh"
"$OPS_ROOT/scripts/chapter-10-install-restic.sh"
````

Ожидается:

```text
restic 0.19.1 installed successfully.
```

---

## 4. Создать production backup layer

Следующий installer создаёт весь основной backup contract одной командой:

```text
/opt/ops/config/backup/
├── excludes.txt
└── systemd/
    ├── vps-backup.service
    ├── vps-backup.timer
    ├── vps-backup-maintenance.service
    └── vps-backup-maintenance.timer

/opt/ops/scripts/
├── backup-materialize.py
├── grafana-sqlite-backup.py
├── backup-secrets-setup.sh
├── restic-wrapper.sh
├── backup-run.sh
├── backup-maintenance.sh
└── backup-status.sh

/opt/data/backups/secrets/       root-only runtime projection
/opt/backups/staging/            temporary consistent staging
/opt/backups/restic-cache/       local restic cache
/opt/backups/state/              last-success state
/opt/data/observability/textfile node_exporter metrics
```

Он также:

- добавляет Chapter 10 variables в `$HOME/config.env`;
- добавляет `SOPS_BACKUP_FILE`;
- подключает node_exporter textfile collector;
- добавляет Prometheus backup alerts;
- создаёт systemd unit files в Git и устанавливает их в `/etc/systemd/system`;
- **не включает timers автоматически**;
- не перезаписывает существующий `backup.enc.yaml`;
- не выводит secrets.

````bash
cat > "$OPS_ROOT/scripts/chapter-10-configure.sh" <<'EOF_CH10_CONFIGURE'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${BACKUPS_ROOT:?BACKUPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"
: "${OBSERVABILITY_ROOT:?OBSERVABILITY_ROOT is not set}"
: "${OBSERVABILITY_CONFIG_ROOT:?OBSERVABILITY_CONFIG_ROOT is not set}"
: "${OBSERVABILITY_DATA_ROOT:?OBSERVABILITY_DATA_ROOT is not set}"
: "${ERROR_TRACKING_ROOT:?ERROR_TRACKING_ROOT is not set}"
: "${ERROR_TRACKING_STACK:?ERROR_TRACKING_STACK is not set}"
: "${SOPS_SECRETS_ROOT:?SOPS_SECRETS_ROOT is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in git install python3 sudo systemctl; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

RESTIC_VERSION="0.19.1"
BACKUP_CONFIG_ROOT="$OPS_ROOT/config/backup"
BACKUP_SYSTEMD_ROOT="$BACKUP_CONFIG_ROOT/systemd"
BACKUP_DATA_ROOT="$DATA_ROOT/backups"
BACKUP_SECRETS_ROOT="$BACKUP_DATA_ROOT/secrets"
BACKUP_STAGING_ROOT="$BACKUPS_ROOT/staging"
RESTIC_CACHE_ROOT="$BACKUPS_ROOT/restic-cache"
BACKUP_STATE_ROOT="$BACKUPS_ROOT/state"
BACKUP_METRICS_ROOT="$OBSERVABILITY_DATA_ROOT/textfile"
BACKUP_EXCLUDES_FILE="$BACKUP_CONFIG_ROOT/excludes.txt"
SOPS_BACKUP_FILE="$SOPS_SECRETS_ROOT/backup.enc.yaml"
RESTIC_RETRY_LOCK="5m"
BACKUP_LOCAL_LOCK_WAIT="1800"
RESTIC_KEEP_DAILY="14"
RESTIC_KEEP_WEEKLY="8"
RESTIC_KEEP_MONTHLY="12"
RESTIC_KEEP_YEARLY="3"
BACKUP_MAX_AGE_SECONDS="108000"

install -d \
  -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$BACKUP_CONFIG_ROOT" \
  "$BACKUP_SYSTEMD_ROOT"

sudo install -d -o root -g root -m 0700 \
  "$BACKUP_DATA_ROOT" \
  "$BACKUP_SECRETS_ROOT" \
  "$BACKUP_STAGING_ROOT" \
  "$RESTIC_CACHE_ROOT" \
  "$BACKUP_STATE_ROOT"

sudo install -d -o root -g root -m 0755 "$BACKUP_METRICS_ROOT"

CONFIG_BLOCK="$(mktemp)"
OUTPUT_FILE="$(mktemp)"
cleanup() {
  rm -f -- "$CONFIG_BLOCK" "$OUTPUT_FILE"
}
trap cleanup EXIT INT TERM

cat > "$CONFIG_BLOCK" <<EOF_CONFIG
# =============================================================================
# BACKUPS — restic encrypted off-site backup
# =============================================================================

# BEGIN VPS GUIDE CHAPTER 10
export RESTIC_VERSION=${RESTIC_VERSION}
export BACKUP_CONFIG_ROOT=${BACKUP_CONFIG_ROOT}
export BACKUP_SYSTEMD_ROOT=${BACKUP_SYSTEMD_ROOT}
export BACKUP_DATA_ROOT=${BACKUP_DATA_ROOT}
export BACKUP_SECRETS_ROOT=${BACKUP_SECRETS_ROOT}
export BACKUP_STAGING_ROOT=${BACKUP_STAGING_ROOT}
export RESTIC_CACHE_ROOT=${RESTIC_CACHE_ROOT}
export BACKUP_STATE_ROOT=${BACKUP_STATE_ROOT}
export BACKUP_METRICS_ROOT=${BACKUP_METRICS_ROOT}
export BACKUP_EXCLUDES_FILE=${BACKUP_EXCLUDES_FILE}
export SOPS_BACKUP_FILE=${SOPS_BACKUP_FILE}
export RESTIC_RETRY_LOCK=${RESTIC_RETRY_LOCK}
export BACKUP_LOCAL_LOCK_WAIT=${BACKUP_LOCAL_LOCK_WAIT}
export RESTIC_KEEP_DAILY=${RESTIC_KEEP_DAILY}
export RESTIC_KEEP_WEEKLY=${RESTIC_KEEP_WEEKLY}
export RESTIC_KEEP_MONTHLY=${RESTIC_KEEP_MONTHLY}
export RESTIC_KEEP_YEARLY=${RESTIC_KEEP_YEARLY}
export BACKUP_MAX_AGE_SECONDS=${BACKUP_MAX_AGE_SECONDS}
# END VPS GUIDE CHAPTER 10
EOF_CONFIG

python3 - "$VPS_GUIDE_CONFIG" "$CONFIG_BLOCK" "$OUTPUT_FILE" <<'PY_CONFIG'
from pathlib import Path
import re
import sys

config_path = Path(sys.argv[1])
block_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

begin = "# BEGIN VPS GUIDE CHAPTER 10"
end = "# END VPS GUIDE CHAPTER 10"
managed = {
    "RESTIC_VERSION",
    "BACKUP_CONFIG_ROOT",
    "BACKUP_SYSTEMD_ROOT",
    "BACKUP_DATA_ROOT",
    "BACKUP_SECRETS_ROOT",
    "BACKUP_STAGING_ROOT",
    "RESTIC_CACHE_ROOT",
    "BACKUP_STATE_ROOT",
    "BACKUP_METRICS_ROOT",
    "BACKUP_EXCLUDES_FILE",
    "SOPS_BACKUP_FILE",
    "RESTIC_RETRY_LOCK",
    "BACKUP_LOCAL_LOCK_WAIT",
    "RESTIC_KEEP_DAILY",
    "RESTIC_KEEP_WEEKLY",
    "RESTIC_KEEP_MONTHLY",
    "RESTIC_KEEP_YEARLY",
    "BACKUP_MAX_AGE_SECONDS",
}
pattern = re.compile(
    r"^\s*export\s+(" + "|".join(sorted(map(re.escape, managed))) + r")="
)

lines = config_path.read_text(encoding="utf-8").splitlines()
out = []
in_block = False

for line in lines:
    stripped = line.strip()
    if stripped == begin:
        in_block = True
        continue
    if in_block:
        if stripped == end:
            in_block = False
        continue
    if pattern.match(line):
        continue
    out.append(line)

while out and not out[-1].strip():
    out.pop()

block = block_path.read_text(encoding="utf-8").rstrip()
content = "\n".join(out).rstrip()
if content:
    content += "\n\n"
content += block + "\n"
output_path.write_text(content, encoding="utf-8")
PY_CONFIG

chmod 0600 "$OUTPUT_FILE"
mv -f "$OUTPUT_FILE" "$VPS_GUIDE_CONFIG"
chmod 0600 "$VPS_GUIDE_CONFIG"

# Reload variables added above.
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

cat > "$BACKUP_EXCLUDES_FILE" <<EOF_EXCLUDES
# Live PostgreSQL files are never copied. backup-run.sh creates pg_dump -Fc.
${DATA_ROOT}/error-tracking/postgres
${DATA_ROOT}/error-tracking/postgres/**

# Runtime plaintext secrets already have encrypted SOPS source-of-truth.
${DATA_ROOT}/error-tracking/secrets
${DATA_ROOT}/error-tracking/secrets/**
${DATA_ROOT}/docker-auth
${DATA_ROOT}/docker-auth/**
${BACKUP_DATA_ROOT}
${BACKUP_DATA_ROOT}/**

# High-churn/reconstructable observability runtime state.
${OBSERVABILITY_DATA_ROOT}
${OBSERVABILITY_DATA_ROOT}/**

EOF_EXCLUDES

chmod 0644 "$BACKUP_EXCLUDES_FILE"

cat > "$OPS_ROOT/scripts/backup-materialize.py" <<'PY_MATERIALIZE'
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

if os.geteuid() != 0:
    raise SystemExit("ERROR: backup-materialize.py must run as root")

if len(sys.argv) != 2:
    raise SystemExit("usage: backup-materialize.py <target-directory>")

target = Path(sys.argv[1])
data = json.load(sys.stdin)

required = {
    "repository": "repository",
    "password": "password",
    "aws_access_key_id": "aws_access_key_id",
    "aws_secret_access_key": "aws_secret_access_key",
    "aws_default_region": "aws_default_region",
}

for key in required:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"ERROR: missing or empty key: {key}")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise SystemExit(f"ERROR: invalid newline/NUL in key: {key}")

target.mkdir(parents=True, exist_ok=True)
os.chown(target, 0, 0)
os.chmod(target, 0o700)

for key, filename in required.items():
    final_path = target / filename
    temp_path = target / f".{filename}.tmp"
    payload = (data[key] + "\n").encode()

    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    os.chown(temp_path, 0, 0)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, final_path)

print("Backup runtime credentials materialized with root-only permissions.")
PY_MATERIALIZE

chmod 0750 "$OPS_ROOT/scripts/backup-materialize.py"

cat > "$OPS_ROOT/scripts/grafana-sqlite-backup.py" <<'PY_GRAFANA_SQLITE'
#!/usr/bin/env python3
import os
from pathlib import Path
import sqlite3
import sys

if os.geteuid() != 0:
    raise SystemExit("ERROR: grafana-sqlite-backup.py must run as root")

if len(sys.argv) != 3:
    raise SystemExit("usage: grafana-sqlite-backup.py <source-db> <target-db>")

os.umask(0o077)
source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])

if not source_path.is_file() or source_path.stat().st_size == 0:
    raise SystemExit(f"ERROR: Grafana SQLite database not found or empty: {source_path}")

target_path.parent.mkdir(parents=True, exist_ok=True)
if target_path.exists():
    target_path.unlink()

source = None
target = None
try:
    source = sqlite3.connect(
        f"file:{source_path}?mode=ro",
        uri=True,
        timeout=30,
    )
    source.execute("PRAGMA query_only = ON")
    target = sqlite3.connect(target_path, timeout=30)
    source.backup(target)

    result = target.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise RuntimeError(f"integrity_check failed: {result!r}")

    target.close()
    target = None
    source.close()
    source = None

    os.chown(target_path, 0, 0)
    os.chmod(target_path, 0o600)
except Exception as exc:
    if target is not None:
        target.close()
    if source is not None:
        source.close()
    target_path.unlink(missing_ok=True)
    raise SystemExit(f"ERROR: Grafana SQLite online backup failed: {exc}") from exc

print("Grafana SQLite online backup passed integrity_check.")
PY_GRAFANA_SQLITE

chmod 0750 "$OPS_ROOT/scripts/grafana-sqlite-backup.py"

cat > "$OPS_ROOT/scripts/backup-secrets-setup.sh" <<'EOF_BACKUP_SECRETS'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  ADMIN_USER OPS_ROOT SOPS_BACKUP_FILE SOPS_AGE_KEY_FILE SOPS_CONFIG \
  BACKUP_SECRETS_ROOT SERVER_HOSTNAME; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in openssl python3 sops sudo; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

export SOPS_AGE_KEY_FILE SOPS_CONFIG

materialize() {
  sops decrypt --output-type json "$SOPS_BACKUP_FILE" |
    sudo "$OPS_ROOT/scripts/backup-materialize.py" "$BACKUP_SECRETS_ROOT"
}

if [[ -s "$SOPS_BACKUP_FILE" ]]; then
  sops decrypt --output-type json "$SOPS_BACKUP_FILE" >/dev/null
  materialize
  printf 'Existing encrypted backup source-of-truth kept unchanged.\n'
  exit 0
fi

printf 'Create/use a dedicated private S3 bucket before continuing.\n'
printf 'Values entered here are encrypted directly into SOPS.\n\n'

IFS= read -r -p 'S3 endpoint host (without https://): ' S3_ENDPOINT
IFS= read -r -p 'S3 bucket name: ' S3_BUCKET
IFS= read -r -p 'S3 region: ' S3_REGION
IFS= read -r -p 'S3 access key ID: ' S3_ACCESS_KEY_ID
IFS= read -r -s -p 'S3 secret access key: ' S3_SECRET_ACCESS_KEY
printf '\n'

for pair in \
  "endpoint:$S3_ENDPOINT" \
  "bucket:$S3_BUCKET" \
  "region:$S3_REGION" \
  "access_key_id:$S3_ACCESS_KEY_ID" \
  "secret_access_key:$S3_SECRET_ACCESS_KEY"; do
  key="${pair%%:*}"
  value="${pair#*:}"
  [[ -n "$value" ]] || {
    printf 'ERROR: %s is empty\n' "$key" >&2
    exit 1
  }
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
    printf 'ERROR: %s contains a newline\n' "$key" >&2
    exit 1
  }
done

[[ "$S3_ENDPOINT" != http://* && "$S3_ENDPOINT" != https://* ]] || {
  printf 'ERROR: enter endpoint host without http:// or https://\n' >&2
  exit 1
}

[[ "$S3_ENDPOINT" != */* ]] || {
  printf 'ERROR: endpoint must be host[:port] only, without path\n' >&2
  exit 1
}

[[ "$S3_BUCKET" =~ ^[A-Za-z0-9._-]+$ ]] || {
  printf 'ERROR: unexpected bucket name format\n' >&2
  exit 1
}

REPOSITORY="s3:https://${S3_ENDPOINT}/${S3_BUCKET}/restic/${SERVER_HOSTNAME}"
RESTIC_PASSWORD="$(openssl rand -base64 48 | tr -d '\n')"

TMP_ENCRYPTED="$(mktemp "${SOPS_BACKUP_FILE}.tmp.XXXXXX")"
cleanup() {
  S3_SECRET_ACCESS_KEY=''
  RESTIC_PASSWORD=''
  rm -f -- "$TMP_ENCRYPTED"
  unset S3_SECRET_ACCESS_KEY RESTIC_PASSWORD
}
trap cleanup EXIT INT TERM

{
  printf '%s\0' \
    "$REPOSITORY" \
    "$RESTIC_PASSWORD" \
    "$S3_ACCESS_KEY_ID" \
    "$S3_SECRET_ACCESS_KEY" \
    "$S3_REGION"
} |
python3 -c '
import json
import sys

parts = sys.stdin.buffer.read().split(b"\0")
if parts and parts[-1] == b"":
    parts.pop()
if len(parts) != 5:
    raise SystemExit("ERROR: internal secret serialization failure")
values = [p.decode() for p in parts]
json.dump({
    "repository": values[0],
    "password": values[1],
    "aws_access_key_id": values[2],
    "aws_secret_access_key": values[3],
    "aws_default_region": values[4],
}, sys.stdout)
' |
sops encrypt \
  --filename-override "$SOPS_BACKUP_FILE" \
  --input-type json \
  --output-type yaml \
  /dev/stdin > "$TMP_ENCRYPTED"

[[ -s "$TMP_ENCRYPTED" ]] || {
  printf 'ERROR: encrypted backup file was not created\n' >&2
  exit 1
}

grep -Fq 'sops:' "$TMP_ENCRYPTED" || {
  printf 'ERROR: encrypted file has no SOPS metadata\n' >&2
  exit 1
}

grep -Fq 'ENC[AES256_GCM,' "$TMP_ENCRYPTED" || {
  printf 'ERROR: encrypted file has no encrypted values\n' >&2
  exit 1
}

chmod 0644 "$TMP_ENCRYPTED"
mv -f "$TMP_ENCRYPTED" "$SOPS_BACKUP_FILE"
chmod 0644 "$SOPS_BACKUP_FILE"

sops decrypt --output-type json "$SOPS_BACKUP_FILE" >/dev/null
materialize

cleanup
trap - EXIT INT TERM

printf 'Encrypted backup credentials created and materialized.\n'
printf 'Repository location is stored in SOPS; secret values were not printed.\n'
EOF_BACKUP_SECRETS

chmod 0750 "$OPS_ROOT/scripts/backup-secrets-setup.sh"

cat > "$OPS_ROOT/scripts/restic-wrapper.sh" <<'EOF_RESTIC_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ -n "${VPS_GUIDE_CONFIG:-}" ]]; then
  :
elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  VPS_GUIDE_CONFIG="/home/${SUDO_USER}/config.env"
else
  VPS_GUIDE_CONFIG="$HOME/config.env"
fi

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in BACKUP_SECRETS_ROOT RESTIC_CACHE_ROOT RESTIC_RETRY_LOCK; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

(( EUID == 0 )) || {
  printf 'ERROR: restic-wrapper.sh must run as root; use sudo\n' >&2
  exit 1
}

for file in \
  repository password aws_access_key_id aws_secret_access_key aws_default_region; do
  path="$BACKUP_SECRETS_ROOT/$file"
  [[ -s "$path" ]] || {
    printf 'ERROR: backup runtime credential missing: %s\n' "$path" >&2
    exit 1
  }
  [[ "$(stat -c '%U:%G:%a' "$path")" == "root:root:600" ]] || {
    printf 'ERROR: unsafe owner/mode for %s\n' "$path" >&2
    exit 1
  }
done

install -d -o root -g root -m 0700 "$RESTIC_CACHE_ROOT"

export RESTIC_REPOSITORY_FILE="$BACKUP_SECRETS_ROOT/repository"
export RESTIC_PASSWORD_FILE="$BACKUP_SECRETS_ROOT/password"
export RESTIC_CACHE_DIR="$RESTIC_CACHE_ROOT"
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION

IFS= read -r AWS_ACCESS_KEY_ID < "$BACKUP_SECRETS_ROOT/aws_access_key_id"
IFS= read -r AWS_SECRET_ACCESS_KEY < "$BACKUP_SECRETS_ROOT/aws_secret_access_key"
IFS= read -r AWS_DEFAULT_REGION < "$BACKUP_SECRETS_ROOT/aws_default_region"

[[ -n "$AWS_ACCESS_KEY_ID" && -n "$AWS_SECRET_ACCESS_KEY" && -n "$AWS_DEFAULT_REGION" ]] || {
  printf 'ERROR: empty S3 runtime credential\n' >&2
  exit 1
}

exec /usr/local/bin/restic \
  --retry-lock "$RESTIC_RETRY_LOCK" \
  "$@"
EOF_RESTIC_WRAPPER

chmod 0750 "$OPS_ROOT/scripts/restic-wrapper.sh"

cat > "$OPS_ROOT/scripts/backup-run.sh" <<'EOF_BACKUP_RUN'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ -n "${VPS_GUIDE_CONFIG:-}" ]]; then
  :
elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  VPS_GUIDE_CONFIG="/home/${SUDO_USER}/config.env"
else
  VPS_GUIDE_CONFIG="$HOME/config.env"
fi

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT APPS_ROOT DATA_ROOT BACKUPS_ROOT ADMIN_USER SERVER_HOSTNAME \
  BACKUP_STAGING_ROOT BACKUP_STATE_ROOT BACKUP_METRICS_ROOT \
  BACKUP_EXCLUDES_FILE ERROR_TRACKING_ROOT ERROR_TRACKING_STACK \
  OBSERVABILITY_DATA_ROOT BACKUP_LOCAL_LOCK_WAIT; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

(( EUID == 0 )) || {
  printf 'ERROR: backup-run.sh must run as root; use sudo\n' >&2
  exit 1
}

for command in \
  date docker dpkg-query flock git install jq mktemp stat systemctl uname; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

[[ -r "$BACKUP_EXCLUDES_FILE" ]] || {
  printf 'ERROR: excludes file missing: %s\n' "$BACKUP_EXCLUDES_FILE" >&2
  exit 1
}

install -d -o root -g root -m 0700 \
  "$BACKUP_STAGING_ROOT" \
  "$BACKUP_STATE_ROOT"
install -d -o root -g root -m 0755 "$BACKUP_METRICS_ROOT"

[[ "$BACKUP_LOCAL_LOCK_WAIT" =~ ^[0-9]+$ ]] || {
  printf 'ERROR: invalid BACKUP_LOCAL_LOCK_WAIT=%s\n' "$BACKUP_LOCAL_LOCK_WAIT" >&2
  exit 1
}

START_TS="$(date +%s)"
LAST_SUCCESS_FILE="$BACKUP_STATE_ROOT/last-success"
METRIC_FILE="$BACKUP_METRICS_ROOT/vps_backup.prom"
STAGE_CURRENT="$BACKUP_STAGING_ROOT/current"
RUN_STATUS=0
LOCK_HELD=0

write_metrics() {
  local now duration last_success tmp
  now="$(date +%s)"
  duration="$(( now - START_TS ))"
  last_success="0"

  if [[ -s "$LAST_SUCCESS_FILE" ]]; then
    IFS= read -r last_success < "$LAST_SUCCESS_FILE"
  fi

  [[ "$last_success" =~ ^[0-9]+$ ]] || last_success="0"

  tmp="$(mktemp "$BACKUP_METRICS_ROOT/.vps_backup.prom.XXXXXX")"
  cat > "$tmp" <<EOF_METRICS
# HELP vps_backup_last_attempt_unixtime Unix timestamp of the latest backup attempt.
# TYPE vps_backup_last_attempt_unixtime gauge
vps_backup_last_attempt_unixtime ${now}
# HELP vps_backup_last_success_unixtime Unix timestamp of the latest successful backup.
# TYPE vps_backup_last_success_unixtime gauge
vps_backup_last_success_unixtime ${last_success}
# HELP vps_backup_last_run_success Whether the latest backup run succeeded (1=yes, 0=no).
# TYPE vps_backup_last_run_success gauge
vps_backup_last_run_success ${RUN_STATUS}
# HELP vps_backup_last_duration_seconds Duration of the latest backup run in seconds.
# TYPE vps_backup_last_duration_seconds gauge
vps_backup_last_duration_seconds ${duration}
EOF_METRICS
  chmod 0644 "$tmp"
  chown root:root "$tmp"
  mv -f "$tmp" "$METRIC_FILE"
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  write_metrics || true
  if (( LOCK_HELD == 1 )); then
    rm -rf -- "$STAGE_CURRENT"
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

exec 9>/run/lock/vps-backup.lock
flock -w "$BACKUP_LOCAL_LOCK_WAIT" 9 || {
  printf 'ERROR: timed out waiting for /run/lock/vps-backup.lock after %s seconds\n' \
    "$BACKUP_LOCAL_LOCK_WAIT" >&2
  exit 75
}
LOCK_HELD=1

# Safety guard before recursive cleanup.
[[ "$STAGE_CURRENT" == "$BACKUPS_ROOT"/staging/current ]] || {
  printf 'ERROR: unsafe staging path: %s\n' "$STAGE_CURRENT" >&2
  exit 1
}

rm -rf -- "$STAGE_CURRENT"
install -d -o root -g root -m 0700 \
  "$STAGE_CURRENT" \
  "$STAGE_CURRENT/databases" \
  "$STAGE_CURRENT/inventory"

printf 'Creating consistent GlitchTip PostgreSQL dump...\n'
DUMP_FILE="$STAGE_CURRENT/databases/glitchtip.dump"
DUMP_TMP="$STAGE_CURRENT/databases/.glitchtip.dump.tmp"

docker compose \
  --project-name "$ERROR_TRACKING_STACK" \
  --project-directory "$ERROR_TRACKING_ROOT" \
  --file "$ERROR_TRACKING_ROOT/compose.yaml" \
  exec -T postgres \
  pg_dump \
    -U glitchtip \
    -d glitchtip \
    -Fc \
    --no-owner \
    --no-privileges > "$DUMP_TMP"

[[ -s "$DUMP_TMP" ]] || {
  printf 'ERROR: PostgreSQL dump is empty\n' >&2
  exit 1
}

# Validate custom-format archive before it is uploaded.
docker compose \
  --project-name "$ERROR_TRACKING_STACK" \
  --project-directory "$ERROR_TRACKING_ROOT" \
  --file "$ERROR_TRACKING_ROOT/compose.yaml" \
  exec -T postgres \
  pg_restore --list < "$DUMP_TMP" >/dev/null

chmod 0600 "$DUMP_TMP"
mv -f "$DUMP_TMP" "$DUMP_FILE"

printf 'Creating consistent Grafana SQLite backup...\n'
GRAFANA_DB="$OBSERVABILITY_DATA_ROOT/grafana/grafana.db"
GRAFANA_BACKUP="$STAGE_CURRENT/databases/grafana.db"

[[ -s "$GRAFANA_DB" ]] || {
  printf 'ERROR: Grafana SQLite database not found: %s\n' "$GRAFANA_DB" >&2
  exit 1
}

"$OPS_ROOT/scripts/grafana-sqlite-backup.py" \
  "$GRAFANA_DB" \
  "$GRAFANA_BACKUP"

printf 'Collecting recovery inventory...\n'
{
  printf 'hostname=%s\n' "$SERVER_HOSTNAME"
  printf 'backup_created_utc=%s\n' "$(date -u +%FT%TZ)"
  printf 'kernel=%s\n' "$(uname -r)"
  printf 'architecture=%s\n' "$(dpkg --print-architecture)"
  printf 'ops_git_head=%s\n' "$(git -C "$OPS_ROOT" rev-parse HEAD)"
} > "$STAGE_CURRENT/inventory/server.txt"

LC_ALL=C dpkg-query -W -f='${binary:Package}\t${Version}\n' \
  > "$STAGE_CURRENT/inventory/packages.tsv"

docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' \
  > "$STAGE_CURRENT/inventory/docker.tsv"

systemctl list-unit-files --state=enabled --no-legend --no-pager \
  > "$STAGE_CURRENT/inventory/systemd-enabled.txt" || true

chmod -R go-rwx "$STAGE_CURRENT"

SOURCES=()
add_source() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    SOURCES+=("$path")
  fi
}

add_source "$OPS_ROOT"
add_source "$APPS_ROOT"
add_source "$DATA_ROOT"
add_source "$STAGE_CURRENT"
add_source "/home/$ADMIN_USER/.ssh"
add_source "/home/$ADMIN_USER/.config/sops/age"
add_source "/home/$ADMIN_USER/config.env"
add_source "/etc"

(( ${#SOURCES[@]} > 0 )) || {
  printf 'ERROR: no backup sources found\n' >&2
  exit 1
}

printf 'Opening remote restic repository...\n'
"$OPS_ROOT/scripts/restic-wrapper.sh" cat config >/dev/null

printf 'Uploading encrypted snapshot...\n'
"$OPS_ROOT/scripts/restic-wrapper.sh" backup \
  --host "$SERVER_HOSTNAME" \
  --tag production \
  --tag vps-guide \
  --group-by host,tags \
  --one-file-system \
  --exclude-file "$BACKUP_EXCLUDES_FILE" \
  "${SOURCES[@]}"

SUCCESS_TS="$(date +%s)"
printf '%s\n' "$SUCCESS_TS" > "$LAST_SUCCESS_FILE.tmp"
chmod 0600 "$LAST_SUCCESS_FILE.tmp"
chown root:root "$LAST_SUCCESS_FILE.tmp"
mv -f "$LAST_SUCCESS_FILE.tmp" "$LAST_SUCCESS_FILE"

RUN_STATUS=1
write_metrics

printf 'Backup completed successfully.\n'
EOF_BACKUP_RUN

chmod 0750 "$OPS_ROOT/scripts/backup-run.sh"

cat > "$OPS_ROOT/scripts/backup-maintenance.sh" <<'EOF_BACKUP_MAINTENANCE'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ -n "${VPS_GUIDE_CONFIG:-}" ]]; then
  :
elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  VPS_GUIDE_CONFIG="/home/${SUDO_USER}/config.env"
else
  VPS_GUIDE_CONFIG="$HOME/config.env"
fi

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT SERVER_HOSTNAME BACKUP_STATE_ROOT BACKUP_METRICS_ROOT \
  BACKUP_LOCAL_LOCK_WAIT \
  RESTIC_KEEP_DAILY RESTIC_KEEP_WEEKLY RESTIC_KEEP_MONTHLY RESTIC_KEEP_YEARLY; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

(( EUID == 0 )) || {
  printf 'ERROR: backup-maintenance.sh must run as root; use sudo\n' >&2
  exit 1
}

for value in \
  "$BACKUP_LOCAL_LOCK_WAIT" \
  "$RESTIC_KEEP_DAILY" "$RESTIC_KEEP_WEEKLY" \
  "$RESTIC_KEEP_MONTHLY" "$RESTIC_KEEP_YEARLY"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    printf 'ERROR: invalid numeric backup setting: %s\n' "$value" >&2
    exit 1
  }
done

install -d -o root -g root -m 0700 "$BACKUP_STATE_ROOT"
install -d -o root -g root -m 0755 "$BACKUP_METRICS_ROOT"

START_TS="$(date +%s)"
LAST_SUCCESS_FILE="$BACKUP_STATE_ROOT/maintenance-last-success"
METRIC_FILE="$BACKUP_METRICS_ROOT/vps_backup_maintenance.prom"
RUN_STATUS=0

write_metrics() {
  local now duration last_success tmp
  now="$(date +%s)"
  duration="$(( now - START_TS ))"
  last_success="0"
  if [[ -s "$LAST_SUCCESS_FILE" ]]; then
    IFS= read -r last_success < "$LAST_SUCCESS_FILE"
  fi
  [[ "$last_success" =~ ^[0-9]+$ ]] || last_success="0"

  tmp="$(mktemp "$BACKUP_METRICS_ROOT/.vps_backup_maintenance.prom.XXXXXX")"
  cat > "$tmp" <<EOF_METRICS
# HELP vps_backup_maintenance_last_success_unixtime Unix timestamp of the latest successful restic maintenance.
# TYPE vps_backup_maintenance_last_success_unixtime gauge
vps_backup_maintenance_last_success_unixtime ${last_success}
# HELP vps_backup_maintenance_last_run_success Whether the latest restic maintenance succeeded.
# TYPE vps_backup_maintenance_last_run_success gauge
vps_backup_maintenance_last_run_success ${RUN_STATUS}
# HELP vps_backup_maintenance_last_duration_seconds Duration of the latest maintenance run.
# TYPE vps_backup_maintenance_last_duration_seconds gauge
vps_backup_maintenance_last_duration_seconds ${duration}
EOF_METRICS
  chmod 0644 "$tmp"
  chown root:root "$tmp"
  mv -f "$tmp" "$METRIC_FILE"
}

finish() {
  local code=$?
  trap - EXIT INT TERM
  write_metrics || true
  exit "$code"
}
trap finish EXIT INT TERM

exec 9>/run/lock/vps-backup.lock
flock -w "$BACKUP_LOCAL_LOCK_WAIT" 9 || {
  printf 'ERROR: timed out waiting for /run/lock/vps-backup.lock after %s seconds\n' \
    "$BACKUP_LOCAL_LOCK_WAIT" >&2
  exit 75
}

printf 'Applying restic retention policy...\n'
"$OPS_ROOT/scripts/restic-wrapper.sh" forget \
  --host "$SERVER_HOSTNAME" \
  --tag production \
  --group-by host,tags \
  --keep-daily "$RESTIC_KEEP_DAILY" \
  --keep-weekly "$RESTIC_KEEP_WEEKLY" \
  --keep-monthly "$RESTIC_KEEP_MONTHLY" \
  --keep-yearly "$RESTIC_KEEP_YEARLY" \
  --prune

# Deterministically check one eighth of repository data each week.
# This limits normal egress/load while still exercising real encrypted packs.
ISO_WEEK="$(date +%V)"
CHECK_PART="$(( 10#$ISO_WEEK % 8 + 1 ))"

printf 'Checking repository metadata and data subset %s/8...\n' "$CHECK_PART"
"$OPS_ROOT/scripts/restic-wrapper.sh" check \
  --read-data-subset="${CHECK_PART}/8"

SUCCESS_TS="$(date +%s)"
printf '%s\n' "$SUCCESS_TS" > "$LAST_SUCCESS_FILE.tmp"
chmod 0600 "$LAST_SUCCESS_FILE.tmp"
chown root:root "$LAST_SUCCESS_FILE.tmp"
mv -f "$LAST_SUCCESS_FILE.tmp" "$LAST_SUCCESS_FILE"

RUN_STATUS=1
write_metrics

printf 'Backup maintenance completed successfully.\n'
EOF_BACKUP_MAINTENANCE

chmod 0750 "$OPS_ROOT/scripts/backup-maintenance.sh"

cat > "$OPS_ROOT/scripts/backup-status.sh" <<'EOF_BACKUP_STATUS'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"
: "${BACKUP_METRICS_ROOT:?BACKUP_METRICS_ROOT is not set}"

printf '## Timers\n'
systemctl list-timers \
  vps-backup.timer \
  vps-backup-maintenance.timer \
  --all \
  --no-pager || true

printf '\n## Latest snapshots\n'
sudo "$OPS_ROOT/scripts/restic-wrapper.sh" snapshots \
  --host "$SERVER_HOSTNAME" \
  --tag production \
  --latest 5

printf '\n## Metrics\n'
for file in \
  "$BACKUP_METRICS_ROOT/vps_backup.prom" \
  "$BACKUP_METRICS_ROOT/vps_backup_maintenance.prom"; do
  if [[ -r "$file" ]]; then
    grep -v '^#' "$file"
  fi
done
EOF_BACKUP_STATUS

chmod 0750 "$OPS_ROOT/scripts/backup-status.sh"

# -----------------------------------------------------------------------------
# Patch node_exporter textfile collector.
# -----------------------------------------------------------------------------
OBS_COMPOSE="$OBSERVABILITY_ROOT/compose.yaml"
[[ -f "$OBS_COMPOSE" ]] || {
  printf 'ERROR: observability Compose not found: %s\n' "$OBS_COMPOSE" >&2
  exit 1
}

python3 - "$OBS_COMPOSE" <<'PY_OBS_COMPOSE'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

flag = "      - --collector.textfile.directory=/textfile\n"
volume = "      - ${BACKUP_METRICS_ROOT:?BACKUP_METRICS_ROOT is not set}:/textfile:ro\n"

if flag not in text:
    needle = "      - --no-collector.timex\n"
    if needle not in text:
        raise SystemExit("ERROR: node-exporter command anchor not found")
    text = text.replace(needle, needle + flag, 1)

if volume not in text:
    needle = "      - /:/host:ro,rslave\n"
    # Restrict replacement to the node-exporter section.
    node_start = text.find("  node-exporter:\n")
    if node_start < 0:
        raise SystemExit("ERROR: node-exporter service not found")
    import re
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[node_start + len("  node-exporter:\n"):])
    if match is None:
        node_end = len(text)
    else:
        search_from = node_start + len("  node-exporter:\n")
        node_end = search_from + match.start()
    section = text[node_start:node_end]
    if needle not in section:
        raise SystemExit("ERROR: node-exporter volume anchor not found")
    section = section.replace(needle, needle + volume, 1)
    text = text[:node_start] + section + text[node_end:]

path.write_text(text, encoding="utf-8")
PY_OBS_COMPOSE

chmod 0644 "$OBS_COMPOSE"

# -----------------------------------------------------------------------------
# Add Prometheus rules as an idempotent managed block.
# -----------------------------------------------------------------------------
PROM_RULES="$OBSERVABILITY_CONFIG_ROOT/prometheus/rules/vps.yml"
[[ -f "$PROM_RULES" ]] || {
  printf 'ERROR: Prometheus rules file not found: %s\n' "$PROM_RULES" >&2
  exit 1
}

python3 - "$PROM_RULES" "$BACKUP_MAX_AGE_SECONDS" <<'PY_RULES'
from pathlib import Path
import sys

path = Path(sys.argv[1])
max_age = int(sys.argv[2])
begin = "# BEGIN VPS GUIDE CHAPTER 10 BACKUP ALERTS"
end = "# END VPS GUIDE CHAPTER 10 BACKUP ALERTS"
text = path.read_text(encoding="utf-8")

if begin in text:
    before, rest = text.split(begin, 1)
    if end not in rest:
        raise SystemExit("ERROR: unterminated Chapter 10 alert block")
    _, after = rest.split(end, 1)
    text = before.rstrip() + "\n" + after.lstrip("\n")

block = f'''{begin}
  - name: backups
    interval: 30s
    rules:
      - alert: BackupLastRunFailed
        expr: vps_backup_last_run_success == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Latest VPS backup failed"
          description: "The latest restic backup run on {{{{ $labels.instance }}}} failed. Check systemctl status vps-backup.service and journalctl -u vps-backup.service."

      - alert: BackupTooOld
        expr: time() - vps_backup_last_success_unixtime > {max_age}
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "VPS backup is too old"
          description: "No successful restic backup has completed within the allowed window on {{{{ $labels.instance }}}}."

      - alert: BackupMetricMissing
        expr: absent(vps_backup_last_success_unixtime)
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "VPS backup metric is missing"
          description: "node_exporter has no vps_backup_last_success_unixtime metric. Check the textfile collector and backup timer."

      - alert: BackupMaintenanceFailed
        expr: vps_backup_maintenance_last_run_success == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Restic maintenance failed"
          description: "The latest restic retention/integrity maintenance run failed."
{end}'''

text = text.rstrip() + "\n\n" + block + "\n"
path.write_text(text, encoding="utf-8")
PY_RULES

chmod 0644 "$PROM_RULES"

# -----------------------------------------------------------------------------
# Versioned systemd units.
# -----------------------------------------------------------------------------
cat > "$BACKUP_SYSTEMD_ROOT/vps-backup.service" <<EOF_SERVICE
[Unit]
Description=VPS encrypted off-site backup with restic
Documentation=https://restic.readthedocs.io/
Wants=network-online.target docker.service
After=network-online.target docker.service
ConditionPathExists=${BACKUP_SECRETS_ROOT}/password

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=VPS_GUIDE_CONFIG=${VPS_GUIDE_CONFIG}
ExecStart=${OPS_ROOT}/scripts/backup-run.sh
TimeoutStartSec=4h
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=${BACKUPS_ROOT} ${BACKUP_METRICS_ROOT} /run/lock
ReadOnlyPaths=${OPS_ROOT} ${DATA_ROOT} /home/${ADMIN_USER} /etc
StandardOutput=journal
StandardError=journal
EOF_SERVICE

cat > "$BACKUP_SYSTEMD_ROOT/vps-backup.timer" <<'EOF_TIMER'
[Unit]
Description=Daily encrypted off-site VPS backup

[Timer]
OnCalendar=*-*-* 03:15:00
RandomizedDelaySec=15m
Persistent=true
AccuracySec=1m
Unit=vps-backup.service

[Install]
WantedBy=timers.target
EOF_TIMER

cat > "$BACKUP_SYSTEMD_ROOT/vps-backup-maintenance.service" <<EOF_SERVICE
[Unit]
Description=Restic retention, prune and repository integrity maintenance
Documentation=https://restic.readthedocs.io/
Wants=network-online.target
After=network-online.target docker.service
ConditionPathExists=${BACKUP_SECRETS_ROOT}/password

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=VPS_GUIDE_CONFIG=${VPS_GUIDE_CONFIG}
ExecStart=${OPS_ROOT}/scripts/backup-maintenance.sh
TimeoutStartSec=6h
Nice=15
IOSchedulingClass=best-effort
IOSchedulingPriority=7
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=${BACKUPS_ROOT} ${BACKUP_METRICS_ROOT} /run/lock
ReadOnlyPaths=${OPS_ROOT} ${BACKUP_SECRETS_ROOT} /home/${ADMIN_USER}
StandardOutput=journal
StandardError=journal
EOF_SERVICE

cat > "$BACKUP_SYSTEMD_ROOT/vps-backup-maintenance.timer" <<'EOF_TIMER'
[Unit]
Description=Weekly restic retention and integrity maintenance

[Timer]
OnCalendar=Sun *-*-* 05:30:00
RandomizedDelaySec=30m
Persistent=true
AccuracySec=1m
Unit=vps-backup-maintenance.service

[Install]
WantedBy=timers.target
EOF_TIMER

chmod 0644 "$BACKUP_SYSTEMD_ROOT"/*

sudo install -o root -g root -m 0644 \
  "$BACKUP_SYSTEMD_ROOT/vps-backup.service" \
  /etc/systemd/system/vps-backup.service
sudo install -o root -g root -m 0644 \
  "$BACKUP_SYSTEMD_ROOT/vps-backup.timer" \
  /etc/systemd/system/vps-backup.timer
sudo install -o root -g root -m 0644 \
  "$BACKUP_SYSTEMD_ROOT/vps-backup-maintenance.service" \
  /etc/systemd/system/vps-backup-maintenance.service
sudo install -o root -g root -m 0644 \
  "$BACKUP_SYSTEMD_ROOT/vps-backup-maintenance.timer" \
  /etc/systemd/system/vps-backup-maintenance.timer

sudo systemctl daemon-reload

# README managed block.
OPS_README="$OPS_ROOT/README.md"
if [[ -f "$OPS_README" ]]; then
  python3 - "$OPS_README" <<'PY_README'
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = "<!-- BEGIN VPS GUIDE CHAPTER 10 -->"
end = "<!-- END VPS GUIDE CHAPTER 10 -->"
text = path.read_text(encoding="utf-8")

if begin in text:
    before, rest = text.split(begin, 1)
    if end not in rest:
        raise SystemExit("ERROR: unterminated Chapter 10 README block")
    _, after = rest.split(end, 1)
    text = before.rstrip() + "\n" + after.lstrip("\n")

block = '''<!-- BEGIN VPS GUIDE CHAPTER 10 -->
## Backups

- encrypted off-site repository: restic over S3-compatible object storage;
- credentials source-of-truth: `secrets/backup.enc.yaml` via SOPS + age;
- runtime credentials: root-only under `/opt/data/backups/secrets`;
- daily systemd timer: `vps-backup.timer`;
- weekly retention/integrity timer: `vps-backup-maintenance.timer`;
- PostgreSQL: logical `pg_dump -Fc`, never a live PGDATA copy;
- backup age/failure metrics: node_exporter textfile collector -> Prometheus -> Alertmanager.
<!-- END VPS GUIDE CHAPTER 10 -->'''

path.write_text(text.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
PY_README
fi

printf 'Chapter 10 backup layer configured. Timers are installed but not enabled.\n'
EOF_CH10_CONFIGURE

chmod 0750 "$OPS_ROOT/scripts/chapter-10-configure.sh"
"$OPS_ROOT/scripts/chapter-10-configure.sh"
````

Ожидается:

```text
Chapter 10 backup layer configured. Timers are installed but not enabled.
```

Перезагрузить variables в текущей shell:

```bash
source "$HOME/config.env"
```

---

## 5. Создать encrypted backup credentials и инициализировать repository

Запустить interactive helper:

```bash
"$OPS_ROOT/scripts/backup-secrets-setup.sh"
```

Он запросит пять значений из шага 2.

Secret access key вводится скрыто.

Helper:

1. генерирует отдельный случайный restic repository password;
2. формирует repository path вида:

```text
s3:https://<endpoint>/<bucket>/restic/<server-hostname>
```

3. шифрует все значения сразу через SOPS;
4. записывает только encrypted:

```text
/opt/ops/secrets/backup.enc.yaml
```

5. materialize runtime values в root-only files;
6. не выводит secret values.

Проверить runtime permissions без чтения содержимого:

```bash
sudo stat -c '%A %U:%G %n' \
  "$BACKUP_SECRETS_ROOT" \
  "$BACKUP_SECRETS_ROOT"/*
```

Ожидается:

```text
drwx------ root:root /opt/data/backups/secrets
-rw------- root:root /opt/data/backups/secrets/...
```

Теперь проверить remote repository.

Команда ниже:

- если repository уже существует и открывается текущим password — оставляет его как есть;
- если restic возвращает code `10` `repository does not exist` — создаёт repository;
- при любой другой ошибке останавливается.

````bash
set +e
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" cat config >/dev/null 2>&1
RESTIC_OPEN_STATUS=$?
set -e

case "$RESTIC_OPEN_STATUS" in
  0)
    printf 'Existing restic repository opened successfully.\n'
    ;;
  10)
    sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
      "$OPS_ROOT/scripts/restic-wrapper.sh" init
    ;;
  *)
    printf 'ERROR: restic repository validation failed with exit code %s\n' \
      "$RESTIC_OPEN_STATUS" >&2
    unset RESTIC_OPEN_STATUS
    false
    ;;
esac

unset RESTIC_OPEN_STATUS
````

После `init` restic должен сообщить, что repository создан.

> Не создавайте второй repository вручную с другим password. Canonical repository password уже находится в `backup.enc.yaml`.

---

## 6. Выполнить static validation

Проверить Bash/Python scripts:

```bash
bash -n \
  "$OPS_ROOT/scripts/chapter-10-install-restic.sh" \
  "$OPS_ROOT/scripts/chapter-10-configure.sh" \
  "$OPS_ROOT/scripts/backup-secrets-setup.sh" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" \
  "$OPS_ROOT/scripts/backup-run.sh" \
  "$OPS_ROOT/scripts/backup-maintenance.sh" \
  "$OPS_ROOT/scripts/backup-status.sh"

python3 -m py_compile \
  "$OPS_ROOT/scripts/backup-materialize.py" \
  "$OPS_ROOT/scripts/grafana-sqlite-backup.py"
rm -rf "$OPS_ROOT/scripts/__pycache__"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x \
    "$OPS_ROOT/scripts/chapter-10-install-restic.sh" \
    "$OPS_ROOT/scripts/chapter-10-configure.sh" \
    "$OPS_ROOT/scripts/backup-secrets-setup.sh" \
    "$OPS_ROOT/scripts/restic-wrapper.sh" \
    "$OPS_ROOT/scripts/backup-run.sh" \
    "$OPS_ROOT/scripts/backup-maintenance.sh" \
    "$OPS_ROOT/scripts/backup-status.sh"
fi
```

Проверить systemd units:

```bash
sudo systemd-analyze verify \
  /etc/systemd/system/vps-backup.service \
  /etc/systemd/system/vps-backup.timer \
  /etc/systemd/system/vps-backup-maintenance.service \
  /etc/systemd/system/vps-backup-maintenance.timer
```

Проверить calendar expressions:

```bash
systemd-analyze calendar '*-*-* 03:15:00' >/dev/null
systemd-analyze calendar 'Sun *-*-* 05:30:00' >/dev/null
printf 'Backup systemd calendar expressions are valid.\n'
```

Проверить patched observability Compose:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" config --quiet
```

Проверить Prometheus rules текущим Prometheus binary:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  exec -T prometheus \
  promtool check rules /etc/prometheus/rules/vps.yml
```

Проверить encrypted secret policy:

```bash
"$OPS_ROOT/scripts/sops-check.sh"
```

---

## 7. Зафиксировать recovery checkpoint в Git

До первого snapshot encrypted source `backup.enc.yaml` должен существовать **вне VPS**.

Это обязательная часть recovery chain:

```text
off-site repository
        +
GitHub: secrets/backup.enc.yaml
        +
offline age identity из главы 09
        =
возможность получить restic password после полной потери VPS
```

Не откладывайте этот commit до конца главы: первый backup должен уже ссылаться в recovery inventory на Chapter 10 Git commit, а не на dirty working tree.

Перейти в repository:

```bash
cd "$OPS_ROOT"
```

Проверить changes:

```bash
git status --short
```

В diff должны находиться Chapter 10 files, изменения observability и encrypted backup source.

Проверить, что encrypted file действительно SOPS ciphertext:

```bash
grep -Fq 'ENC[AES256_GCM,' "$SOPS_BACKUP_FILE"
grep -Fq 'sops:' "$SOPS_BACKUP_FILE"
printf 'backup.enc.yaml is SOPS-encrypted.\n'
```

Добавить изменения:

```bash
git add -A
```

Запустить staged secret policy:

```bash
python3 scripts/secret-policy.py --staged
```

Проверить staged filenames:

```bash
git diff --cached --name-only
```

Создать commit:

```bash
git commit -m "Add encrypted off-site restic backups"
```

Отправить в GitHub:

```bash
git push origin main
```

Проверить clean state:

```bash
git status --short
```

Вывод должен быть пустым.

---

## 8. Выполнить первый production backup вручную

До включения timer создаём первый реальный snapshot.

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/backup-run.sh"
```

Успешный запуск должен закончиться строкой:

```text
Backup completed successfully.
```

В этом запуске автоматически:

- создаётся `pg_dump -Fc` GlitchTip;
- создаётся консистентный SQLite backup `grafana.db`;
- проверяется `pg_restore --list`;
- собирается recovery inventory;
- выполняется encrypted upload;
- создаётся restic snapshot с tags `production,vps-guide`;
- timestamp success записывается в root-only state;
- Prometheus textfile metric обновляется атомарно;
- local staging удаляется после завершения.

Сразу проверить latest snapshots:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" snapshots \
    --host "$SERVER_HOSTNAME" \
    --tag production \
    --latest 3
```

Должен существовать минимум один snapshot текущего сервера.

---

## 9. Проверить repository после первого snapshot

Выполнить metadata check:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" check
```

Ожидается завершение без ошибок.

Проверить, что оба консистентных database artifacts действительно присутствуют внутри snapshot, **не восстанавливая их пока**:

````bash
SNAPSHOT_CONTENT="$(
  sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
    "$OPS_ROOT/scripts/restic-wrapper.sh" ls latest
)"

for path in \
  '/opt/backups/staging/current/databases/glitchtip.dump' \
  '/opt/backups/staging/current/databases/grafana.db'; do
  grep -Fq "$path" <<< "$SNAPSHOT_CONTENT" || {
    printf 'ERROR: expected backup artifact not found: %s\n' "$path" >&2
    unset SNAPSHOT_CONTENT
    false
  }
done

unset SNAPSHOT_CONTENT
printf 'Database backup artifacts are present in the latest snapshot.\n'
````

Это только backup-content smoke test. Полный `restore` выполняется в следующей главе.

---

## 10. Активировать backup metrics в node_exporter и Prometheus

Первый successful backup уже создал textfile metric, поэтому можно безопасно включить collector и alert rules без ложного `BackupMetricMissing`.

Пересоздать только `node-exporter` и `prometheus`:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  up -d --no-deps --force-recreate node-exporter prometheus
```

Проверить Prometheus targets единым существующим health-check:

```bash
"$OPS_ROOT/scripts/observability-check.sh"
```

Проверить backup metric через Prometheus API:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=vps_backup_last_success_unixtime' \
  http://127.0.0.1:9090/api/v1/query |
jq -e '.data.result | length == 1' >/dev/null

printf 'Prometheus sees the backup success metric.\n'
```

---

## 11. Выполнить первый retention/integrity maintenance

Сейчас snapshots ещё мало, поэтому `forget --prune` ничего важного не удалит. Этот запуск проверит весь automated maintenance path.

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/backup-maintenance.sh"
```

Он применяет policy:

```text
14 daily
8 weekly
12 monthly
3 yearly
```

Grouping выполняется по:

```text
host,tags
```

а не по полному path list. Это важно: появление нового optional system directory не должно создавать отдельную retention-группу навсегда.

После prune запускается repository integrity check для одной восьмой data packs.

Ожидаемая последняя строка:

```text
Backup maintenance completed successfully.
```

Проверить maintenance metric:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  --get \
  --data-urlencode 'query=vps_backup_maintenance_last_run_success' \
  http://127.0.0.1:9090/api/v1/query |
jq -e '.data.result[0].value[1] == "1"' >/dev/null

printf 'Prometheus sees successful backup maintenance.\n'
```

---

## 12. Включить systemd timers

Только после successful manual backup и successful maintenance включить автоматизацию:

```bash
sudo systemctl enable --now \
  vps-backup.timer \
  vps-backup-maintenance.timer
```

Проверить только эти timers:

```bash
systemctl list-timers \
  vps-backup.timer \
  vps-backup-maintenance.timer \
  --all \
  --no-pager
```

Должны отображаться два будущих запуска.

Schedule:

```text
backup       daily 03:15 + random 0..15 min
maintenance Sunday 05:30 + random 0..30 min
```

`Persistent=true` означает: если VPS был выключен в scheduled time, systemd выполнит пропущенный job после следующего boot.

`OnCalendar` использует локальную timezone VPS, настроенную в системной главе, а не timezone компьютера администратора.

---

## 13. Проверить Telegram alert contract без поломки repository

Не будем намеренно ломать S3 credentials или удалять repository.

Проверим, что новые Prometheus rules загружены:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  http://127.0.0.1:9090/api/v1/rules |
jq -e '
  [
    .data.groups[].rules[]
    | select(
        .name == "BackupLastRunFailed"
        or .name == "BackupTooOld"
        or .name == "BackupMetricMissing"
        or .name == "BackupMaintenanceFailed"
      )
  ]
  | length == 4
' >/dev/null

printf 'All backup alert rules are loaded.\n'
```

Alert path уже используется существующим contract:

```text
Prometheus -> Alertmanager -> Telegram
```

При следующем реальном backup failure `backup-run.sh` запишет:

```text
vps_backup_last_run_success 0
```

и Alertmanager отправит Telegram notification через уже настроенные SOPS-managed Telegram credentials.

---

## 14. Проверить backup scope

Основной snapshot включает:

```text
/opt/ops
/opt/apps
/opt/data
/opt/backups/staging/current
/home/<admin>/.ssh
/home/<admin>/.config/sops/age
/home/<admin>/config.env
/etc
```

Из `/opt/data` исключаются:

```text
/opt/data/error-tracking/postgres
/opt/data/error-tracking/secrets
/opt/data/docker-auth
/opt/data/backups
/opt/data/observability
```

Почему:

| Path | Причина |
| --- | --- |
| live PostgreSQL PGDATA | заменён consistent logical dump |
| runtime secret files | canonical encrypted source уже в SOPS/Git |
| docker-auth | GHCR credential уже в SOPS |
| backup runtime credentials | нельзя рекурсивно включать backup runtime в backup source |
| observability runtime directory | Prometheus/Loki/Alloy raw state не сохраняется; Grafana `grafana.db` заменяется консистентной SQLite-копией в staging |

Caddy state **не исключён**:

```text
/opt/data/caddy
```

поэтому ACME account, certificates и Caddy state входят в encrypted off-site snapshot.

---

## 15. Проверить права и secret leakage

Encrypted source может быть world-readable как ciphertext `0644`, но private age identity и plaintext backup runtime должны оставаться закрытыми.

Проверить:

```bash
stat -c '%A %U:%G %n' \
  "$SOPS_BACKUP_FILE" \
  "$SOPS_AGE_KEY_FILE"

sudo stat -c '%A %U:%G %n' \
  "$BACKUP_SECRETS_ROOT" \
  "$BACKUP_SECRETS_ROOT"/* \
  "$BACKUP_STAGING_ROOT" \
  "$RESTIC_CACHE_ROOT" \
  "$BACKUP_STATE_ROOT"
```

Ожидаемый contract:

```text
backup.enc.yaml              0644 encrypted only
age keys.txt                 0600 admin-owned
backup secrets directory     0700 root:root
backup runtime secret files  0600 root:root
staging/cache/state           0700 root:root
```

Запустить repository secret policy:

```bash
cd "$OPS_ROOT"
python3 scripts/secret-policy.py
```

---

## 16. Проверить обычный operational workflow

После этой главы основные команды следующие.

### Статус backups

```bash
"$OPS_ROOT/scripts/backup-status.sh"
```

### Запустить backup вручную

```bash
sudo systemctl start vps-backup.service
```

После завершения:

```bash
systemctl status vps-backup.service --no-pager
```

### Посмотреть только backup journal

```bash
journalctl -u vps-backup.service -n 200 --no-pager
```

### Запустить maintenance вручную

```bash
sudo systemctl start vps-backup-maintenance.service
```

### Посмотреть snapshots

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" snapshots
```

### Проверить repository metadata

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" check
```

Не запускайте `unlock`, `forget`, `prune`, `repair` или ручное удаление S3 objects «на всякий случай».

---

## 17. Финальный runtime gate главы 10

Выполнить единый final check:

````bash
FINAL_CHECK="$(mktemp)"
chmod 0700 "$FINAL_CHECK"

cat > "$FINAL_CHECK" <<'EOF_CH10_FINAL'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

for name in \
  OPS_ROOT SERVER_HOSTNAME BACKUP_SECRETS_ROOT BACKUP_METRICS_ROOT \
  SOPS_BACKUP_FILE SOPS_AGE_KEY_FILE; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ -z "$(git -C "$OPS_ROOT" status --porcelain)" ]] || {
  printf 'ERROR: Git working tree is dirty\n' >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

git -C "$OPS_ROOT" fetch --quiet origin main
LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"
[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ\n' >&2
  printf 'local:  %s\nremote: %s\n' "$LOCAL_SHA" "$REMOTE_SHA" >&2
  exit 1
}

for unit in \
  vps-backup.timer \
  vps-backup-maintenance.timer; do
  systemctl is-enabled --quiet "$unit" || {
    printf 'ERROR: timer is not enabled: %s\n' "$unit" >&2
    exit 1
  }
  systemctl is-active --quiet "$unit" || {
    printf 'ERROR: timer is not active: %s\n' "$unit" >&2
    exit 1
  }
done

for file in \
  repository password aws_access_key_id aws_secret_access_key aws_default_region; do
  path="$BACKUP_SECRETS_ROOT/$file"
  [[ -s "$path" ]] || {
    printf 'ERROR: runtime backup credential missing: %s\n' "$path" >&2
    exit 1
  }
  [[ "$(sudo stat -c '%U:%G:%a' "$path")" == "root:root:600" ]] || {
    printf 'ERROR: invalid backup credential permissions: %s\n' "$path" >&2
    exit 1
  }
done

grep -Fq 'ENC[AES256_GCM,' "$SOPS_BACKUP_FILE"
[[ "$(stat -c '%a' "$SOPS_AGE_KEY_FILE")" == "600" ]]

SNAPSHOT_COUNT="$(
  sudo env VPS_GUIDE_CONFIG="$VPS_GUIDE_CONFIG" \
    "$OPS_ROOT/scripts/restic-wrapper.sh" snapshots \
      --host "$SERVER_HOSTNAME" \
      --tag production \
      --json |
  jq 'length'
)"

(( SNAPSHOT_COUNT >= 1 )) || {
  printf 'ERROR: no production restic snapshots found\n' >&2
  exit 1
}

PROM_RESULT="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --get \
    --data-urlencode 'query=vps_backup_last_run_success' \
    http://127.0.0.1:9090/api/v1/query
)"

[[ "$(jq -r '.data.result[0].value[1] // empty' <<< "$PROM_RESULT")" == "1" ]] || {
  printf 'ERROR: Prometheus does not report successful latest backup\n' >&2
  exit 1
}

RULE_COUNT="$(
  curl --fail --silent --show-error http://127.0.0.1:9090/api/v1/rules |
  jq '[.data.groups[].rules[] | select(.name | startswith("Backup"))] | length'
)"

(( RULE_COUNT >= 4 )) || {
  printf 'ERROR: backup Prometheus rules are not loaded\n' >&2
  exit 1
}

printf 'Chapter 10 final check passed. snapshots=%s backup_rules=%s\n' \
  "$SNAPSHOT_COUNT" "$RULE_COUNT"
EOF_CH10_FINAL

"$FINAL_CHECK"
FINAL_STATUS=$?
rm -f -- "$FINAL_CHECK"
unset FINAL_CHECK

if [[ "$FINAL_STATUS" -ne 0 ]]; then
  unset FINAL_STATUS
  false
else
  unset FINAL_STATUS
fi
````

Ожидается:

```text
Chapter 10 final check passed. snapshots=<N> backup_rules=<N>
```

---

## 18. Что должно получиться после главы

```text
GitHub
└── vps-ops
    ├── config/backup/
    │   ├── excludes.txt
    │   └── systemd/
    ├── scripts/
    │   ├── backup-materialize.py
    │   ├── grafana-sqlite-backup.py
    │   ├── backup-secrets-setup.sh
    │   ├── restic-wrapper.sh
    │   ├── backup-run.sh
    │   ├── backup-maintenance.sh
    │   └── backup-status.sh
    └── secrets/
        └── backup.enc.yaml -------- encrypted only

VPS
├── /opt/data/backups/secrets ------- plaintext runtime, root-only
├── /opt/backups/staging ------------ temporary, root-only
├── /opt/backups/restic-cache ------- local cache, root-only
├── /opt/backups/state -------------- timestamps, root-only
└── /opt/data/observability/textfile
    ├── vps_backup.prom
    └── vps_backup_maintenance.prom

systemd
├── vps-backup.timer ---------------- daily
└── vps-backup-maintenance.timer ----- weekly

External provider
└── private S3 bucket
    └── restic/server ---------------- encrypted repository
```

Recovery chain после полной потери VPS:

```text
GitHub repository
       +
offline age recovery key from Chapter 09
       |
       v
decrypt secrets/backup.enc.yaml
       |
       v
S3 credentials + restic password
       |
       v
off-site restic repository
       |
       v
restore data/configuration
```

Поэтому offline age recovery key из главы 09 остаётся обязательным recovery asset.

---

## 19. Критерии завершения главы

Глава завершена только если выполняются все пункты:

- `restic version` показывает `0.19.1`;
- `secrets/backup.enc.yaml` существует и содержит SOPS ciphertext;
- plaintext backup credentials отсутствуют в Git;
- runtime backup secrets имеют `root:root 0600`;
- remote repository находится вне VPS;
- создан минимум один production snapshot;
- snapshot содержит `glitchtip.dump` и консистентный `grafana.db`;
- live PostgreSQL PGDATA исключён;
- `/opt/data/caddy` входит в backup scope;
- `restic check` проходит;
- manual maintenance проходит;
- `vps_backup_last_run_success == 1` виден Prometheus;
- backup alert rules загружены;
- `vps-backup.timer` enabled/active;
- `vps-backup-maintenance.timer` enabled/active;
- Git working tree clean;
- Chapter 10 commit с encrypted `backup.enc.yaml` отправлен в `origin/main` **до первого snapshot**;
- local `main` совпадает с `origin/main`.

После этого можно утверждать:

```text
off-site encrypted backups are running automatically
```

Но пока нельзя утверждать:

```text
disaster recovery is verified
```

Это будет gate следующей главы.

---

## 20. Диагностика

Все команды ниже нужны **только если основной сценарий завершился ошибкой**.

<details>
<summary><code>restic repository validation failed with exit code 12</code></summary>

Code `12` означает неправильный repository password.

Не выполняйте `restic init` поверх существующего repository.

Сначала проверить, что runtime credentials действительно materialized из текущего SOPS source:

```bash
"$OPS_ROOT/scripts/backup-secrets-setup.sh"
```

Затем повторить:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" cat config >/dev/null
```

Если repository был создан раньше с другим password, нужен тот исходный password. Создание нового password не расшифрует существующий repository.

</details>

<details>
<summary><code>restic repository validation failed with exit code 10</code></summary>

Code `10` означает, что repository по указанному path ещё не существует.

Это штатно только при первом запуске.

Создать его:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" init
```

Если `init` также не работает — проверять endpoint/bucket/credentials, а не повторять `init` много раз.

</details>

<details>
<summary>S3 возвращает <code>AccessDenied</code>, <code>403</code> или signature error</summary>

Проверить:

- bucket private;
- access key относится именно к этому bucket;
- key разрешает list/read/write/delete objects, необходимые normal restic + prune workflow;
- endpoint введён **без** `https://`;
- region соответствует provider;
- server clock синхронизирован.

Проверить clock:

```bash
timedatectl status
```

Если endpoint/credentials были введены неверно и `backup.enc.yaml` ещё не закоммичен, удалить только encrypted backup source и runtime projection, затем повторить setup:

```bash
rm -f "$SOPS_BACKUP_FILE"
sudo rm -f "$BACKUP_SECRETS_ROOT"/*
"$OPS_ROOT/scripts/backup-secrets-setup.sh"
```

Не удаляйте SOPS age key.

</details>

<details>
<summary><code>timed out waiting for /run/lock/vps-backup.lock</code></summary>

Сначала проверить реально выполняющиеся jobs:

```bash
systemctl status \
  vps-backup.service \
  vps-backup-maintenance.service \
  --no-pager

pgrep -a restic || true
```

Backup/maintenance автоматически ждёт local lock до 30 минут. Если timeout всё же произошёл, сначала проверить, какой job удерживал lock.

Если restic действительно работает — ничего не делать, дождаться завершения текущего job.

Если processes отсутствуют, локальный `flock` уже освобождён автоматически. Повторить команду.

Не удаляйте remote restic locks только из-за local lock timeout.

</details>

<details>
<summary>Restic сообщает, что repository locked</summary>

Сначала убедиться, что на сервере нет active restic process:

```bash
pgrep -a restic || true
systemctl status \
  vps-backup.service \
  vps-backup-maintenance.service \
  --no-pager
```

`restic-wrapper.sh` уже использует `--retry-lock 5m`.

Если ни одного restic process нет, а lock остаётся после аварийно оборванного старого job, посмотреть locks:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" list locks
```

Только после подтверждения stale lock:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" unlock
```

Не автоматизируем `unlock`: автоматическое удаление lock может повредить concurrent repository operation.

</details>

<details>
<summary><code>pg_dump</code> или <code>pg_restore --list</code> завершился ошибкой</summary>

Проверить PostgreSQL container:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" ps postgres
"$OPS_ROOT/scripts/glitchtip-compose.sh" logs --tail=120 postgres
```

Проверить logical dump отдельно:

```bash
"$OPS_ROOT/scripts/glitchtip-compose.sh" \
  exec -T postgres \
  sh -eu -c '
    dump=/tmp/glitchtip-backup-test.dump
    rm -f "$dump"
    pg_dump -U glitchtip -d glitchtip -Fc -f "$dump"
    pg_restore --list "$dump" >/dev/null
    rm -f "$dump"
    printf "PostgreSQL logical dump is valid.\n"
  '
```

Не заменяйте logical dump копированием `/var/lib/postgresql/data` во время работы PostgreSQL.

</details>

<details>
<summary>Grafana SQLite online backup завершился ошибкой</summary>

Проверить source database без остановки Grafana:

```bash
sudo test -s "$OBSERVABILITY_DATA_ROOT/grafana/grafana.db"

sudo python3 - "$OBSERVABILITY_DATA_ROOT/grafana/grafana.db" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=30)
try:
    print(connection.execute("PRAGMA integrity_check").fetchone()[0])
finally:
    connection.close()
PY
```

Ожидается:

```text
ok
```

Не копируйте live `grafana.db` через `cp` как замену online backup.

</details>

<details>
<summary><code>backup-run.sh</code> получает restic exit code 3</summary>

Для `backup` code `3` означает: snapshot создан, но часть source data не удалось прочитать. Такой run считается failed и не должен обновлять success timestamp.

Посмотреть journal:

```bash
journalctl -u vps-backup.service -n 300 --no-pager
```

Найти конкретный unreadable path и исправить permission/source contract.

Не маскируйте code `3` через `|| true`.

</details>

<details>
<summary>Prometheus не видит <code>vps_backup_last_success_unixtime</code></summary>

Проверить metric file:

```bash
sudo cat "$BACKUP_METRICS_ROOT/vps_backup.prom"
```

В этом файле нет secrets.

Проверить node_exporter command/mount:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" config |
grep -A30 'node-exporter:'
```

Проверить raw node_exporter endpoint через observability gateway:

```bash
curl \
  --fail \
  --silent \
  "http://${OBSERVABILITY_GATEWAY}:9100/metrics" |
grep '^vps_backup_'
```

Если metric file существует, но metric отсутствует — пересоздать node-exporter:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  up -d --no-deps --force-recreate node-exporter
```

</details>

<details>
<summary>Prometheus rules не загружаются после Chapter 10</summary>

Проверить rules:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  exec -T prometheus \
  promtool check rules /etc/prometheus/rules/vps.yml
```

После исправления YAML пересоздать только Prometheus:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  up -d --no-deps --force-recreate prometheus
```

</details>

<details>
<summary>Timer enabled, но backup не запускался</summary>

Проверить timer:

```bash
systemctl status vps-backup.timer --no-pager
systemctl list-timers vps-backup.timer --all --no-pager
```

Проверить service journal:

```bash
journalctl -u vps-backup.service --since '2 days ago' --no-pager
```

Если timer был disabled:

```bash
sudo systemctl enable --now vps-backup.timer
```

</details>

<details>
<summary><code>ProtectSystem=strict</code> блокирует запись backup service</summary>

Service должен писать только в:

```text
/opt/backups
/opt/data/observability/textfile
```

Проверить ошибку:

```bash
journalctl -u vps-backup.service -n 200 --no-pager
```

Не отключайте `ProtectSystem=strict` целиком.

Если добавился новый необходимый writable path, добавьте **только его** в `ReadWritePaths=` versioned unit:

```text
/opt/ops/config/backup/systemd/vps-backup.service
```

после чего переустановите unit и выполните:

```bash
sudo systemctl daemon-reload
```

</details>

<details>
<summary>Repository check сообщает повреждение</summary>

Не запускайте `repair`, `prune` или удаление objects автоматически.

Сначала остановить scheduled maintenance:

```bash
sudo systemctl stop \
  vps-backup.timer \
  vps-backup-maintenance.timer
```

Повторить metadata check и сохранить journal/output:

```bash
sudo env VPS_GUIDE_CONFIG="$HOME/config.env" \
  "$OPS_ROOT/scripts/restic-wrapper.sh" check
```

Если corruption подтверждается, следовать конкретной инструкции, которую выводит текущая версия restic. Перед repair желательно иметь provider-side versioning или вторую copy repository.

После восстановления integrity снова включить timers:

```bash
sudo systemctl start \
  vps-backup.timer \
  vps-backup-maintenance.timer
```

</details>

<details>
<summary>Нужно временно остановить automatic prune</summary>

Backup и maintenance timers разделены специально.

Остановить только destructive maintenance:

```bash
sudo systemctl disable --now vps-backup-maintenance.timer
```

Ежедневные backups продолжат работать через `vps-backup.timer`.

Вернуть maintenance:

```bash
sudo systemctl enable --now vps-backup-maintenance.timer
```

</details>

---

## 21. Что намеренно не делаем в этой главе

### Полный restore test

Наличие snapshots не доказывает восстановимость всего VPS.

Глава 11 выполнит:

- restore в чистую directory;
- проверку permissions;
- `pg_restore` в отдельную database;
- recovery SOPS/age;
- recovery Caddy/application data;
- clean-VPS restore sequence;
- RPO/RTO;
- disaster recovery runbook.

### Backup Docker `/var/lib/docker`

Docker image/cache/container runtime не является source-of-truth и не должен раздувать backups.

Images восстанавливаются из GHCR по immutable digest.

### Live backup PostgreSQL PGDATA

Не используется. Только logical `pg_dump -Fc`.

### Backup Prometheus/Loki/Alloy raw runtime

На этом single-VPS profile metrics/logs считаются reconstructable observability data. Их raw stores имеют высокий churn и ограниченный retention.

Grafana — исключение: её persistent SQLite state сохраняется отдельно через online backup API и попадает в snapshot как staging artifact.

### Automatic `restic unlock`

Не используем. Lock сначала расследуется.

### Automatic repository repair

Не используем. Repair — operator action после подтверждённой corruption.

### Object Lock вместе с normal prune

Не смешиваем. Immutable/append-only backup требует отдельного credential/repository design.

---

## 22. Технические ориентиры главы

Зафиксировано на 2026-08-08:

```text
restic 0.19.1
Ubuntu 24.04
systemd timers
SOPS 3.13.3
age 1.3.1
```

Основные решения:

- repository password передаётся через `RESTIC_PASSWORD_FILE`, а не command line;
- repository path передаётся через `RESTIC_REPOSITORY_FILE`;
- S3 secret key не хранится в systemd unit или Git plaintext;
- restic operations выполняются под `root`, потому что backup должен читать root-owned state и SSH/SOPS recovery material;
- root service ограничен systemd hardening и explicit writable paths;
- локальный `flock` предотвращает overlap на одном VPS и ждёт lock до 30 минут перед failure;
- `--retry-lock 5m` корректно обрабатывает кратковременную repository lock contention;
- backup exit code `3` считается failure, даже если partial snapshot был создан;
- `backup` и `forget` используют одинаковую snapshot grouping policy `host,tags`;
- `forget --prune` вынесен из daily backup в отдельный weekly maintenance job;
- integrity check после prune читает реальную subset encrypted data;
- backup age измеряется timestamp последнего **успешного** run, а не временем timer invocation; default alert window — 30 часов;
- alerting использует уже существующий Prometheus/Alertmanager/Telegram stack.

Официальная документация:

- restic releases: https://github.com/restic/restic/releases
- restic installation: https://restic.readthedocs.io/en/stable/020_installation.html
- repository backends: https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html
- backup: https://restic.readthedocs.io/en/stable/040_backup.html
- repository checks: https://restic.readthedocs.io/en/stable/045_working_with_repos.html
- retention/prune: https://restic.readthedocs.io/en/stable/060_forget.html
- scripting/exit codes: https://restic.readthedocs.io/en/stable/075_scripting.html

---

## 23. Следующая глава

Следующая обязательная глава:

```text
Глава 11. Disaster recovery / restore test
```

В ней backup впервые будет проверен настоящим восстановлением, а не только созданием snapshots и `restic check`.
