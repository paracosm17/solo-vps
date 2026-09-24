# Глава 09. SOPS + age: encrypted secrets в Git и безопасный runtime workflow

Эта глава переводит секреты инфраструктуры из схемы «plaintext-файлы только на VPS» в управляемую production-схему **SOPS + age**.

После выполнения главы:

- source-of-truth секретов хранится в Git только в SOPS-encrypted виде;
- приватный `age` identity хранится вне repository с mode `0600`;
- `.sops.yaml` фиксирует production recipient и правила шифрования;
- существующие Docker Compose stack продолжают читать секреты по прежним путям в `/opt/data/...`;
- observability, GlitchTip и GHCR не требуют изменения Compose contract;
- текущие plaintext runtime secrets мигрируются в SOPS без вывода значений в terminal;
- decrypt выполняется только на VPS, где находится private `age` identity;
- runtime-файлы создаются атомарно и получают прежние безопасные permissions;
- старые secret-generator scripts перестают генерировать новые независимые значения и становятся SOPS materializers;
- Git pre-commit hook блокирует plaintext secret files, private keys и очевидные token leaks;
- GitHub Actions независимо проверяет repository secret policy без production decryption key;
- GHCR token и Telegram credentials получают безопасный update workflow без plaintext temp files;
- private GitHub deploy key намеренно остаётся вне SOPS и вне Git как bootstrap credential;
- создаётся обязательная offline/recovery copy `age` identity;
- rotation `age` key отделена от rotation application credentials;
- stateful credentials нельзя случайно «поменять только в YAML» и рассинхронизировать с PostgreSQL/Grafana/GlitchTip.

> Команды рассчитаны на Ubuntu 24.04 после успешно завершённой главы 08.
>
> В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, **не переходите к следующему номеру шага**, пока причина не устранена.
>
> Никогда не выполняйте `cat`, `less`, `grep`, `sops decrypt` или `set -x` над production secrets без явной необходимости.
>
> Все основные scripts этой главы идемпотентны: повторный запуск не должен создавать новый secret source поверх существующего encrypted source-of-truth.

---

## 0. Что именно строим

```text
                         GitHub private repository
                                  |
                                  | encrypted only
                                  v
/opt/ops
├── .sops.yaml ---------------- production age recipient
├── secrets/
│   ├── observability.enc.yaml
│   ├── error-tracking.enc.yaml
│   ├── registry.enc.yaml
│   ├── recipients/
│   │   └── production.txt ---- public key only
│   └── README.md
│
└── scripts/
    ├── sops-apply.sh
    ├── sops-migrate-existing.sh
    ├── sops-check.sh
    └── secret-policy.py

               decrypt on VPS only
                       |
                       | ~/.config/sops/age/keys.txt
                       | mode 0600, NEVER Git
                       v
/opt/data
├── observability/secrets/ ---- plaintext runtime files, mode 0640
├── error-tracking/secrets/ --- plaintext runtime files, mode 0640
└── docker-auth/config.json --- Docker runtime auth, mode 0600
                       |
                       v
                 Docker Compose
```

SOPS решает конкретную задачу:

```text
Git / GitHub / clone / pull request
           !=
     plaintext secrets
```

SOPS **не** является защитой от root-compromise production VPS.

Если атакующий получил `root` на работающем сервере, он может прочитать:

- private `age` identity;
- materialized runtime secrets;
- Docker mounts;
- process/container state, доступный root.

Поэтому модель этой главы:

```text
Git compromise without age key        -> secrets remain encrypted
Accidental commit plaintext secret    -> local hook / CI blocks it
Lost VPS                               -> Git + offline age key restore secrets
Root compromise of running VPS        -> incident response + credential rotation
```

### Почему plaintext runtime-файлы не переносим в `/run`

На сервере уже используются `restart: unless-stopped` и Compose services, которые должны переживать reboot без отдельного orchestration layer.

Если runtime secret создать только в `/run`, после reboot tmpfs станет пустым, а Docker может попытаться поднять container раньше отдельного decrypt service.

Поэтому сейчас используем более надёжный single-VPS contract:

- canonical source — encrypted SOPS files в Git;
- plaintext runtime projection — persistent `/opt/data/...` на VPS;
- permissions ограничивают чтение;
- Chapter 10 добавит encrypted off-site backup;
- отдельный systemd secret-render dependency layer здесь намеренно не вводим.

---

## 1. Выполнить preflight главы 09

Загрузить текущую server configuration:

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
```

Создать временный preflight script **вне `/opt/ops`**. Он проверяет Git checkpoint, существующие runtime secrets и запущенные observability/error-tracking stack, но **не выводит secret values**.

Preflight принципиально создаётся через `mktemp`, а не внутри Git repository: иначе сам только что созданный файл делал бы working tree dirty и ломал собственную проверку `git status`.

````bash
PREFLIGHT_SCRIPT="$(mktemp)"
chmod 0700 "$PREFLIGHT_SCRIPT"

cat > "$PREFLIGHT_SCRIPT" <<'EOF_CH09_SCRIPT'
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
  OPS_ROOT DATA_ROOT ADMIN_USER OPS_GROUP \
  OBSERVABILITY_STACK ERROR_TRACKING_STACK \
  OBSERVABILITY_SECRETS_ROOT ERROR_TRACKING_SECRETS_ROOT \
  REGISTRY_HOST REGISTRY_DOCKER_CONFIG GITHUB_REMOTE; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s, not as %s\n' "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}

for command in curl docker git jq python3 sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

[[ -d "$OPS_ROOT/.git" ]] || {
  printf 'ERROR: %s is not a Git repository\n' "$OPS_ROOT" >&2
  exit 1
}

[[ "$(git -C "$OPS_ROOT" remote get-url origin)" == "$GITHUB_REMOTE" ]] || {
  printf 'ERROR: origin differs from GITHUB_REMOTE\n' >&2
  exit 1
}

[[ -z "$(git -C "$OPS_ROOT" status --porcelain)" ]] || {
  printf 'ERROR: %s has uncommitted changes\n' "$OPS_ROOT" >&2
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

for file in \
  "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id" \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token" \
  "$REGISTRY_DOCKER_CONFIG/config.json"; do
  [[ -s "$file" ]] || {
    printf 'ERROR: required runtime secret is missing or empty: %s\n' "$file" >&2
    exit 1
  }
done

for project in "$OBSERVABILITY_STACK" "$ERROR_TRACKING_STACK"; do
  CONTAINER_IDS="$(
    docker ps \
      --filter "label=com.docker.compose.project=$project" \
      --format '{{.ID}}'
  )"

  [[ -n "$CONTAINER_IDS" ]] || {
    printf 'ERROR: Docker Compose project is not running: %s\n' "$project" >&2
    exit 1
  }
done

unset CONTAINER_IDS

printf 'Chapter 09 preflight passed: %s\n' "$LOCAL_SHA"
EOF_CH09_SCRIPT

"$PREFLIGHT_SCRIPT"
PREFLIGHT_STATUS=$?

rm -f -- "$PREFLIGHT_SCRIPT"
unset PREFLIGHT_SCRIPT

if [[ "$PREFLIGHT_STATUS" -ne 0 ]]; then
  printf 'ERROR: Chapter 09 preflight failed. Исправьте ошибку выше и повторите шаг 1.\n' >&2
  unset PREFLIGHT_STATUS
  false
else
  unset PREFLIGHT_STATUS
fi
````

Ожидаемая последняя строка:

```text
Chapter 09 preflight passed: <git-commit-sha>
```

---

## 2. Установить фиксированные версии SOPS и age

В этой главе фиксируем:

```text
SOPS  3.13.3
age   1.3.1
```

Не используем `curl | sh` и не устанавливаем бинарник без integrity check.

Installer:

- определяет `amd64`/`arm64`;
- скачивает exact upstream release artifact;
- проверяет pinned SHA-256;
- устанавливает binaries в `/usr/local/bin` как `root:root 0755`;
- проверяет фактическую версию после установки.

````bash
cat > "$OPS_ROOT/scripts/chapter-09-install-tools.sh" <<'EOF_CH09_SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

SOPS_VERSION="3.13.3"
AGE_VERSION="1.3.1"
HTTPS_SCHEME="https"
GITHUB_HOST="github.com"

for command in curl dpkg find install mktemp sha256sum tar; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

case "$(dpkg --print-architecture)" in
  amd64)
    SOPS_ARCH="amd64"
    SOPS_SHA256="e5bec3346a873ae91d871550f3e698c1aad962aff462a080e40f25fde17fef6b"
    AGE_ARCH="amd64"
    AGE_SHA256="bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377"
    ;;
  arm64)
    SOPS_ARCH="arm64"
    SOPS_SHA256="53b0abacd38ef1b12a66d6c100956691b9cefce018d91f81e73ddf7438b94d77"
    AGE_ARCH="arm64"
    AGE_SHA256="c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a"
    ;;
  *)
    printf 'ERROR: unsupported architecture: %s\n' \
      "$(dpkg --print-architecture)" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT INT TERM

curl_download() {
  local url="$1"
  local output="$2"

  curl \
    --proto '=https' \
    --tlsv1.2 \
    --fail \
    --location \
    --silent \
    --show-error \
    --retry 3 \
    --retry-delay 2 \
    --output "$output" \
    "$url"
}

SOPS_FILE="sops-v${SOPS_VERSION}.linux.${SOPS_ARCH}"
SOPS_PATH="$TMP_DIR/$SOPS_FILE"

curl_download \
  "${HTTPS_SCHEME}://${GITHUB_HOST}/getsops/sops/releases/download/v${SOPS_VERSION}/${SOPS_FILE}" \
  "$SOPS_PATH"

printf '%s  %s\n' "$SOPS_SHA256" "$SOPS_PATH" |
  sha256sum --check --status || {
  printf 'ERROR: SOPS checksum verification failed\n' >&2
  exit 1
}

sudo install \
  -o root \
  -g root \
  -m 0755 \
  "$SOPS_PATH" \
  /usr/local/bin/sops

AGE_FILE="age-v${AGE_VERSION}-linux-${AGE_ARCH}.tar.gz"
AGE_PATH="$TMP_DIR/$AGE_FILE"

curl_download \
  "${HTTPS_SCHEME}://${GITHUB_HOST}/FiloSottile/age/releases/download/v${AGE_VERSION}/${AGE_FILE}" \
  "$AGE_PATH"

printf '%s  %s\n' "$AGE_SHA256" "$AGE_PATH" |
  sha256sum --check --status || {
  printf 'ERROR: age checksum verification failed\n' >&2
  exit 1
}

mkdir -p "$TMP_DIR/age"
tar -xzf "$AGE_PATH" -C "$TMP_DIR/age"

for binary in age age-keygen; do
  source_path="$(find "$TMP_DIR/age" -type f -name "$binary" -print -quit)"

  [[ -n "$source_path" ]] || {
    printf 'ERROR: %s was not found in age archive\n' "$binary" >&2
    exit 1
  }

  sudo install \
    -o root \
    -g root \
    -m 0755 \
    "$source_path" \
    "/usr/local/bin/$binary"
done

source_path="$(find "$TMP_DIR/age" -type f -name age-inspect -print -quit || true)"
if [[ -n "$source_path" ]]; then
  sudo install \
    -o root \
    -g root \
    -m 0755 \
    "$source_path" \
    /usr/local/bin/age-inspect
fi

sops --version | grep -Fq "$SOPS_VERSION" || {
  printf 'ERROR: unexpected SOPS version\n' >&2
  sops --version >&2 || true
  exit 1
}

age --version | grep -Fq "$AGE_VERSION" || {
  printf 'ERROR: unexpected age version\n' >&2
  age --version >&2 || true
  exit 1
}

printf 'SOPS %s installed and checksum-verified.\n' "$SOPS_VERSION"
printf 'age %s installed and checksum-verified.\n' "$AGE_VERSION"
EOF_CH09_SCRIPT
chmod 0750 "$OPS_ROOT/scripts/chapter-09-install-tools.sh"
"$OPS_ROOT/scripts/chapter-09-install-tools.sh"
````

Ожидаемые последние строки:

```text
SOPS 3.13.3 installed and checksum-verified.
age 1.3.1 installed and checksum-verified.
```

---

## 3. Создать production age identity и repository policy

Private `age` identity будет находиться здесь:

```text
~/.config/sops/age/keys.txt
```

Repository хранит **только public recipient**.

Configuration script также:

- добавляет Chapter 09 variables в `$HOME/config.env`;
- создаёт `.sops.yaml`;
- меняет старый `.gitignore` contract `secrets/` на allowlist encrypted files;
- обновляет `/opt/ops/README.md`, чтобы `secrets/` больше не описывался как полностью untracked directory;
- не перезаписывает существующий age identity;
- не меняет recipient молча, если обнаруживает несовпадение.

````bash
cat > "$OPS_ROOT/scripts/chapter-09-configure.sh" <<'EOF_CH09_SCRIPT'
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
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s, not as %s\n' "$ADMIN_USER" "$(id -un)" >&2
  exit 1
}

for command in age-keygen git install python3 sops; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

ADMIN_PRIMARY_GROUP="$(id -gn "$ADMIN_USER")"
id -nG "$ADMIN_USER" | tr ' ' '\n' | grep -Fxq "$OPS_GROUP" || {
  printf 'ERROR: %s is not a member of group %s\n' \
    "$ADMIN_USER" "$OPS_GROUP" >&2
  exit 1
}

SOPS_VERSION="3.13.3"
AGE_VERSION="1.3.1"
SOPS_SECRETS_ROOT="$OPS_ROOT/secrets"
SOPS_RECIPIENTS_ROOT="$SOPS_SECRETS_ROOT/recipients"
SOPS_AGE_DIR="$HOME/.config/sops/age"
SOPS_AGE_KEY_FILE="$SOPS_AGE_DIR/keys.txt"
SOPS_AGE_RECIPIENT_FILE="$SOPS_RECIPIENTS_ROOT/production.txt"
SOPS_CONFIG="$OPS_ROOT/.sops.yaml"
SOPS_OBSERVABILITY_FILE="$SOPS_SECRETS_ROOT/observability.enc.yaml"
SOPS_ERROR_TRACKING_FILE="$SOPS_SECRETS_ROOT/error-tracking.enc.yaml"
SOPS_REGISTRY_FILE="$SOPS_SECRETS_ROOT/registry.enc.yaml"

install -d \
  -o "$ADMIN_USER" \
  -g "$ADMIN_PRIMARY_GROUP" \
  -m 0700 \
  "$SOPS_AGE_DIR"

install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 2775 \
  "$SOPS_SECRETS_ROOT" \
  "$SOPS_RECIPIENTS_ROOT"

if [[ -e "$SOPS_AGE_KEY_FILE" && ! -s "$SOPS_AGE_KEY_FILE" ]]; then
  printf 'ERROR: age identity file exists but is empty: %s\n' \
    "$SOPS_AGE_KEY_FILE" >&2
  printf 'Remove the empty file only after confirming it contains no previous key.\n' >&2
  exit 1
fi

if [[ ! -e "$SOPS_AGE_KEY_FILE" ]]; then
  umask 077
  age-keygen -o "$SOPS_AGE_KEY_FILE" >/dev/null
fi

chown "$ADMIN_USER:$ADMIN_PRIMARY_GROUP" "$SOPS_AGE_KEY_FILE"
chmod 0600 "$SOPS_AGE_KEY_FILE"

AGE_RECIPIENT="$(age-keygen -y "$SOPS_AGE_KEY_FILE")"

[[ "$AGE_RECIPIENT" =~ ^age1[0-9a-z]+$ ]] || {
  printf 'ERROR: unexpected age recipient format\n' >&2
  exit 1
}

if [[ -e "$SOPS_AGE_RECIPIENT_FILE" ]]; then
  EXISTING_RECIPIENT="$(tr -d '\r\n' < "$SOPS_AGE_RECIPIENT_FILE")"

  [[ "$EXISTING_RECIPIENT" == "$AGE_RECIPIENT" ]] || {
    printf 'ERROR: %s contains a different recipient.\n' \
      "$SOPS_AGE_RECIPIENT_FILE" >&2
    printf 'Use the key-rotation procedure instead of overwriting it.\n' >&2
    exit 1
  }
else
  printf '%s\n' "$AGE_RECIPIENT" > "$SOPS_AGE_RECIPIENT_FILE"
fi

chown "$ADMIN_USER:$OPS_GROUP" "$SOPS_AGE_RECIPIENT_FILE"
chmod 0644 "$SOPS_AGE_RECIPIENT_FILE"

if [[ ! -e "$SOPS_CONFIG" ]]; then
  cat > "$SOPS_CONFIG" <<EOF_SOPS_CONFIG
---
creation_rules:
  - path_regex: '(^|/)secrets/.*\\.enc\\.yaml$'
    age:
      - ${AGE_RECIPIENT}
    mac_only_encrypted: false

stores:
  yaml:
    indent: 2
EOF_SOPS_CONFIG
else
  grep -Fq "$AGE_RECIPIENT" "$SOPS_CONFIG" || {
    printf 'ERROR: existing %s does not contain the active age recipient.\n' \
      "$SOPS_CONFIG" >&2
    printf 'Use the key-rotation procedure instead of modifying keys implicitly.\n' >&2
    exit 1
  }
fi

chown "$ADMIN_USER:$OPS_GROUP" "$SOPS_CONFIG"
chmod 0644 "$SOPS_CONFIG"

README_FILE="$SOPS_SECRETS_ROOT/README.md"
if [[ ! -e "$README_FILE" ]]; then
  cat > "$README_FILE" <<'EOF_README'
# Encrypted secrets

This directory is versioned in Git, but only SOPS-encrypted `*.enc.yaml` files
may contain secret values.

Rules:

- plaintext secret files are forbidden;
- age private identities are forbidden;
- `recipients/*.txt` contains public age recipients only;
- runtime plaintext is materialized under `/opt/data/...` on the VPS;
- never use `sops decrypt` without redirecting its output to a trusted consumer.
EOF_README
fi

chown "$ADMIN_USER:$OPS_GROUP" "$README_FILE"
chmod 0644 "$README_FILE"

OPS_README="$OPS_ROOT/README.md"
if [[ -f "$OPS_README" ]]; then
  python3 - "$OPS_README" <<'PY_OPS_README'
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = "<!-- BEGIN VPS GUIDE CHAPTER 09 -->"
end = "<!-- END VPS GUIDE CHAPTER 09 -->"
text = path.read_text(encoding="utf-8")
text = text.replace(
    "- `secrets/` — never committed",
    "- `secrets/` — SOPS-encrypted secrets only; plaintext runtime secrets live under `/opt/data`",
)

lines = text.splitlines()
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

block = """<!-- BEGIN VPS GUIDE CHAPTER 09 -->
## Secrets contract

- encrypted source-of-truth: `secrets/*.enc.yaml`;
- public age recipients: `secrets/recipients/*.txt`;
- age private identities: outside Git under `~/.config/sops/age/`;
- runtime plaintext: `/opt/data/.../secrets` and Docker auth config;
- bootstrap SSH private keys are never stored in SOPS or Git.
<!-- END VPS GUIDE CHAPTER 09 -->"""

content = "\n".join(out).rstrip()
if content:
    content += "\n\n"
content += block + "\n"
path.write_text(content, encoding="utf-8")
PY_OPS_README

  chown "$ADMIN_USER:$OPS_GROUP" "$OPS_README"
  chmod 0644 "$OPS_README"
fi

CONFIG_BLOCK="$(mktemp)"
OUTPUT_FILE="$(mktemp)"
cleanup() {
  rm -f -- "$CONFIG_BLOCK" "$OUTPUT_FILE"
}
trap cleanup EXIT INT TERM

cat > "$CONFIG_BLOCK" <<EOF_CONFIG_BLOCK
# =============================================================================
# SOPS / AGE — encrypted secrets source-of-truth
# =============================================================================

# BEGIN VPS GUIDE CHAPTER 09
export SOPS_VERSION=${SOPS_VERSION}
export AGE_VERSION=${AGE_VERSION}
export SOPS_SECRETS_ROOT=${SOPS_SECRETS_ROOT}
export SOPS_RECIPIENTS_ROOT=${SOPS_RECIPIENTS_ROOT}
export SOPS_AGE_KEY_FILE=${SOPS_AGE_KEY_FILE}
export SOPS_AGE_RECIPIENT_FILE=${SOPS_AGE_RECIPIENT_FILE}
export SOPS_CONFIG=${SOPS_CONFIG}
export SOPS_OBSERVABILITY_FILE=${SOPS_OBSERVABILITY_FILE}
export SOPS_ERROR_TRACKING_FILE=${SOPS_ERROR_TRACKING_FILE}
export SOPS_REGISTRY_FILE=${SOPS_REGISTRY_FILE}
# END VPS GUIDE CHAPTER 09
EOF_CONFIG_BLOCK

python3 - \
  "$VPS_GUIDE_CONFIG" \
  "$CONFIG_BLOCK" \
  "$OUTPUT_FILE" <<'PY_CONFIG'
from pathlib import Path
import re
import sys

config_path = Path(sys.argv[1])
block_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

begin = "# BEGIN VPS GUIDE CHAPTER 09"
end = "# END VPS GUIDE CHAPTER 09"

managed = {
    "SOPS_VERSION",
    "AGE_VERSION",
    "SOPS_SECRETS_ROOT",
    "SOPS_RECIPIENTS_ROOT",
    "SOPS_AGE_KEY_FILE",
    "SOPS_AGE_RECIPIENT_FILE",
    "SOPS_CONFIG",
    "SOPS_OBSERVABILITY_FILE",
    "SOPS_ERROR_TRACKING_FILE",
    "SOPS_REGISTRY_FILE",
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

GITIGNORE="$OPS_ROOT/.gitignore"
touch "$GITIGNORE"

python3 - "$GITIGNORE" <<'PY_GITIGNORE'
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = "# BEGIN VPS GUIDE SOPS POLICY"
end = "# END VPS GUIDE SOPS POLICY"

lines = path.read_text(encoding="utf-8").splitlines()
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

    # Chapter 05 ignored the entire secrets directory. Chapter 09 replaces
    # only this exact legacy rule; other project-specific ignore rules stay.
    if stripped == "secrets/":
        continue

    out.append(line)

while out and not out[-1].strip():
    out.pop()

block = """# BEGIN VPS GUIDE SOPS POLICY
# Plaintext files below secrets/ are ignored by default.
secrets/**
!secrets/**/
!secrets/*.enc.yaml
!secrets/**/*.enc.yaml
!secrets/README.md
!secrets/recipients/*.txt

# Never version age private identities.
*.agekey
**/keys.txt
# END VPS GUIDE SOPS POLICY"""

content = "\n".join(out).rstrip()
if content:
    content += "\n\n"
content += block + "\n"
path.write_text(content, encoding="utf-8")
PY_GITIGNORE

chown "$ADMIN_USER:$OPS_GROUP" "$GITIGNORE"
chmod 0644 "$GITIGNORE"

export SOPS_AGE_KEY_FILE SOPS_CONFIG

printf 'SOPS/age repository policy configured.\n'
printf 'Public age recipient: %s\n' "$AGE_RECIPIENT"
printf 'Private age identity: %s (mode 0600, outside Git)\n' "$SOPS_AGE_KEY_FILE"
printf 'Encrypted secrets root: %s\n' "$SOPS_SECRETS_ROOT"
EOF_CH09_SCRIPT
chmod 0750 "$OPS_ROOT/scripts/chapter-09-configure.sh"
"$OPS_ROOT/scripts/chapter-09-configure.sh"
````

Перезагрузить environment:

```bash
source "$HOME/config.env"
```

Private identity **не выводить**.

Public recipient вывести безопасно:

```bash
cat "$SOPS_AGE_RECIPIENT_FILE"
```

Строка вида:

```text
age1...
```

является public key и может храниться в Git.

---

## 4. Обязательно создать recovery copy age identity

Это единственный обязательный шаг главы, который выполняется **на локальном компьютере**, а не на VPS.

Если VPS погибнет вместе с единственной копией `keys.txt`, encrypted secrets в Git станут бесполезны.

На **Windows-компьютере** открыть PowerShell и выполнить. Команда использует стандартный OpenSSH Client (`ssh.exe`/`scp.exe`), тот же SSH alias `server`, который уже использовался в предыдущих главах.

```powershell
$ErrorActionPreference = 'Stop'

$SshAlias = 'server'
$RecoveryDir = Join-Path $HOME '.config\vps-guide\recovery'
$RecoveryFile = Join-Path $RecoveryDir 'server-sops-age-keys.txt'

New-Item -ItemType Directory -Force -Path $RecoveryDir | Out-Null

# Не оставляем старую копию с неизвестными ACL.
if (Test-Path -LiteralPath $RecoveryFile) {
    Remove-Item -LiteralPath $RecoveryFile -Force
}

& scp.exe "${SshAlias}:.config/sops/age/keys.txt" "$RecoveryFile"
if ($LASTEXITCODE -ne 0) {
    throw 'Не удалось скопировать recovery age identity с VPS.'
}

# Удаляем у файла унаследованные ACL и оставляем полный доступ только
# текущему Windows-пользователю. Имена локальных групп не используются,
# поэтому команда не зависит от языка Windows.
$CurrentUser = (& whoami.exe).Trim()
& icacls.exe "$RecoveryFile" /inheritance:r /grant:r "${CurrentUser}:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Не удалось ограничить ACL recovery-файла.'
}

$RemoteHash = (& ssh.exe $SshAlias 'sha256sum "$HOME/.config/sops/age/keys.txt" | cut -d" " -f1').Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RemoteHash)) {
    throw 'Не удалось получить SHA-256 recovery age identity с VPS.'
}

$LocalHash = (Get-FileHash -LiteralPath $RecoveryFile -Algorithm SHA256).Hash

if (-not $RemoteHash.Equals($LocalHash, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Recovery age identity checksum mismatch.'
}

Write-Host "Offline/recovery age identity copy verified: $RecoveryFile"

Remove-Variable RemoteHash, LocalHash, CurrentUser -ErrorAction SilentlyContinue
```

Ожидается:

```text
Offline/recovery age identity copy verified.
```

Если локальный компьютер не использует encrypted disk, перенесите этот файл в надёжное password manager / encrypted vault и удалите plaintext copy с диска.

**Не отправляйте `server-sops-age-keys.txt` в GitHub, cloud notes, Telegram Saved Messages или обычную почту.**

---

## 5. Установить SOPS workflow, Git guard и CI policy

Следующий installer создаёт весь operational layer одним запуском:

```text
scripts/sops-apply.sh
scripts/sops-migrate-existing.sh
scripts/sops-check.sh
scripts/secret-policy.py
scripts/sops-finalize-helpers.sh
scripts/secrets-update-registry.sh
scripts/secrets-update-telegram.sh
.githooks/pre-commit
.github/workflows/secret-policy.yml
```

Он также включает repository-local:

```text
core.hooksPath=.githooks
```

Если в repository уже настроен другой `core.hooksPath`, installer остановится вместо молчаливого overwrite.

````bash
cat > "$OPS_ROOT/scripts/chapter-09-install-workflow.sh" <<'EOF_CH09_SCRIPT'
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
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT/scripts" \
  "$OPS_ROOT/.githooks" \
  "$OPS_ROOT/.github" \
  "$OPS_ROOT/.github/workflows"

cat > "$OPS_ROOT/scripts/sops-apply.sh" <<'EOF_SOPS_APPLY'
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

: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${REGISTRY_HOST:?REGISTRY_HOST is not set}"
: "${REGISTRY_DOCKER_CONFIG:?REGISTRY_DOCKER_CONFIG is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"
: "${SOPS_OBSERVABILITY_FILE:?SOPS_OBSERVABILITY_FILE is not set}"
: "${SOPS_ERROR_TRACKING_FILE:?SOPS_ERROR_TRACKING_FILE is not set}"
: "${SOPS_REGISTRY_FILE:?SOPS_REGISTRY_FILE is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in docker jq python3 sops; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

[[ -r "$SOPS_AGE_KEY_FILE" ]] || {
  printf 'ERROR: age identity is not readable: %s\n' "$SOPS_AGE_KEY_FILE" >&2
  exit 1
}

export SOPS_AGE_KEY_FILE SOPS_CONFIG

materialize_json() {
  local scope="$1"
  local encrypted_file="$2"

  [[ -r "$encrypted_file" ]] || {
    printf 'ERROR: encrypted secret file is not readable: %s\n' \
      "$encrypted_file" >&2
    exit 1
  }

  sops decrypt \
    --input-type yaml \
    --output-type json \
    "$encrypted_file" |
    python3 /dev/fd/3 \
      "$scope" \
      "$ADMIN_USER" \
      "$OPS_GROUP" \
      "$OBSERVABILITY_SECRETS_ROOT" \
      "$ERROR_TRACKING_SECRETS_ROOT" 3<<'PY_MATERIALIZE'
import json
import os
import pwd
import grp
import re
import sys
import tempfile
from pathlib import Path

scope = sys.argv[1]
admin_user = sys.argv[2]
ops_group = sys.argv[3]
observability_root = Path(sys.argv[4])
error_tracking_root = Path(sys.argv[5])

data = json.load(sys.stdin)
uid = pwd.getpwnam(admin_user).pw_uid
gid = grp.getgrnam(ops_group).gr_gid


def require_string(name: str, *, pattern: str | None = None, min_len: int = 1) -> str:
    value = data.get(name)
    if not isinstance(value, str) or len(value) < min_len:
        raise SystemExit(f"ERROR: invalid or missing secret key: {name}")
    if "\x00" in value:
        raise SystemExit(f"ERROR: NUL byte is not allowed in secret: {name}")
    if pattern and not re.fullmatch(pattern, value):
        raise SystemExit(f"ERROR: secret has unexpected format: {name}")
    return value


def atomic_write(path: Path, value: str, mode: int = 0o640) -> None:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(path.parent, uid, gid)
    os.chmod(path.parent, 0o750)

    fd, tmp_name = tempfile.mkstemp(prefix=".sops-runtime-", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            if not value.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(tmp_path, uid, gid)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        os.chown(path, uid, gid)
        os.chmod(path, mode)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


if scope == "observability":
    grafana = require_string("grafana_admin_password", min_len=20)
    telegram_token = require_string(
        "telegram_bot_token",
        pattern=r"[0-9]+:[A-Za-z0-9_-]{20,}",
    )
    telegram_chat_id = require_string(
        "telegram_chat_id",
        pattern=r"-?[0-9]+",
    )

    atomic_write(observability_root / "grafana_admin_password", grafana)
    atomic_write(observability_root / "telegram_bot_token", telegram_token)
    atomic_write(observability_root / "telegram_chat_id", telegram_chat_id)

elif scope == "error-tracking":
    secret_key = require_string("secret_key", pattern=r"[a-f0-9]{128}")
    postgres_password = require_string(
        "postgres_password",
        pattern=r"[a-f0-9]{64}",
    )
    admin_password = require_string("admin_password", min_len=20)
    prometheus_token = require_string("prometheus_token", min_len=20)

    atomic_write(error_tracking_root / "secret_key", secret_key)
    atomic_write(error_tracking_root / "postgres_password", postgres_password)
    atomic_write(error_tracking_root / "admin_password", admin_password)
    atomic_write(error_tracking_root / "prometheus_token", prometheus_token)

    atomic_write(
        error_tracking_root / "postgres.env",
        "\n".join(
            [
                "POSTGRES_DB=glitchtip",
                "POSTGRES_USER=glitchtip",
                f"POSTGRES_PASSWORD={postgres_password}",
                "PGDATA=/var/lib/postgresql/data/pgdata",
            ]
        ),
    )

    atomic_write(
        error_tracking_root / "glitchtip.env",
        "\n".join(
            [
                f"SECRET_KEY={secret_key}",
                "DATABASE_URL="
                f"postgresql://glitchtip:{postgres_password}@postgres:5432/glitchtip",
            ]
        ),
    )

else:
    raise SystemExit(f"ERROR: unsupported materialization scope: {scope}")
PY_MATERIALIZE
}

apply_registry() {
  [[ -r "$SOPS_REGISTRY_FILE" ]] || {
    printf 'ERROR: encrypted secret file is not readable: %s\n' \
      "$SOPS_REGISTRY_FILE" >&2
    exit 1
  }

  install -d \
    -o "$ADMIN_USER" \
    -g "$OPS_GROUP" \
    -m 0700 \
    "$REGISTRY_DOCKER_CONFIG"

  local username
  username="$(
    sops decrypt \
      --input-type yaml \
      --output-type json \
      "$SOPS_REGISTRY_FILE" |
      jq -er '.username | select(type == "string" and length > 0)'
  )"

  sops decrypt \
    --input-type yaml \
    --output-type json \
    "$SOPS_REGISTRY_FILE" |
    jq -jer '.token | select(type == "string" and length > 0)' |
    DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG" \
      docker login \
        "$REGISTRY_HOST" \
        --username "$username" \
        --password-stdin >/dev/null

  # docker login is the last writer in this scope. Enforce the final
  # runtime permissions after it so an existing directory from an older
  # chapter cannot keep broader permissions.
  chown "$ADMIN_USER:$OPS_GROUP" "$REGISTRY_DOCKER_CONFIG"
  chmod 00700 "$REGISTRY_DOCKER_CONFIG"

  if [[ -f "$REGISTRY_DOCKER_CONFIG/config.json" ]]; then
    chown "$ADMIN_USER:$OPS_GROUP" "$REGISTRY_DOCKER_CONFIG/config.json"
    chmod 0600 "$REGISTRY_DOCKER_CONFIG/config.json"
  fi

  unset username
  printf 'Registry runtime credential materialized.\n'
}

apply_scope() {
  case "$1" in
    observability)
      materialize_json observability "$SOPS_OBSERVABILITY_FILE"
      printf 'Observability runtime secrets materialized.\n'
      ;;
    error-tracking)
      materialize_json error-tracking "$SOPS_ERROR_TRACKING_FILE"
      printf 'Error-tracking runtime secrets materialized.\n'
      ;;
    registry)
      apply_registry
      ;;
    all)
      apply_scope observability
      apply_scope error-tracking
      apply_scope registry
      ;;
    *)
      printf 'Usage: %s {all|observability|error-tracking|registry}\n' \
        "$0" >&2
      exit 2
      ;;
  esac
}

apply_scope "${1:-all}"
EOF_SOPS_APPLY

chmod 750 "$OPS_ROOT/scripts/sops-apply.sh"

cat > "$OPS_ROOT/scripts/sops-migrate-existing.sh" <<'EOF_SOPS_MIGRATE'
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

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OBSERVABILITY_SECRETS_ROOT:?OBSERVABILITY_SECRETS_ROOT is not set}"
: "${ERROR_TRACKING_SECRETS_ROOT:?ERROR_TRACKING_SECRETS_ROOT is not set}"
: "${REGISTRY_HOST:?REGISTRY_HOST is not set}"
: "${REGISTRY_DOCKER_CONFIG:?REGISTRY_DOCKER_CONFIG is not set}"
: "${SOPS_SECRETS_ROOT:?SOPS_SECRETS_ROOT is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"
: "${SOPS_OBSERVABILITY_FILE:?SOPS_OBSERVABILITY_FILE is not set}"
: "${SOPS_ERROR_TRACKING_FILE:?SOPS_ERROR_TRACKING_FILE is not set}"
: "${SOPS_REGISTRY_FILE:?SOPS_REGISTRY_FILE is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in base64 jq python3 sops; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

export SOPS_AGE_KEY_FILE SOPS_CONFIG

require_nonempty() {
  [[ -s "$1" ]] || {
    printf 'ERROR: required runtime secret is missing or empty: %s\n' "$1" >&2
    exit 1
  }
}

for file in \
  "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id" \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token" \
  "$REGISTRY_DOCKER_CONFIG/config.json"; do
  require_nonempty "$file"
done

mkdir -p "$SOPS_SECRETS_ROOT"

encrypt_stream_once() {
  local target="$1"
  local generator="$2"

  if [[ -e "$target" ]]; then
    sops decrypt \
      --input-type yaml \
      --output-type json \
      "$target" >/dev/null || {
      printf 'ERROR: existing encrypted file cannot be decrypted: %s\n' \
        "$target" >&2
      exit 1
    }
    printf 'Existing encrypted source preserved: %s\n' "$target"
    return
  fi

  local tmp
  tmp="$(mktemp "$SOPS_SECRETS_ROOT/.sops-encrypted.XXXXXX")"

  if ! "$generator" |
    sops encrypt \
      --filename-override "$target" \
      --input-type json \
      --output-type yaml > "$tmp"; then
    rm -f -- "$tmp"
    printf 'ERROR: failed to encrypt %s\n' "$target" >&2
    exit 1
  fi

  [[ -s "$tmp" ]] || {
    rm -f -- "$tmp"
    printf 'ERROR: SOPS produced an empty file for %s\n' "$target" >&2
    exit 1
  }

  if ! sops decrypt \
    --input-type yaml \
    --output-type json \
    "$tmp" >/dev/null; then
    rm -f -- "$tmp"
    printf 'ERROR: encrypted verification failed for %s\n' "$target" >&2
    exit 1
  fi

  chmod 0644 "$tmp"
  mv -f -- "$tmp" "$target"

  printf 'Migrated into encrypted source: %s\n' "$target"
}

generate_observability_json() {
  python3 - \
    "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password" \
    "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
    "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id" <<'PY_OBS'
import json
from pathlib import Path
import sys

paths = [Path(value) for value in sys.argv[1:]]
keys = [
    "grafana_admin_password",
    "telegram_bot_token",
    "telegram_chat_id",
]
values = {}
for key, path in zip(keys, paths, strict=True):
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if not value:
        raise SystemExit(f"ERROR: empty runtime secret: {path}")
    values[key] = value

json.dump(values, sys.stdout, separators=(",", ":"))
PY_OBS
}

generate_error_tracking_json() {
  python3 - \
    "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
    "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
    "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
    "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token" <<'PY_ERROR_TRACKING'
import json
from pathlib import Path
import sys

paths = [Path(value) for value in sys.argv[1:]]
keys = [
    "secret_key",
    "postgres_password",
    "admin_password",
    "prometheus_token",
]
values = {}
for key, path in zip(keys, paths, strict=True):
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if not value:
        raise SystemExit(f"ERROR: empty runtime secret: {path}")
    values[key] = value

json.dump(values, sys.stdout, separators=(",", ":"))
PY_ERROR_TRACKING
}

generate_registry_json() {
  python3 - \
    "$REGISTRY_DOCKER_CONFIG/config.json" \
    "$REGISTRY_HOST" <<'PY_REGISTRY'
import base64
import json
from pathlib import Path
import sys

config_path = Path(sys.argv[1])
registry_host = sys.argv[2]

config = json.loads(config_path.read_text(encoding="utf-8"))
entry = config.get("auths", {}).get(registry_host, {})
auth = entry.get("auth")

if not isinstance(auth, str) or not auth:
    raise SystemExit(
        "ERROR: registry config has no inline auth entry. "
        "Rerun the chapter-06 registry login once, then retry migration."
    )

try:
    decoded = base64.b64decode(auth, validate=True).decode("utf-8")
except Exception as exc:
    raise SystemExit("ERROR: registry auth entry is not valid base64") from exc

if ":" not in decoded:
    raise SystemExit("ERROR: registry auth entry has unexpected format")

username, token = decoded.split(":", 1)
if not username or not token:
    raise SystemExit("ERROR: registry username/token is empty")

json.dump(
    {"username": username, "token": token},
    sys.stdout,
    separators=(",", ":"),
)
PY_REGISTRY
}

encrypt_stream_once "$SOPS_OBSERVABILITY_FILE" generate_observability_json
encrypt_stream_once "$SOPS_ERROR_TRACKING_FILE" generate_error_tracking_json
encrypt_stream_once "$SOPS_REGISTRY_FILE" generate_registry_json

"$OPS_ROOT/scripts/sops-apply.sh" all

printf 'Existing runtime secrets migrated to SOPS without printing plaintext.\n'
EOF_SOPS_MIGRATE

chmod 750 "$OPS_ROOT/scripts/sops-migrate-existing.sh"

cat > "$OPS_ROOT/scripts/sops-check.sh" <<'EOF_SOPS_CHECK'
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
  OPS_ROOT ADMIN_USER OPS_GROUP \
  OBSERVABILITY_SECRETS_ROOT ERROR_TRACKING_SECRETS_ROOT \
  REGISTRY_HOST REGISTRY_DOCKER_CONFIG \
  SOPS_VERSION AGE_VERSION SOPS_AGE_KEY_FILE SOPS_AGE_RECIPIENT_FILE \
  SOPS_CONFIG SOPS_OBSERVABILITY_FILE SOPS_ERROR_TRACKING_FILE \
  SOPS_REGISTRY_FILE; do
  [[ -n "${!name:-}" ]] || {
    printf 'ERROR: %s is not set\n' "$name" >&2
    exit 1
  }
done

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in age age-keygen git jq python3 sops; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

sops --version | grep -Fq "$SOPS_VERSION" || {
  printf 'ERROR: unexpected SOPS version\n' >&2
  exit 1
}

age --version | grep -Fq "$AGE_VERSION" || {
  printf 'ERROR: unexpected age version\n' >&2
  exit 1
}

[[ "$(stat -c '%a' "$SOPS_AGE_KEY_FILE")" == "600" ]] || {
  printf 'ERROR: age identity must have mode 0600\n' >&2
  exit 1
}

[[ "$(stat -c '%a' "$(dirname "$SOPS_AGE_KEY_FILE")")" == "700" ]] || {
  printf 'ERROR: age identity directory must have mode 0700\n' >&2
  exit 1
}

[[ "$(stat -c '%U' "$SOPS_AGE_KEY_FILE")" == "$ADMIN_USER" ]] || {
  printf 'ERROR: age identity owner must be %s\n' "$ADMIN_USER" >&2
  exit 1
}

[[ "$(stat -c '%U' "$(dirname "$SOPS_AGE_KEY_FILE")")" == "$ADMIN_USER" ]] || {
  printf 'ERROR: age identity directory owner must be %s\n' "$ADMIN_USER" >&2
  exit 1
}

python3 - "$OPS_ROOT" "$SOPS_AGE_KEY_FILE" <<'PY_PATH'
from pathlib import Path
import sys

repo = Path(sys.argv[1]).resolve()
key = Path(sys.argv[2]).resolve()

try:
    key.relative_to(repo)
except ValueError:
    pass
else:
    raise SystemExit("ERROR: age private identity is stored inside the Git repository")
PY_PATH

export SOPS_AGE_KEY_FILE SOPS_CONFIG

RECIPIENT="$(age-keygen -y "$SOPS_AGE_KEY_FILE")"
[[ "$(tr -d '\r\n' < "$SOPS_AGE_RECIPIENT_FILE")" == "$RECIPIENT" ]] || {
  printf 'ERROR: public recipient does not match private age identity\n' >&2
  exit 1
}

grep -Fq "$RECIPIENT" "$SOPS_CONFIG" || {
  printf 'ERROR: active recipient is missing from %s\n' "$SOPS_CONFIG" >&2
  exit 1
}

for encrypted_file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  [[ -s "$encrypted_file" ]] || {
    printf 'ERROR: encrypted source is missing: %s\n' "$encrypted_file" >&2
    exit 1
  }

  grep -Fq 'ENC[AES256_GCM,' "$encrypted_file" || {
    printf 'ERROR: encrypted payload marker is missing: %s\n' "$encrypted_file" >&2
    exit 1
  }

  grep -Fq "$RECIPIENT" "$encrypted_file" || {
    printf 'ERROR: active recipient is missing from encrypted metadata: %s\n' \
      "$encrypted_file" >&2
    exit 1
  }

  sops decrypt \
    --input-type yaml \
    --output-type json \
    "$encrypted_file" >/dev/null

done

compare_scope() {
  local scope="$1"
  local encrypted_file="$2"

  sops decrypt \
    --input-type yaml \
    --output-type json \
    "$encrypted_file" |
    python3 /dev/fd/3 \
      "$scope" \
      "$OBSERVABILITY_SECRETS_ROOT" \
      "$ERROR_TRACKING_SECRETS_ROOT" 3<<'PY_COMPARE'
import base64
import json
import sys
from pathlib import Path

scope = sys.argv[1]
obs_root = Path(sys.argv[2])
error_root = Path(sys.argv[3])
data = json.load(sys.stdin)


def file_value(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"ERROR: runtime secret file is missing: {path}")
    return path.read_text(encoding="utf-8").rstrip("\r\n")


if scope == "observability":
    mapping = {
        "grafana_admin_password": obs_root / "grafana_admin_password",
        "telegram_bot_token": obs_root / "telegram_bot_token",
        "telegram_chat_id": obs_root / "telegram_chat_id",
    }
elif scope == "error-tracking":
    mapping = {
        "secret_key": error_root / "secret_key",
        "postgres_password": error_root / "postgres_password",
        "admin_password": error_root / "admin_password",
        "prometheus_token": error_root / "prometheus_token",
    }
else:
    raise SystemExit(f"ERROR: unsupported comparison scope: {scope}")

for key, path in mapping.items():
    if data.get(key) != file_value(path):
        raise SystemExit(f"ERROR: runtime secret drift detected: {scope}/{key}")
PY_COMPARE
}

compare_scope observability "$SOPS_OBSERVABILITY_FILE"
compare_scope error-tracking "$SOPS_ERROR_TRACKING_FILE"

sops decrypt \
  --input-type yaml \
  --output-type json \
  "$SOPS_REGISTRY_FILE" |
  python3 /dev/fd/3 \
    "$REGISTRY_DOCKER_CONFIG/config.json" \
    "$REGISTRY_HOST" 3<<'PY_REGISTRY_COMPARE'
import base64
import json
import sys
from pathlib import Path

secrets = json.load(sys.stdin)
config_path = Path(sys.argv[1])
registry_host = sys.argv[2]

config = json.loads(config_path.read_text(encoding="utf-8"))
auth = config.get("auths", {}).get(registry_host, {}).get("auth")
if not isinstance(auth, str) or not auth:
    raise SystemExit("ERROR: runtime registry auth is missing")

try:
    decoded = base64.b64decode(auth, validate=True).decode("utf-8")
except Exception as exc:
    raise SystemExit("ERROR: runtime registry auth is invalid") from exc

if ":" not in decoded:
    raise SystemExit("ERROR: runtime registry auth has unexpected format")

username, token = decoded.split(":", 1)
if username != secrets.get("username") or token != secrets.get("token"):
    raise SystemExit("ERROR: runtime registry credential drift detected")
PY_REGISTRY_COMPARE

for path in \
  "$OBSERVABILITY_SECRETS_ROOT" \
  "$ERROR_TRACKING_SECRETS_ROOT"; do
  [[ "$(stat -c '%a' "$path")" == "750" ]] || {
    printf 'ERROR: runtime secrets directory must have mode 0750: %s\n' \
      "$path" >&2
    exit 1
  }
  [[ "$(stat -c '%U:%G' "$path")" == "$ADMIN_USER:$OPS_GROUP" ]] || {
    printf 'ERROR: runtime secrets directory owner/group must be %s:%s: %s\n' \
      "$ADMIN_USER" "$OPS_GROUP" "$path" >&2
    exit 1
  }
done

for path in \
  "$OBSERVABILITY_SECRETS_ROOT/grafana_admin_password" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_bot_token" \
  "$OBSERVABILITY_SECRETS_ROOT/telegram_chat_id" \
  "$ERROR_TRACKING_SECRETS_ROOT/secret_key" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/admin_password" \
  "$ERROR_TRACKING_SECRETS_ROOT/prometheus_token" \
  "$ERROR_TRACKING_SECRETS_ROOT/postgres.env" \
  "$ERROR_TRACKING_SECRETS_ROOT/glitchtip.env"; do
  [[ "$(stat -c '%a' "$path")" == "640" ]] || {
    printf 'ERROR: runtime secret file must have mode 0640: %s\n' "$path" >&2
    exit 1
  }
  [[ "$(stat -c '%U:%G' "$path")" == "$ADMIN_USER:$OPS_GROUP" ]] || {
    printf 'ERROR: runtime secret file owner/group must be %s:%s: %s\n' \
      "$ADMIN_USER" "$OPS_GROUP" "$path" >&2
    exit 1
  }
done

[[ "$(stat -c '%a' "$REGISTRY_DOCKER_CONFIG")" == "700" ]] || {
  printf 'ERROR: registry auth directory must have mode 0700\n' >&2
  exit 1
}

[[ "$(stat -c '%a' "$REGISTRY_DOCKER_CONFIG/config.json")" == "600" ]] || {
  printf 'ERROR: registry config must have mode 0600\n' >&2
  exit 1
}

[[ "$(stat -c '%U' "$REGISTRY_DOCKER_CONFIG")" == "$ADMIN_USER" ]] || {
  printf 'ERROR: registry auth directory owner must be %s\n' "$ADMIN_USER" >&2
  exit 1
}

[[ "$(stat -c '%U' "$REGISTRY_DOCKER_CONFIG/config.json")" == "$ADMIN_USER" ]] || {
  printf 'ERROR: registry config owner must be %s\n' "$ADMIN_USER" >&2
  exit 1
}

for tracked in \
  .sops.yaml \
  secrets/README.md \
  secrets/recipients/production.txt \
  secrets/observability.enc.yaml \
  secrets/error-tracking.enc.yaml \
  secrets/registry.enc.yaml \
  scripts/sops-apply.sh \
  scripts/secret-policy.py \
  .githooks/pre-commit \
  .github/workflows/secret-policy.yml; do
  git -C "$OPS_ROOT" ls-files --error-unmatch "$tracked" >/dev/null 2>&1 || {
    printf 'ERROR: expected file is not tracked by Git: %s\n' "$tracked" >&2
    exit 1
  }
done

python3 "$OPS_ROOT/scripts/secret-policy.py"

[[ -z "$(git -C "$OPS_ROOT" status --porcelain)" ]] || {
  printf 'ERROR: repository has uncommitted changes\n' >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}

git -C "$OPS_ROOT" fetch --quiet origin main
LOCAL_SHA="$(git -C "$OPS_ROOT" rev-parse main)"
REMOTE_SHA="$(git -C "$OPS_ROOT" rev-parse origin/main)"
[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || {
  printf 'ERROR: local main and origin/main differ\n' >&2
  exit 1
}

printf 'SOPS/age check passed. Runtime values match encrypted source-of-truth.\n'
EOF_SOPS_CHECK

chmod 750 "$OPS_ROOT/scripts/sops-check.sh"

cat > "$OPS_ROOT/scripts/secret-policy.py" <<'EOF_SECRET_POLICY'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def tracked_paths(staged: bool) -> list[str]:
    # `git ls-files` reflects the index. With --staged reads below use `git show :path`,
    # so the hook validates the complete repository exactly as it would be committed.
    raw = git_bytes("ls-files", "-z")
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def read_tracked(path: str, staged: bool) -> bytes:
    if staged:
        return git_bytes("show", f":{path}")
    return Path(path).read_bytes()


def is_allowed_secret_path(path: str) -> bool:
    if path == "secrets/README.md":
        return True
    if re.fullmatch(r"secrets/recipients/[A-Za-z0-9._-]+\.txt", path):
        return True
    if re.fullmatch(r"secrets/(?:.*/)?[A-Za-z0-9._-]+\.enc\.yaml", path):
        return True
    return False


def validate_encrypted_yaml(path: str, text: str, errors: list[str]) -> None:
    if "sops:" not in text or "ENC[AES256_GCM," not in text:
        errors.append(f"{path}: file does not look like SOPS-encrypted YAML")
        return

    before_metadata = text.split("\nsops:", 1)[0]
    scalar = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
    secret_fields = 0

    for line in before_metadata.splitlines():
        match = scalar.match(line)
        if not match:
            continue
        value = match.group(2).strip()
        if not value:
            continue
        secret_fields += 1
        if not value.startswith("ENC[AES256_GCM,"):
            errors.append(f"{path}: top-level value is not encrypted: {match.group(1)}")

    if secret_fields == 0:
        errors.append(f"{path}: no encrypted top-level secret values found")


parser = argparse.ArgumentParser()
parser.add_argument("--staged", action="store_true")
args = parser.parse_args()

paths = tracked_paths(args.staged)
errors: list[str] = []

required_paths = {
    ".sops.yaml",
    "secrets/recipients/production.txt",
    "secrets/observability.enc.yaml",
    "secrets/error-tracking.enc.yaml",
    "secrets/registry.enc.yaml",
    "scripts/secret-policy.py",
    ".githooks/pre-commit",
    ".github/workflows/secret-policy.yml",
}

for required_path in sorted(required_paths):
    if required_path not in paths:
        errors.append(f"{required_path}: required secret-management file is not tracked")

private_age_prefix = "AGE-" + "SECRET-KEY-"
private_key_header = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
pem_private_key = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"
)
github_token = re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")
telegram_token = re.compile(r"\b[0-9]{6,12}:[A-Za-z0-9_-]{30,}\b")
known_runtime_basenames = {
    "grafana_admin_password",
    "telegram_bot_token",
    "telegram_chat_id",
    "secret_key",
    "postgres_password",
    "admin_password",
    "prometheus_token",
    "postgres.env",
    "glitchtip.env",
}

for path in paths:
    if path.startswith("secrets/") and not is_allowed_secret_path(path):
        errors.append(f"{path}: forbidden tracked path below secrets/")

    if Path(path).name in known_runtime_basenames:
        errors.append(f"{path}: runtime plaintext secret filename must not be tracked")

    try:
        raw = read_tracked(path, args.staged)
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"{path}: cannot read tracked content: {exc}")
        continue

    if b"\0" in raw or len(raw) > 2 * 1024 * 1024:
        continue

    text = raw.decode("utf-8", errors="replace")

    if path.endswith(".enc.yaml") and path.startswith("secrets/"):
        validate_encrypted_yaml(path, text, errors)

    if path.startswith("secrets/recipients/"):
        values = [line.strip() for line in text.splitlines() if line.strip()]
        if not values or any(not re.fullmatch(r"age1[0-9a-z]+", value) for value in values):
            errors.append(f"{path}: recipient file must contain public age recipients only")

    if private_age_prefix in text:
        errors.append(f"{path}: age private identity detected")

    if private_key_header in text or pem_private_key.search(text):
        errors.append(f"{path}: private key material detected")

    if github_token.search(text):
        errors.append(f"{path}: GitHub token-like value detected")

    if telegram_token.search(text):
        errors.append(f"{path}: Telegram bot token-like value detected")

if ".sops.yaml" in paths:
    text = read_tracked(".sops.yaml", args.staged).decode("utf-8", errors="replace")
    if "creation_rules:" not in text or "age:" not in text:
        errors.append(".sops.yaml: creation rule with age recipient is missing")
    if private_age_prefix in text:
        errors.append(".sops.yaml: private age identity detected")

if errors:
    print("Secret policy failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    raise SystemExit(1)

mode = "staged files" if args.staged else "tracked repository"
print(f"Secret policy passed for {mode}.")
EOF_SECRET_POLICY

chmod 750 "$OPS_ROOT/scripts/secret-policy.py"

cat > "$OPS_ROOT/scripts/sops-finalize-helpers.sh" <<'EOF_FINALIZE'
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
: "${ADMIN_USER:?ADMIN_USER is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

[[ -x "$OPS_ROOT/scripts/sops-apply.sh" ]] || {
  printf 'ERROR: sops-apply.sh is missing\n' >&2
  exit 1
}

for encrypted_file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  [[ -s "$encrypted_file" ]] || {
    printf 'ERROR: encrypted source is missing: %s\n' "$encrypted_file" >&2
    exit 1
  }
done

cat > "$OPS_ROOT/scripts/observability-secrets.sh" <<'EOF_OBS_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

exec "$OPS_ROOT/scripts/sops-apply.sh" observability
EOF_OBS_WRAPPER

cat > "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" <<'EOF_GLITCHTIP_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

exec "$OPS_ROOT/scripts/sops-apply.sh" error-tracking
EOF_GLITCHTIP_WRAPPER

cat > "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" <<'EOF_GLITCHTIP_TOKEN_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

exec "$OPS_ROOT/scripts/sops-apply.sh" error-tracking
EOF_GLITCHTIP_TOKEN_WRAPPER

cat > "$OPS_ROOT/scripts/registry-login.sh" <<'EOF_REGISTRY_WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

exec "$OPS_ROOT/scripts/sops-apply.sh" registry
EOF_REGISTRY_WRAPPER

chmod 0750 \
  "$OPS_ROOT/scripts/observability-secrets.sh" \
  "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" \
  "$OPS_ROOT/scripts/registry-login.sh"

for script in \
  "$OPS_ROOT/scripts/observability-secrets.sh" \
  "$OPS_ROOT/scripts/glitchtip-secrets-ensure.sh" \
  "$OPS_ROOT/scripts/glitchtip-prometheus-token-ensure.sh" \
  "$OPS_ROOT/scripts/registry-login.sh"; do
  bash -n "$script"
done

printf 'Legacy secret generators now materialize only from SOPS.\n'
EOF_FINALIZE

chmod 750 "$OPS_ROOT/scripts/sops-finalize-helpers.sh"

cat > "$OPS_ROOT/scripts/secrets-update-registry.sh" <<'EOF_UPDATE_REGISTRY'
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

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${SOPS_REGISTRY_FILE:?SOPS_REGISTRY_FILE is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

export SOPS_AGE_KEY_FILE SOPS_CONFIG

TOKEN=''
cleanup() {
  TOKEN=''
  unset TOKEN
}
trap cleanup EXIT INT TERM

printf 'Paste the new GHCR read token. Input is hidden.\n'
IFS= read -r -s -p 'New GHCR read token: ' TOKEN
printf '\n'

[[ ${#TOKEN} -ge 20 ]] || {
  printf 'ERROR: token is unexpectedly short\n' >&2
  exit 1
}

printf '%s' "$TOKEN" |
  python3 -c 'import json,sys; json.dump(sys.stdin.read(), sys.stdout)' |
  sops set \
    --value-stdin \
    "$SOPS_REGISTRY_FILE" \
    '["token"]'

cleanup
trap - EXIT INT TERM

"$OPS_ROOT/scripts/sops-apply.sh" registry

printf 'Registry token updated in SOPS and applied to Docker auth.\n'
printf 'Commit secrets/registry.enc.yaml after reviewing git status.\n'
EOF_UPDATE_REGISTRY

chmod 750 "$OPS_ROOT/scripts/secrets-update-registry.sh"

cat > "$OPS_ROOT/scripts/secrets-update-telegram.sh" <<'EOF_UPDATE_TELEGRAM'
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

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${SERVER_HOSTNAME:?SERVER_HOSTNAME is not set}"
: "${SOPS_OBSERVABILITY_FILE:?SOPS_OBSERVABILITY_FILE is not set}"
: "${SOPS_AGE_KEY_FILE:?SOPS_AGE_KEY_FILE is not set}"
: "${SOPS_CONFIG:?SOPS_CONFIG is not set}"

[[ "$(id -un)" == "$ADMIN_USER" ]] || {
  printf 'ERROR: run as %s\n' "$ADMIN_USER" >&2
  exit 1
}

for command in curl jq python3 sops; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 1
  }
done

export SOPS_AGE_KEY_FILE SOPS_CONFIG

HTTPS_SCHEME="https"
TELEGRAM_API_HOST="api.telegram.org"

TOKEN=''
CHAT_ID=''
cleanup() {
  TOKEN=''
  CHAT_ID=''
  unset TOKEN CHAT_ID
}
trap cleanup EXIT INT TERM

printf 'Paste the replacement Telegram bot token. Input is hidden.\n'
IFS= read -r -s -p 'Telegram bot token: ' TOKEN
printf '\n'
IFS= read -r -p 'Telegram chat ID: ' CHAT_ID

[[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{20,}$ ]] || {
  printf 'ERROR: Telegram bot token format is invalid\n' >&2
  exit 1
}

[[ "$CHAT_ID" =~ ^-?[0-9]+$ ]] || {
  printf 'ERROR: Telegram chat ID format is invalid\n' >&2
  exit 1
}

telegram_api() {
  local method="$1"
  shift

  curl \
    --config - \
    "$@" <<EOF_CURL
url = "${HTTPS_SCHEME}://${TELEGRAM_API_HOST}/bot${TOKEN}/${method}"
fail
silent
show-error
max-time = 15
EOF_CURL
}

GET_ME="$(telegram_api getMe)"
[[ "$(jq -r '.ok' <<< "$GET_ME")" == "true" ]] || {
  printf 'ERROR: Telegram getMe failed\n' >&2
  exit 1
}

TEST_REPLY="$(
  telegram_api sendMessage \
    --request POST \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=SOPS Telegram credential validation on ${SERVER_HOSTNAME}."
)"

[[ "$(jq -r '.ok' <<< "$TEST_REPLY")" == "true" ]] || {
  printf 'ERROR: Telegram test message failed\n' >&2
  exit 1
}

printf '%s' "$TOKEN" |
  python3 -c 'import json,sys; json.dump(sys.stdin.read(), sys.stdout)' |
  sops set \
    --value-stdin \
    "$SOPS_OBSERVABILITY_FILE" \
    '["telegram_bot_token"]'

printf '%s' "$CHAT_ID" |
  python3 -c 'import json,sys; json.dump(sys.stdin.read(), sys.stdout)' |
  sops set \
    --value-stdin \
    "$SOPS_OBSERVABILITY_FILE" \
    '["telegram_chat_id"]'

cleanup
trap - EXIT INT TERM

"$OPS_ROOT/scripts/sops-apply.sh" observability
"$OPS_ROOT/scripts/observability-compose.sh" \
  up -d --no-deps --force-recreate alertmanager

printf 'Telegram credentials updated, applied and Alertmanager recreated.\n'
printf 'Commit secrets/observability.enc.yaml after reviewing git status.\n'
EOF_UPDATE_TELEGRAM

chmod 750 "$OPS_ROOT/scripts/secrets-update-telegram.sh"

cat > "$OPS_ROOT/.githooks/pre-commit" <<'EOF_PRECOMMIT'
#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 scripts/secret-policy.py --staged

VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
if [[ -r "$VPS_GUIDE_CONFIG" ]]; then
  # shellcheck source=/dev/null
  source "$VPS_GUIDE_CONFIG"
fi

if command -v sops >/dev/null 2>&1 && \
   [[ -n "${SOPS_AGE_KEY_FILE:-}" && -r "${SOPS_AGE_KEY_FILE:-}" ]]; then
  export SOPS_AGE_KEY_FILE

  while IFS= read -r -d '' path; do
    case "$path" in
      secrets/*.enc.yaml)
        git show ":$path" |
          sops decrypt \
            --input-type yaml \
            --output-type json >/dev/null || {
          printf 'ERROR: staged SOPS file cannot be decrypted: %s\n' \
            "$path" >&2
          exit 1
        }
        ;;
    esac
  done < <(
    git diff \
      --cached \
      --name-only \
      --diff-filter=ACMR \
      -z
  )
fi

printf 'Pre-commit secret checks passed.\n'
EOF_PRECOMMIT

chmod 750 "$OPS_ROOT/.githooks/pre-commit"

# В Bash `case` шаблон `*` матчится в том числе через `/`, поэтому
# `secrets/*.enc.yaml` покрывает и `secrets/foo.enc.yaml`, и вложенные
# `secrets/subdir/foo.enc.yaml`. Отдельный `secrets/**/*.enc.yaml` здесь
# намеренно не используется: ShellCheck считает его перекрытым (SC2221/SC2222).

cat > "$OPS_ROOT/.github/workflows/secret-policy.yml" <<'EOF_WORKFLOW'
name: Secret policy

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

concurrency:
  group: secret-policy-${{ github.ref }}
  cancel-in-progress: true

jobs:
  policy:
    runs-on: ubuntu-24.04
    timeout-minutes: 5

    steps:
      - name: Checkout
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Validate tracked secret policy
        run: python3 scripts/secret-policy.py
EOF_WORKFLOW

chmod 644 "$OPS_ROOT/.github/workflows/secret-policy.yml"

CURRENT_HOOKS_PATH="$(git -C "$OPS_ROOT" config --local --get core.hooksPath || true)"
if [[ -n "$CURRENT_HOOKS_PATH" && "$CURRENT_HOOKS_PATH" != ".githooks" ]]; then
  printf 'ERROR: existing core.hooksPath is %s; refusing to overwrite it.\n' \
    "$CURRENT_HOOKS_PATH" >&2
  exit 1
fi

git -C "$OPS_ROOT" config --local core.hooksPath .githooks

for script in \
  "$OPS_ROOT/scripts/sops-apply.sh" \
  "$OPS_ROOT/scripts/sops-migrate-existing.sh" \
  "$OPS_ROOT/scripts/sops-check.sh" \
  "$OPS_ROOT/scripts/sops-finalize-helpers.sh" \
  "$OPS_ROOT/scripts/secrets-update-registry.sh" \
  "$OPS_ROOT/scripts/secrets-update-telegram.sh" \
  "$OPS_ROOT/.githooks/pre-commit"; do
  bash -n "$script"
done

python3 -m py_compile "$OPS_ROOT/scripts/secret-policy.py"
rm -rf "$OPS_ROOT/scripts/__pycache__"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x \
    "$OPS_ROOT/scripts/sops-apply.sh" \
    "$OPS_ROOT/scripts/sops-migrate-existing.sh" \
    "$OPS_ROOT/scripts/sops-check.sh" \
    "$OPS_ROOT/scripts/sops-finalize-helpers.sh" \
    "$OPS_ROOT/scripts/secrets-update-registry.sh" \
    "$OPS_ROOT/scripts/secrets-update-telegram.sh" \
    "$OPS_ROOT/.githooks/pre-commit"
fi

printf 'SOPS workflow helpers, Git hook and CI policy installed.\n'
EOF_CH09_SCRIPT
chmod 0750 "$OPS_ROOT/scripts/chapter-09-install-workflow.sh"
"$OPS_ROOT/scripts/chapter-09-install-workflow.sh"
````

Ожидается:

```text
SOPS workflow helpers, Git hook and CI policy installed.
```

---

## 6. Мигрировать существующие production secrets в SOPS

Сейчас canonical source ещё находится в существующих runtime files глав 06–08.

Migration выполняется один раз:

```bash
"$OPS_ROOT/scripts/sops-migrate-existing.sh"
```

Script:

1. читает текущие Grafana/Telegram secrets;
2. читает текущие GlitchTip/PostgreSQL/Prometheus secrets;
3. извлекает GHCR credential из Docker `config.json`;
4. передаёт plaintext в SOPS через pipe;
5. не создаёт plaintext staging file в repository;
6. пишет только encrypted `*.enc.yaml`;
7. сразу проверяет decryptability;
8. повторно materialize runtime values из SOPS;
9. сравнение plaintext руками не требуется.

После успешного запуска должны появиться:

```text
/opt/ops/secrets/observability.enc.yaml
/opt/ops/secrets/error-tracking.enc.yaml
/opt/ops/secrets/registry.enc.yaml
```

Если encrypted file уже существует, migration **не перезаписывает его runtime-значениями**. Существующий encrypted source считается более новым source-of-truth и только проверяется на decryptability.

<details>
<summary>Необязательная проверка metadata без вывода secrets</summary>

```bash
find "$SOPS_SECRETS_ROOT" \
  -maxdepth 2 \
  -type f \
  -printf '%m %u:%g %P\n' |
  sort
```

Encrypted files и public recipient могут иметь `0644`.

Private key здесь **вообще не должен находиться**.

Проверить только наличие SOPS markers:

```bash
for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  grep -Fq 'ENC[AES256_GCM,' "$file" || exit 1
  grep -Fq 'sops:' "$file" || exit 1
done

printf 'Encrypted SOPS markers exist.\n'
```

</details>

---

## 7. Переключить старые secret helpers на SOPS source-of-truth

До этой главы scripts глав 06–08 могли:

- сгенерировать новый Grafana password;
- принять новый Telegram token;
- сгенерировать GlitchTip/PostgreSQL secrets;
- создать GlitchTip Prometheus token;
- принять новый GHCR token.

После появления SOPS это стало бы split-brain:

```text
runtime secret != encrypted source in Git
```

Выполнить **только одну команду**:

```bash
"$OPS_ROOT/scripts/sops-finalize-helpers.sh"
```

Ожидаемый вывод:

```text
Legacy secret generators now materialize only from SOPS.
```

**На этом шаг 7 завершён. Больше ничего из этого раздела в терминал вводить не нужно.**

После переключения логика helpers становится следующей:

| Helper | Что он теперь делает |
| --- | --- |
| `observability-secrets.sh` | вызывает `sops-apply.sh observability` |
| `glitchtip-secrets-ensure.sh` | вызывает `sops-apply.sh error-tracking` |
| `glitchtip-prometheus-token-ensure.sh` | вызывает `sops-apply.sh error-tracking` |
| `registry-login.sh` | вызывает `sops-apply.sh registry` |

Это **описание поведения**, а не команды для ручного запуска.

То есть повторный запуск старого operational helper больше не создаст новый secret мимо Git source-of-truth.

---

## 8. Зафиксировать encrypted source и policy в Git

Перейти в repository и удалить возможный пустой артефакт, который мог появиться только если в терминал была случайно вставлена старая поясняющая строка `-> sops-apply.sh ...`:

```bash
cd "$OPS_ROOT"

if [[ -f "$OPS_ROOT/sops-apply.sh" ]] && \
   [[ ! -s "$OPS_ROOT/sops-apply.sh" ]] && \
   ! git -C "$OPS_ROOT" ls-files --error-unmatch sops-apply.sh >/dev/null 2>&1; then
  rm -f -- "$OPS_ROOT/sops-apply.sh"
fi
```

Теперь staged all changes текущей главы:

```bash
git add -A
```

Проверить staged repository policy:

```bash
python3 scripts/secret-policy.py --staged
```

Ожидается:

```text
Secret policy passed for staged files.
```

Проверить whitespace errors:

```bash
git diff --cached --check
```

Показать только список/stats, не содержимое encrypted documents:

```bash
git status --short
git diff --cached --stat
```

В staged changes должны находиться `.sops.yaml`, encrypted files, public recipient, scripts, hook, workflow и изменения repository policy.

### Что проверяет pre-commit hook

При `git commit` hook проверяет **полный будущий Git index**, а не только случайный subset файлов:

- в `secrets/` разрешены только encrypted YAML, public recipients и README;
- runtime plaintext filenames запрещены;
- age private identity запрещён;
- private-key PEM/OpenSSH material запрещён;
- obvious GitHub/Telegram token patterns запрещены;
- `*.enc.yaml` должен выглядеть как SOPS encrypted YAML;
- staged encrypted files дополнительно должны успешно decrypt через production age identity.

### Что проверяет GitHub Actions

CI получает **только repository contents**.

Production age private key в GitHub Actions не добавляем.

CI проверяет:

- tracked secret policy;
- отсутствие obvious plaintext secret leaks;
- структуру SOPS-encrypted files.

Это специально устроено так, чтобы compromise CI environment не давал production decrypt key.

---

## 9. Commit и push

Commit:

```bash
git commit -m "Add SOPS age secrets management"
```

Перед созданием commit автоматически выполнится `.githooks/pre-commit`.

Ожидаемая последняя строка hook:

```text
Pre-commit secret checks passed.
```

Push:

```bash
git push origin main
```

---

## 10. Выполнить единый финальный check главы

> Важно: весь repair запускается в **отдельном Bash process**. Он не включает `set -u` в вашем интерактивном Zsh и не может сломать Oh My Zsh prompt/plugins.
>
> На Ubuntu GNU `chmod 0700 directory` может сохранить inherited `setgid` bit каталога и фактически оставить mode `2700`. Поэтому для Docker auth directory здесь используется **пятизначный** mode `00700`, который явно очищает special bits и оставляет ровно `0700`.

Если глава выполнялась по одной из ранних редакций, выполнить **один блок целиком**:

```bash
bash <<'CH09_REPAIR'
set -Eeuo pipefail

source "$HOME/config.env"
cd "$OPS_ROOT"

# -----------------------------------------------------------------------------
# 1. Нормализовать имя installer из ранней редакции.
# -----------------------------------------------------------------------------
python3 - <<'PY_RENAME'
from pathlib import Path
import subprocess

repo = Path.cwd()
legacy = Path("scripts") / ("chapter-09-install-workflow" + chr(92) + ".sh")
canonical = Path("scripts/chapter-09-install-workflow.sh")


def tracked(path: Path) -> bool:
    return subprocess.run(
        ["git", "--literal-pathspecs", "ls-files", "--error-unmatch", str(path)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


legacy_exists = legacy.exists()
canonical_exists = canonical.exists()
legacy_tracked = tracked(legacy)
canonical_tracked = tracked(canonical)

if canonical_exists:
    subprocess.run(["bash", "-n", str(canonical)], cwd=repo, check=True)

    if legacy_tracked:
        subprocess.run(
            ["git", "--literal-pathspecs", "rm", "-f", "--", str(legacy)],
            cwd=repo,
            check=True,
        )
    elif legacy_exists:
        legacy.unlink()

    if not canonical_tracked:
        subprocess.run(
            ["git", "--literal-pathspecs", "add", "--", str(canonical)],
            cwd=repo,
            check=True,
        )

    if legacy_exists or legacy_tracked:
        print(f"Removed legacy installer artifact: {legacy}")
        print(f"Canonical installer kept: {canonical}")
    else:
        print("Installer filename is already canonical.")

elif legacy_exists or legacy_tracked:
    if legacy_tracked:
        subprocess.run(
            ["git", "--literal-pathspecs", "mv", "--", str(legacy), str(canonical)],
            cwd=repo,
            check=True,
        )
    else:
        legacy.rename(canonical)
        subprocess.run(
            ["git", "--literal-pathspecs", "add", "--", str(canonical)],
            cwd=repo,
            check=True,
        )

    subprocess.run(["bash", "-n", str(canonical)], cwd=repo, check=True)
    print(f"Renamed legacy installer: {legacy} -> {canonical}")

else:
    raise SystemExit(
        "ERROR: Chapter 09 workflow installer is missing under both expected names"
    )
PY_RENAME

# -----------------------------------------------------------------------------
# 2. Исправить chmod semantics в runtime helper и canonical installer.
#    GNU chmod с 4-digit numeric mode сохраняет setgid у directories.
#    00700 явно очищает special bits.
# -----------------------------------------------------------------------------
python3 - \
  "$OPS_ROOT/scripts/sops-apply.sh" \
  "$OPS_ROOT/scripts/chapter-09-install-workflow.sh" <<'PY_CHMOD'
from pathlib import Path
import sys

for raw in sys.argv[1:]:
    path = Path(raw)
    text = path.read_text(encoding="utf-8")

    old = 'chmod 0700 "$REGISTRY_DOCKER_CONFIG"'
    new = 'chmod 00700 "$REGISTRY_DOCKER_CONFIG"'

    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
PY_CHMOD

bash -n "$OPS_ROOT/scripts/sops-apply.sh"
bash -n "$OPS_ROOT/scripts/chapter-09-install-workflow.sh"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x "$OPS_ROOT/scripts/sops-apply.sh"
fi

# -----------------------------------------------------------------------------
# 3. Materialize registry credential и выставить точные runtime permissions.
# -----------------------------------------------------------------------------
"$OPS_ROOT/scripts/sops-apply.sh" registry

# Пятизначный mode нужен намеренно: он очищает inherited setuid/setgid bits.
chmod 00700 "$REGISTRY_DOCKER_CONFIG"
chmod 00600 "$REGISTRY_DOCKER_CONFIG/config.json"

REGISTRY_DIR_MODE="$(stat -c '%a' "$REGISTRY_DOCKER_CONFIG")"
REGISTRY_FILE_MODE="$(stat -c '%a' "$REGISTRY_DOCKER_CONFIG/config.json")"
REGISTRY_DIR_OWNER="$(stat -c '%U:%G' "$REGISTRY_DOCKER_CONFIG")"
REGISTRY_FILE_OWNER="$(stat -c '%U:%G' "$REGISTRY_DOCKER_CONFIG/config.json")"

printf 'Registry auth directory: mode=%s owner=%s path=%s\n' \
  "$REGISTRY_DIR_MODE" "$REGISTRY_DIR_OWNER" "$REGISTRY_DOCKER_CONFIG"
printf 'Registry auth file:      mode=%s owner=%s path=%s\n' \
  "$REGISTRY_FILE_MODE" "$REGISTRY_FILE_OWNER" \
  "$REGISTRY_DOCKER_CONFIG/config.json"

[[ "$REGISTRY_DIR_MODE" == "700" ]] || {
  printf 'ERROR: registry auth directory is not exact mode 0700\n' >&2
  exit 1
}

[[ "$REGISTRY_FILE_MODE" == "600" ]] || {
  printf 'ERROR: registry auth config is not exact mode 0600\n' >&2
  exit 1
}

unset \
  REGISTRY_DIR_MODE REGISTRY_FILE_MODE \
  REGISTRY_DIR_OWNER REGISTRY_FILE_OWNER

# -----------------------------------------------------------------------------
# 4. Stage только известные compatibility changes.
# -----------------------------------------------------------------------------
git add -- \
  scripts/sops-apply.sh \
  scripts/chapter-09-install-workflow.sh

# Не позволять repair случайно закоммитить посторонние staged changes.
python3 - <<'PY_STAGE'
import subprocess

allowed = {
    "scripts/sops-apply.sh",
    "scripts/chapter-09-install-workflow.sh",
    "scripts/chapter-09-install-workflow" + chr(92) + ".sh",
}

raw = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only", "-z"]
)
staged = {item.decode() for item in raw.split(b"\0") if item}
unexpected = sorted(staged - allowed)

if unexpected:
    raise SystemExit(
        "ERROR: unrelated staged changes detected:\n  " + "\n  ".join(unexpected)
    )
PY_STAGE

if ! git diff --cached --quiet; then
  python3 scripts/secret-policy.py --staged
  git diff --cached --check
  git commit -m "Fix Chapter 09 SOPS compatibility"
  git push origin main
fi

# -----------------------------------------------------------------------------
# 5. Финальный acceptance check.
# -----------------------------------------------------------------------------
"$OPS_ROOT/scripts/sops-check.sh"
CH09_REPAIR
```

Ожидаемый конец:

```text
Registry auth directory: mode=700 owner=alex:ops ...
Registry auth file:      mode=600 owner=alex:ops ...
SOPS/age check passed. Runtime values match encrypted source-of-truth.
```

Если блок завершился с ошибкой, SSH-сессия **не закрывается**: завершается только дочерний `bash`.

После успешного финального check глава завершена.

---

## 11. Обычный workflow после этой главы

### Восстановить runtime secrets из Git source-of-truth

Если runtime files были случайно удалены или VPS восстанавливается после restore:

```bash
source "$HOME/config.env"
"$OPS_ROOT/scripts/sops-apply.sh" all
```

Можно materialize только один scope:

```bash
"$OPS_ROOT/scripts/sops-apply.sh" observability
"$OPS_ROOT/scripts/sops-apply.sh" error-tracking
"$OPS_ROOT/scripts/sops-apply.sh" registry
```

`registry` выполняет `docker login --password-stdin`; token не передаётся в command-line argument.

### Никогда не использовать это как обычный просмотр secrets

Не делать:

```text
sops decrypt secrets/observability.enc.yaml
sops decrypt secrets/error-tracking.enc.yaml
sops decrypt secrets/registry.enc.yaml
```

без redirect/consumer: это выведет plaintext в terminal и может попасть в scrollback, screen recording или support log.

Для operational workflow используются готовые scripts этой главы.

---

## 12. Безопасно обновить GHCR read token

После создания нового read-only GHCR token не выполнять обычный `docker login` вручную как постоянный workflow.

Запустить:

```bash
"$OPS_ROOT/scripts/secrets-update-registry.sh"
```

Script:

- читает token с hidden input;
- не передаёт token как CLI argument;
- записывает новое значение через `sops set --value-stdin`;
- materialize Docker auth;
- не создаёт plaintext temp file в Git repository.

После успеха:

```bash
cd "$OPS_ROOT"
git add secrets/registry.enc.yaml
git commit -m "Rotate GHCR read token"
git push origin main
```

Старый PAT после успешного применения и проверки нового credential отозвать в GitHub.

---

## 13. Безопасно обновить Telegram bot credential

Если Telegram token или target chat меняется:

```bash
"$OPS_ROOT/scripts/secrets-update-telegram.sh"
```

Script до изменения SOPS:

- валидирует token format;
- проверяет Telegram `getMe`;
- отправляет test message в указанный chat;

и только после успешной проверки:

- меняет оба encrypted values через stdin;
- materialize observability runtime files;
- пересоздаёт только `alertmanager`;
- не перезапускает Grafana/Prometheus/Loki/Alloy.

Commit:

```bash
cd "$OPS_ROOT"
git add secrets/observability.enc.yaml
git commit -m "Rotate Telegram alert credentials"
git push origin main
```

После успешного test message старый bot token можно revoke в BotFather, если выполнялась полноценная token rotation.

---

## 14. Stateful secrets: не менять универсальной командой

Следующие values **нельзя** безопасно менять только в encrypted YAML:

```text
observability.enc.yaml
  grafana_admin_password

error-tracking.enc.yaml
  secret_key
  postgres_password
  admin_password
  prometheus_token
```

Причина:

### `grafana_admin_password`

После первичной инициализации password хранится в Grafana database.

Изменить только file:

```text
SOPS value -> new
Grafana DB  -> old
```

получится drift.

### `postgres_password`

Password существует одновременно:

```text
PostgreSQL role
postgres.env
GlitchTip DATABASE_URL
SOPS source
```

Его rotation должна быть транзакционной и включать `ALTER ROLE`, обновление source, materialization и controlled container recreate.

### `prometheus_token`

Token существует в GlitchTip database. Случайный replacement только в SOPS немедленно сломает Prometheus scrape authentication.

### `admin_password`

GlitchTip administrator уже существует в database. Bootstrap password file не является runtime password authority после создания account.

### `secret_key`

Django/GlitchTip `SECRET_KEY` — cryptographic application identity. Его нельзя регулярно вращать как обычный API token без анализа влияния на signed sessions/tokens и support конкретной версии приложения.

Поэтому в этой главе нет опасной команды вида:

```text
sops-set-anything <key>
```

Stateful rotation выполняется отдельным service-aware runbook, когда она действительно нужна.

---

## 15. Почему GitHub SSH deploy key не переносим в SOPS

Текущий key:

```text
$GITHUB_SSH_KEY
```

нужен серверу, чтобы получить private `/opt/ops` repository.

Если положить этот private key в тот же encrypted repository:

```text
нужен Git key -> чтобы скачать repository
нужен repository -> чтобы получить Git key
```

получится bootstrap cycle.

Поэтому:

- GitHub deploy private key остаётся вне Git;
- age private identity остаётся вне Git;
- оба credential имеют отдельный recovery procedure;
- encrypted repository содержит application/platform secrets, но не credentials, без которых невозможно получить сам repository.

---

## 16. Rotation production age identity

Обычная периодическая rotation age identity для одного solo-admin VPS не нужна «каждые 30 дней» ради галочки.

Rotation нужна, если:

- private key мог быть скомпрометирован;
- ноутбук/recovery storage потерян;
- меняется operator/device trust boundary;
- требуется перейти на новый master identity по policy.

<details>
<summary>Процедура controlled age key rotation</summary>

### 1. Загрузить config

```bash
source "$HOME/config.env"
cd "$OPS_ROOT"
```

### 2. Создать новый identity рядом со старым, но не заменять старый

```bash
NEXT_KEY="$HOME/.config/sops/age/keys.next.txt"

[[ ! -e "$NEXT_KEY" ]] || {
  printf 'ERROR: next age key already exists: %s\n' "$NEXT_KEY" >&2
  exit 1
}

umask 077
age-keygen -o "$NEXT_KEY" >/dev/null
chmod 0600 "$NEXT_KEY"

OLD_RECIPIENT="$(age-keygen -y "$SOPS_AGE_KEY_FILE")"
NEW_RECIPIENT="$(age-keygen -y "$NEXT_KEY")"

printf 'Old public recipient: %s\n' "$OLD_RECIPIENT"
printf 'New public recipient: %s\n' "$NEW_RECIPIENT"
```

Это public values.

### 3. Создать recovery copy нового key **до переключения**

На локальном компьютере сохранить `keys.next.txt` так же, как в шаге 4 главы, и проверить SHA-256.

### 4. Временно добавить оба recipients в `.sops.yaml`

```bash
cat > "$SOPS_CONFIG" <<EOF_SOPS_ROTATE_ADD
---
creation_rules:
  - path_regex: '(^|/)secrets/.*\.enc\.yaml$'
    age:
      - $OLD_RECIPIENT
      - $NEW_RECIPIENT
    mac_only_encrypted: false

stores:
  yaml:
    indent: 2
EOF_SOPS_ROTATE_ADD
```

### 5. Добавить новый recipient во все encrypted files

```bash
for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  sops updatekeys -y "$file"
done
```

### 6. Проверить decrypt новым key отдельно

```bash
for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  SOPS_AGE_KEY_FILE="$NEXT_KEY" \
    sops decrypt \
      --input-type yaml \
      --output-type json \
      "$file" >/dev/null
done

printf 'New age identity decrypts all encrypted sources.\n'
```

### 7. Переключить server identity

```bash
mv "$SOPS_AGE_KEY_FILE" \
  "$HOME/.config/sops/age/keys.previous.txt"

mv "$NEXT_KEY" "$SOPS_AGE_KEY_FILE"
chmod 0600 "$SOPS_AGE_KEY_FILE"
```

### 8. Удалить old recipient и заменить SOPS data keys

```bash
cat > "$SOPS_CONFIG" <<EOF_SOPS_ROTATE_REMOVE
---
creation_rules:
  - path_regex: '(^|/)secrets/.*\.enc\.yaml$'
    age:
      - $NEW_RECIPIENT
    mac_only_encrypted: false

stores:
  yaml:
    indent: 2
EOF_SOPS_ROTATE_REMOVE

# Сначала updatekeys удаляет old recipient из metadata, затем rotate создаёт
# новый data key уже только под новым recipient.

printf '%s\n' "$NEW_RECIPIENT" > "$SOPS_AGE_RECIPIENT_FILE"
chmod 0644 "$SOPS_AGE_RECIPIENT_FILE"

for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  sops updatekeys -y "$file"
  sops rotate --in-place "$file"
done
```

### 9. Проверить current state

```bash
for file in \
  "$SOPS_OBSERVABILITY_FILE" \
  "$SOPS_ERROR_TRACKING_FILE" \
  "$SOPS_REGISTRY_FILE"; do
  grep -Fq "$NEW_RECIPIENT" "$file" || exit 1
  ! grep -Fq "$OLD_RECIPIENT" "$file" || exit 1
done

"$OPS_ROOT/scripts/sops-apply.sh" all
```

### 10. Commit rotation

```bash
git add \
  .sops.yaml \
  secrets/recipients/production.txt \
  secrets/*.enc.yaml

git commit -m "Rotate production age recipient"
git push origin main
```

### 11. Удалить old server identity только после successful push/recovery verification

```bash
rm -f "$HOME/.config/sops/age/keys.previous.txt"
unset OLD_RECIPIENT NEW_RECIPIENT NEXT_KEY
```

`rm` удаляет filesystem entry, но на SSD/VPS storage нельзя считать обычный `shred` криптографически гарантированным secure erase.

### Если old age identity был скомпрометирован

В процедуре выше current files уже получают новый SOPS data key через `sops rotate --in-place`. Это закрывает доступ старого recipient к **текущей** версии ciphertext.

Но удаление old recipient и rotation data key **не делают старую Git history недоступной старому key**: предыдущие commits всё ещё содержат старые encrypted data keys и старые значения.

Поэтому дополнительно требуется:

1. rotate реальные application credentials;
2. revoke старые external tokens;
3. отдельно обработать stateful credentials;
4. считать значения из старых commits скомпрометированными;
5. при необходимости выполнить incident-specific history rewrite.

`age` key rotation без rotation underlying secrets не является полноценным incident response.

</details>

---

## 17. Recovery age identity на новом VPS

При disaster recovery encrypted Git repository недостаточно.

На новом VPS после восстановления Git access:

```bash
install -d -m 0700 "$HOME/.config/sops/age"
```

С локального recovery storage передать key по SSH в этот path и затем на VPS:

```bash
chmod 0600 "$HOME/.config/sops/age/keys.txt"
```

Проверить public recipient:

```bash
age-keygen -y "$HOME/.config/sops/age/keys.txt"
```

Он должен совпасть с:

```text
secrets/recipients/production.txt
```

После восстановления `$HOME/config.env`:

```bash
source "$HOME/config.env"
"$OPS_ROOT/scripts/sops-apply.sh" all
```

Полный clean-server restore будет оформлен отдельно в Disaster Recovery chapter.

---

## 18. Диагностика

Все проверки ниже нужны **только если основной шаг завершился ошибкой**.

<details>
<summary>SOPS/age installer: checksum verification failed</summary>

Не отключать SHA-256 check и не устанавливать downloaded file вручную.

Удалить незавершённый temp download достаточно повторным запуском installer: он использует новый `mktemp` directory и сам очищает его.

Проверить архитектуру:

```bash
dpkg --print-architecture
```

Поддерживаются этой главой:

```text
amd64
arm64
```

Если upstream выпустил новую версию, **не менять только URL**. Одновременно должны быть обновлены:

```text
version
artifact filename
pinned checksum
```

</details>

<details>
<summary><code>no matching creation rules found</code> при encrypt</summary>

Проверить:

```bash
source "$HOME/config.env"
cd "$OPS_ROOT"

sed -n '1,120p' "$SOPS_CONFIG"
printf '%s\n' "$SOPS_OBSERVABILITY_FILE"
```

Encrypted filename должен заканчиваться:

```text
secrets/*.enc.yaml
```

и соответствовать `path_regex` из `.sops.yaml`.

Не переименовывать `.sops.yaml` в `.sops.yml`.

</details>

<details>
<summary>SOPS не может decrypt: age identity not found / no identity matched</summary>

Проверить только path/permissions:

```bash
source "$HOME/config.env"

stat -c '%a %U:%G %n' \
  "$(dirname "$SOPS_AGE_KEY_FILE")" \
  "$SOPS_AGE_KEY_FILE"
```

Ожидается:

```text
700 ... ~/.config/sops/age
600 ... ~/.config/sops/age/keys.txt
```

Сравнить public recipient без вывода private key:

```bash
ACTUAL="$(age-keygen -y "$SOPS_AGE_KEY_FILE")"
EXPECTED="$(cat "$SOPS_AGE_RECIPIENT_FILE")"
EXPECTED="${EXPECTED//$'\r'/}"

[[ "$ACTUAL" == "$EXPECTED" ]] || {
  printf 'ERROR: age identity does not match repository recipient\n' >&2
  exit 1
}

unset ACTUAL EXPECTED
```

Если key потерян, использовать recovery copy. Не генерировать новый key поверх старого recipient — новый identity не сможет decrypt существующие files.

</details>

<details>
<summary>Migration сообщает, что registry auth entry отсутствует</summary>

Chapter 06 хранит Docker auth в:

```text
$REGISTRY_DOCKER_CONFIG/config.json
```

Проверить только структуру без token:

```bash
jq \
  --arg host "$REGISTRY_HOST" \
  '{
    registry: $host,
    has_auth: (.auths[$host].auth | type == "string" and length > 0)
  }' \
  "$REGISTRY_DOCKER_CONFIG/config.json"
```

Должно быть:

```text
"has_auth": true
```

Если `false`, один раз восстановить working GHCR login способом главы 06, затем повторить migration.

Не вставлять PAT в command line.

</details>

<details>
<summary>Pre-commit hook блокирует commit</summary>

Hook намеренно нельзя обходить через `git commit --no-verify` для production repository.

Сначала выполнить:

```bash
cd "$OPS_ROOT"
python3 scripts/secret-policy.py --staged
```

Исправить конкретный path из ошибки.

Если plaintext secret уже staged:

```bash
git restore --staged -- path/to/file
```

После этого переместить value в SOPS-encrypted source, а plaintext file оставить только в разрешённом runtime path `/opt/data/...`.

</details>

<details>
<summary><code>runtime secret drift detected</code></summary>

Это означает:

```text
encrypted source != runtime file
```

Не сравнивать secret values через `cat`.

Если encrypted Git source является правильным:

```bash
"$OPS_ROOT/scripts/sops-apply.sh" all
"$OPS_ROOT/scripts/sops-check.sh"
```

Если правильным является runtime secret, сначала выяснить **почему он был изменён вне SOPS**.

Не запускать migration повторно с целью «затереть SOPS»: migration специально не перезаписывает уже существующий encrypted source.

</details>

<details>
<summary>После Telegram rotation Alertmanager не отправляет alerts</summary>

Сначала проверить только Alertmanager logs:

```bash
"$OPS_ROOT/scripts/observability-compose.sh" \
  logs --since=10m alertmanager
```

Повторно materialize + recreate только Alertmanager:

```bash
"$OPS_ROOT/scripts/sops-apply.sh" observability

"$OPS_ROOT/scripts/observability-compose.sh" \
  up -d --no-deps --force-recreate alertmanager
```

Не перезапускайте весь observability stack без причины.

</details>

<details>
<summary>Age private key случайно попал в Git</summary>

Считать key скомпрометированным, даже если commit ещё не был pushed.

1. остановить commit/push;
2. удалить private key из index;
3. выполнить controlled age key rotation;
4. если commit уже ушёл remote — считать старую Git history доступной владельцу старого key;
5. rotate underlying credentials по incident procedure.

Одного добавления файла в `.gitignore` после commit недостаточно.

</details>

---

## 19. Критерии завершения главы

Глава 09 завершена, если одновременно выполнено всё:

```text
[ ] SOPS 3.13.3 установлен и checksum-verified
[ ] age 1.3.1 установлен и checksum-verified
[ ] private age identity существует вне /opt/ops
[ ] private age identity имеет mode 0600
[ ] age directory имеет mode 0700
[ ] recovery copy age identity сохранена вне VPS и checksum совпал
[ ] .sops.yaml tracked в Git
[ ] production public recipient tracked в Git
[ ] observability.enc.yaml tracked и decryptable
[ ] error-tracking.enc.yaml tracked и decryptable
[ ] registry.enc.yaml tracked и decryptable
[ ] runtime plaintext secrets остались только под /opt/data/...
[ ] старые secret helper scripts больше не генерируют независимые secrets
[ ] pre-commit hook включён через core.hooksPath=.githooks
[ ] GitHub Actions secret-policy workflow tracked
[ ] production age key отсутствует в GitHub Actions secrets
[ ] secret-policy.py проходит
[ ] sops-check.sh проходит
[ ] working tree clean
[ ] local main == origin/main
```

Главный acceptance test:

```bash
"$OPS_ROOT/scripts/sops-check.sh"
```

---

## 20. Технические ориентиры главы

В этой главе используются следующие security/operational принципы:

- SOPS шифрует leaf values structured YAML, а metadata/keys остаются inspectable;
- age X25519 identity используется как master recipient для SOPS data key;
- SOPS умеет находить age identity в `~/.config/sops/age/keys.txt`, но scripts дополнительно фиксируют `SOPS_AGE_KEY_FILE`;
- `.sops.yaml` является repository policy и задаёт creation rule;
- при encryption из stdin обязательно используется filename override, чтобы SOPS применил правильную creation rule;
- `sops set --value-stdin` используется вместо передачи secret value в command-line argument;
- `sops updatekeys` используется для изменения recipients без необходимости вручную редактировать SOPS metadata;
- encrypted source может безопасно version-control изменяться и review-иться без plaintext value;
- private decryption identity не передаётся GitHub Actions;
- Docker/runtime всё равно нуждается в plaintext representation, поэтому SOPS не отменяет host hardening и permissions;
- recovery identity является частью disaster-recovery capability, а не optional convenience.

### Почему используем обычный X25519 age key, а не усложняем схему

Для single-VPS / solo-developer production baseline важнее:

```text
простая recovery model
предсказуемая SOPS interoperability
минимум moving parts
```

Hardware-backed/PQ recipients можно добавить позже как второй recipient через `sops updatekeys`, не меняя runtime architecture.

---

## 21. Что намеренно не делаем в этой главе

Не добавляем:

- HashiCorp Vault/OpenBao — для текущего single-VPS масштаба лишний control plane;
- Infisical server — требует отдельного stateful stack и ресурсов;
- production age private key в GitHub Actions secrets;
- plaintext `.env` secrets в repository;
- decrypt-on-every-container-start через fragile shell wrapper;
- secret values в Docker image build args;
- secret values в CLI arguments;
- generic «rotate any key» script для stateful services;
- automatic periodic master-key rotation без security reason;
- backup repository — это следующая глава;
- automatic destructive Git history rewrite.

---

## 22. Следующая глава

После SOPS следующий крупнейший production gap — **off-site backups**.

Следующая глава:

```text
10 — restic: encrypted off-site backups, retention, systemd timer,
     Telegram failure alerts и Prometheus backup-age metric
```

В Chapter 10 будем backup не только «каталог целиком», а разделим:

```text
Git-backed configuration
runtime data
database-native dumps
application files
backup metadata
```

и сразу заложим основу для отдельного Chapter 11 с реальным restore test.
