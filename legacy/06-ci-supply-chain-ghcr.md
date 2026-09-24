# Глава 06. CI supply chain: GitHub, GitHub Actions, GHCR и immutable image digest

Эта глава добавляет следующий слой поверх production contract из главы 05:

- существующий `/opt/ops` подключается к отдельному private GitHub repository;
- VPS получает отдельный repo-scoped SSH Deploy Key только для этого repository;
- GitHub Actions собирает тестовый OCI/Docker image;
- image публикуется в GitHub Container Registry (`ghcr.io`);
- перед публикацией image проходит vulnerability scan;
- при публикации BuildKit добавляет SBOM и provenance attestations;
- production никогда не деплоит mutable tag вроде `latest`;
- VPS получает точный `IMAGE@sha256:...`;
- существующий `/opt/ops/scripts/app-deploy.sh` остаётся единственной точкой production-деплоя;
- GitHub Actions **не получает SSH-ключ от VPS** и в этой главе не выполняет удалённый deploy;
- private GHCR pull credential хранится вне Git в отдельном Docker config directory;
- все несекретные настройки сервера хранятся в едином расширяемом `$HOME/config.env`; отдельные `chapter-*.env` и `platform.env` больше не создаются.

> Команды рассчитаны на текущее состояние после успешно завершённой главы 05.
>
> Не вставляйте в терминал заголовки Markdown, разделители `---`, поясняющий текст и строки ожидаемого вывода. В терминал копируется только содержимое блоков `bash`.
>
> Если команда завершилась ошибкой, не переходите к следующему номеру шага, пока причина не устранена.

---

## 0. Что именно строим

```text
local /opt/ops Git repository
     |
     | SSH Deploy Key, write access only to one repository
     v
private GitHub repository
     |
     | push to main
     v
GitHub Actions
     |
     | checkout exact commit
     | build scan candidate
     | Trivy scan
     | build + SBOM + provenance
     v
GHCR
ghcr.io/<owner>/<repo>-ci-smoke:sha-<git-sha>
ghcr.io/<owner>/<repo>-ci-smoke@sha256:<digest>
     |
     | authenticated pull
     v
VPS
/opt/ops/scripts/app-deploy.sh deploy-test IMAGE@sha256:DIGEST
     |
     v
existing Caddy -> deploy-test
```

В этой итерации **нет continuous deployment**.

Сначала проверяем supply chain: `source -> CI -> registry -> immutable digest -> existing production deploy contract`. Автоматический доступ GitHub runner к VPS будет отдельной итерацией.

---

## 1. Проверить checkpoint главы 05

```bash
source "$HOME/config.env"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"

DEPLOY_TEST_STACK="${DEPLOY_TEST_STACK:-deploy-test}"
DEPLOY_TEST_DOMAIN="${DEPLOY_TEST_DOMAIN:-deploy-test.$BASE_DOMAIN}"

export DEPLOY_TEST_STACK DEPLOY_TEST_DOMAIN
```

Git-дерево должно быть чистым:

```bash
test -z "$(git -C "$OPS_ROOT" status --porcelain)" || {
  printf 'ERROR: %s has uncommitted changes\n' "$OPS_ROOT" >&2
  git -C "$OPS_ROOT" status --short >&2
  exit 1
}
```

Проверить текущую ветку и локальную историю:

```bash
CURRENT_BRANCH="$(git -C "$OPS_ROOT" branch --show-current)"

[[ "$CURRENT_BRANCH" == "main" ]] || {
  printf 'ERROR: expected branch main, got: %s\n' "$CURRENT_BRANCH" >&2
  exit 1
}

git -C "$OPS_ROOT" log -5 --oneline
```

Production health:

```bash
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3

curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'
```

Caddy:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose ps

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Systemd:

```bash
sudo systemctl --failed
```

Не продолжать, пока все проверки главы 05 не проходят.

---

## 2. Задать и сохранить GitHub repository identity

На VPS выполнить следующий блок и изменить только три значения в начале.

Для personal repository `REGISTRY_USERNAME` обычно совпадает с `GITHUB_OWNER`. Если repository принадлежит GitHub Organization, в `GITHUB_OWNER` указывается организация, а в `REGISTRY_USERNAME` — личный GitHub login владельца PAT, который будет использоваться VPS для чтения private GHCR package.

Значения сразу записываются в единый `$HOME/config.env`, поэтому они не потеряются после выхода из SSH-сессии.

```bash
source "$HOME/config.env"

GITHUB_OWNER="CHANGE_ME_GITHUB_OWNER"
OPS_REPO_NAME="vps-ops"
REGISTRY_USERNAME="CHANGE_ME_REGISTRY_USERNAME"

[[ "$GITHUB_OWNER" != CHANGE_ME_* ]] || {
  printf 'ERROR: set GITHUB_OWNER first\n' >&2
  exit 1
}

[[ "$REGISTRY_USERNAME" != CHANGE_ME_* ]] || {
  printf 'ERROR: set REGISTRY_USERNAME first\n' >&2
  exit 1
}

[[ "$GITHUB_OWNER" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]] || {
  printf 'ERROR: invalid GITHUB_OWNER: %s\n' "$GITHUB_OWNER" >&2
  exit 1
}

[[ "$OPS_REPO_NAME" =~ ^[A-Za-z0-9._-]{1,100}$ ]] || {
  printf 'ERROR: invalid OPS_REPO_NAME: %s\n' "$OPS_REPO_NAME" >&2
  exit 1
}

[[ "$OPS_REPO_NAME" != "." && "$OPS_REPO_NAME" != ".." ]] || {
  printf 'ERROR: invalid OPS_REPO_NAME: %s\n' "$OPS_REPO_NAME" >&2
  exit 1
}

[[ "$REGISTRY_USERNAME" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]] || {
  printf 'ERROR: invalid REGISTRY_USERNAME: %s\n' \
    "$REGISTRY_USERNAME" >&2
  exit 1
}

CONFIG_ENV="$HOME/config.env"

python3 - \
  "$CONFIG_ENV" \
  "$GITHUB_OWNER" \
  "$OPS_REPO_NAME" \
  "$REGISTRY_USERNAME" <<'PY_GITHUB_IDENTITY'
from pathlib import Path
import re
import shlex
import sys

path = Path(sys.argv[1])
values = {
    "GITHUB_OWNER": sys.argv[2],
    "OPS_REPO_NAME": sys.argv[3],
    "REGISTRY_USERNAME": sys.argv[4],
}

text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
seen = set()
out = []

pattern = re.compile(
    r"^\s*export\s+(GITHUB_OWNER|OPS_REPO_NAME|REGISTRY_USERNAME)="
)

for line in lines:
    match = pattern.match(line)
    if not match:
        out.append(line)
        continue

    name = match.group(1)
    if name in seen:
        continue

    out.append(f"export {name}={shlex.quote(values[name])}")
    seen.add(name)

missing = [name for name in values if name not in seen]
if missing:
    if out and out[-1].strip():
        out.append("")
    out.extend([
        "# =============================================================================",
        "# GITHUB — repository identity",
        "# =============================================================================",
    ])
    for name in missing:
        out.append(f"export {name}={shlex.quote(values[name])}")

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY_GITHUB_IDENTITY

chmod 0600 "$CONFIG_ENV"
bash -n "$CONFIG_ENV"
source "$CONFIG_ENV"

printf '%s\n' \
  "GITHUB_OWNER=$GITHUB_OWNER" \
  "OPS_REPO_NAME=$OPS_REPO_NAME" \
  "REGISTRY_USERNAME=$REGISTRY_USERNAME" \
  "CONFIG_ENV=$CONFIG_ENV"
```

Проверить Git identity существующего локального repository:

```bash
printf '%s\n' \
  "Git user.name=$(git -C "$OPS_ROOT" config --get user.name)" \
  "Git user.email=$(git -C "$OPS_ROOT" config --get user.email)"
```

Оба значения должны быть непустыми. В главах 1–5 они уже использовались для локальных commit.

---
## 3. Создать private GitHub repository

Repository создаётся через GitHub web UI. Это намеренно: VPS не получает GitHub API token с правом создания repositories.

Открыть:

```text
https://github.com/new
```

Создать repository со следующими параметрами:

```text
Owner:       значение GITHUB_OWNER
Repository:  значение OPS_REPO_NAME
Visibility:  Private
```

**Не включать** при создании repository:

- `Add a README file`;
- `.gitignore` template;
- license;
- repository template.

Remote repository должен быть полностью пустым. История уже существует локально в `/opt/ops` и будет отправлена на GitHub без merge и force push.

---

## 4. Создать отдельный SSH Deploy Key для GitHub

Используем отдельный Ed25519 key только для `/opt/ops`. Он не является SSH-ключом входа на VPS и не используется для других repositories.

Создать ключ:

```bash
source "$HOME/config.env"

: "${OPS_REPO_NAME:?repeat step 2: OPS_REPO_NAME is not set}"

GITHUB_SSH_KEY="$HOME/.ssh/github_ops_ed25519"

install -d -m 0700 "$HOME/.ssh"

if [[ -e "$GITHUB_SSH_KEY" || -e "${GITHUB_SSH_KEY}.pub" ]]; then
  printf 'ERROR: GitHub deploy key already exists: %s\n' \
    "$GITHUB_SSH_KEY" >&2
  exit 1
fi

ssh-keygen \
  -t ed25519 \
  -f "$GITHUB_SSH_KEY" \
  -C "${SERVER_HOSTNAME}:${OPS_REPO_NAME}:deploy-key" \
  -N ''

chmod 0600 "$GITHUB_SSH_KEY"
chmod 0644 "${GITHUB_SSH_KEY}.pub"
```

Не использовать `ssh-keyscan` вслепую. Добавить официальный GitHub Ed25519 host key напрямую:

```bash
GITHUB_KNOWN_HOST='github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl'

install -m 0600 /dev/null "$HOME/.ssh/known_hosts.tmp"

if [[ -f "$HOME/.ssh/known_hosts" ]]; then
  cat "$HOME/.ssh/known_hosts" > "$HOME/.ssh/known_hosts.tmp"
fi

if ! grep -Fqx "$GITHUB_KNOWN_HOST" "$HOME/.ssh/known_hosts.tmp"; then
  printf '%s\n' "$GITHUB_KNOWN_HOST" >> "$HOME/.ssh/known_hosts.tmp"
fi

mv -f "$HOME/.ssh/known_hosts.tmp" "$HOME/.ssh/known_hosts"
chmod 0600 "$HOME/.ssh/known_hosts"
```

Актуальный fingerprint официального Ed25519 host key GitHub:

```text
SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
```

Показать public deploy key:

```bash
printf 'Deploy key title: %s\n\n' \
  "${SERVER_HOSTNAME}-${OPS_REPO_NAME}-write"

cat "${GITHUB_SSH_KEY}.pub"
```

Приватный файл `$HOME/.ssh/github_ops_ed25519` никуда не копировать и не добавлять в GitHub.

---

## 5. Добавить Deploy Key в GitHub repository

В GitHub открыть:

```text
Repository -> Settings -> Deploy keys -> Add deploy key
```

Заполнить:

```text
Title:  значение из команды Deploy key title
Key:    содержимое ~/.ssh/github_ops_ed25519.pub
```

Включить:

```text
Allow write access
```

Write access нужен только потому, что `/opt/ops` в текущей архитектуре является рабочим инфраструктурным repository на VPS и дальнейшие главы продолжают выполнять `git push` с сервера.

Deploy Key выбран вместо SSH key пользовательского GitHub account, потому что он ограничен одним repository.

---

## 6. Настроить `origin` и отправить существующую историю в GitHub

Загрузить сохранённую identity из единого конфигурационного файла:

```bash
source "$HOME/config.env"

: "${GITHUB_OWNER:?GITHUB_OWNER is not set}"
: "${OPS_REPO_NAME:?OPS_REPO_NAME is not set}"
: "${REGISTRY_USERNAME:?REGISTRY_USERNAME is not set}"

GITHUB_SSH_KEY="$HOME/.ssh/github_ops_ed25519"
GITHUB_REMOTE="git@github.com:${GITHUB_OWNER}/${OPS_REPO_NAME}.git"

if git -C "$OPS_ROOT" remote get-url origin >/dev/null 2>&1; then
  CURRENT_ORIGIN="$(git -C "$OPS_ROOT" remote get-url origin)"

  [[ "$CURRENT_ORIGIN" == "$GITHUB_REMOTE" ]] || {
    printf 'ERROR: origin already exists and points elsewhere:\n%s\n' \
      "$CURRENT_ORIGIN" >&2
    exit 1
  }
else
  git -C "$OPS_ROOT" remote add origin "$GITHUB_REMOTE"
fi

git -C "$OPS_ROOT" config \
  core.sshCommand \
  "ssh -i $GITHUB_SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
```

Проверить доступ Deploy Key к repository:

```bash
git -C "$OPS_ROOT" ls-remote origin >/dev/null
printf 'GitHub SSH access: OK\n'
```

Проверить remote:

```bash
git -C "$OPS_ROOT" remote -v

git -C "$OPS_ROOT" config --get core.sshCommand
```

Отправить уже существующую историю глав 1–5:

```bash
git -C "$OPS_ROOT" push -u origin main
```

Сверить local и remote HEAD:

```bash
LOCAL_HEAD="$(git -C "$OPS_ROOT" rev-parse HEAD)"
REMOTE_HEAD="$(
  git -C "$OPS_ROOT" ls-remote origin refs/heads/main |
  awk '{print $1}'
)"

printf '%s\n' \
  "LOCAL_HEAD=$LOCAL_HEAD" \
  "REMOTE_HEAD=$REMOTE_HEAD"

[[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]]
```


> На этом этапе private GitHub repository уже содержит всю существующую историю `/opt/ops` до начала CI-изменений главы 06.

---

## 7. Усилить GitHub Actions policy repository

До добавления workflow открыть:

```text
Repository -> Settings -> Actions -> General
```

Установить:

```text
Actions permissions:
  Allow OWNER, and select non-OWNER, actions and reusable workflows

Enable:
  Allow actions created by GitHub

Disable / do not enable:
  Allow Marketplace actions by verified creators
```

Если доступна настройка:

```text
Require actions to be pinned to a full-length commit SHA
```

включить её.

В `Workflow permissions` оставить минимальный default:

```text
Read repository contents and packages permissions
```

Не включать:

```text
Allow GitHub Actions to create and approve pull requests
```

Если отображаются настройки private fork workflows, не включать передачу write token и secrets в fork pull requests.

Workflow этой главы сам запрашивает только:

```yaml
permissions:
  contents: read
  packages: write
```

---

## 8. Расширить единый `$HOME/config.env`

Начиная с этой версии инструкции сервер использует один расширяемый конфигурационный файл:

```text
/home/alex/config.env
```

В командах используется `$HOME/config.env`, поэтому путь не требуется дублировать вручную.

Старые `/etc/vps-guide/config.env`, `/etc/vps-guide/platform.env` и `chapter-*.env` считаются legacy-файлами предыдущих версий инструкции. В этой главе они больше не читаются и не изменяются. Удалять их сейчас не требуется: старые production-скрипты главы 05 будут мигрированы точечно в следующем шаге.

`config.env` содержит только несекретные параметры и пути. GitHub PAT, пароли, private SSH keys и другие credentials в него не записываются.

Создать управляющий скрипт главы 06:

````bash
cat > "$OPS_ROOT/scripts/chapter-06-configure.sh" <<'EOF_CHAPTER_06_CONFIGURE'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ $EUID -ne 0 ]] || {
  printf 'ERROR: run this script as the regular admin user, not through sudo\n' >&2
  exit 1
}

[[ $# -le 1 ]] || {
  printf 'Usage: %s [REGISTRY_USERNAME]\n' "$0" >&2
  exit 2
}

CONFIG_ENV="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -f "$CONFIG_ENV" && ! -L "$CONFIG_ENV" ]] || {
  printf 'ERROR: config file is missing or is not a regular file: %s\n' \
    "$CONFIG_ENV" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$CONFIG_ENV"

: "${OPS_ROOT:?OPS_ROOT is not set}"
: "${APPS_ROOT:?APPS_ROOT is not set}"
: "${DATA_ROOT:?DATA_ROOT is not set}"
: "${ADMIN_USER:?ADMIN_USER is not set}"
: "${OPS_GROUP:?OPS_GROUP is not set}"
: "${BASE_DOMAIN:?BASE_DOMAIN is not set}"

command -v git >/dev/null 2>&1 || {
  printf 'ERROR: git is not installed\n' >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: python3 is not installed\n' >&2
  exit 1
}

ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"

[[ -n "$ADMIN_HOME" && "$HOME" == "$ADMIN_HOME" ]] || {
  printf 'ERROR: run as configured ADMIN_USER=%s\n' "$ADMIN_USER" >&2
  exit 1
}

GITHUB_REMOTE="$(git -C "$OPS_ROOT" remote get-url origin 2>/dev/null || true)"

[[ -n "$GITHUB_REMOTE" ]] || {
  printf 'ERROR: Git remote origin is not configured\n' >&2
  exit 1
}

REGISTRY_IDENTITY="$(
  python3 - "$GITHUB_REMOTE" <<'PY_GITHUB_REMOTE'
import re
import sys
from urllib.parse import urlparse

remote = sys.argv[1].strip()
scp = re.fullmatch(r"git@github\.com:([^/]+)/(.+)", remote)

if scp:
    owner, repo = scp.groups()
else:
    parsed = urlparse(remote)

    if parsed.hostname != "github.com":
        raise SystemExit(f"ERROR: origin is not GitHub: {remote}")

    parts = parsed.path.strip("/").split("/")

    if len(parts) != 2:
        raise SystemExit(f"ERROR: unexpected GitHub remote: {remote}")

    owner, repo = parts

repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)

if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner):
    raise SystemExit(f"ERROR: unsupported GitHub owner: {owner}")

if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", repo):
    raise SystemExit(f"ERROR: unsupported GitHub repository name: {repo}")

if repo in {".", ".."}:
    raise SystemExit(f"ERROR: unsupported GitHub repository name: {repo}")

print(f"{owner}\t{repo}")
PY_GITHUB_REMOTE
)" || exit 1

GITHUB_OWNER="${REGISTRY_IDENTITY%%$'\t'*}"
OPS_REPO_NAME="${REGISTRY_IDENTITY#*$'\t'}"
REGISTRY_USERNAME="${1:-${REGISTRY_USERNAME:-$GITHUB_OWNER}}"

[[ "$REGISTRY_USERNAME" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]] || {
  printf 'ERROR: invalid REGISTRY_USERNAME: %s\n' \
    "$REGISTRY_USERNAME" >&2
  exit 1
}

GITHUB_SSH_KEY="$HOME/.ssh/github_ops_ed25519"

[[ -f "$GITHUB_SSH_KEY" && ! -L "$GITHUB_SSH_KEY" ]] || {
  printf 'ERROR: GitHub private deploy key is missing: %s\n' \
    "$GITHUB_SSH_KEY" >&2
  exit 1
}

[[ -f "${GITHUB_SSH_KEY}.pub" && ! -L "${GITHUB_SSH_KEY}.pub" ]] || {
  printf 'ERROR: GitHub public deploy key is missing: %s\n' \
    "${GITHUB_SSH_KEY}.pub" >&2
  exit 1
}

REGISTRY_HOST="ghcr.io"
REGISTRY_OWNER="${GITHUB_OWNER,,}"
REGISTRY_REPOSITORY="${OPS_REPO_NAME,,}"
REGISTRY_DOCKER_CONFIG="$DATA_ROOT/docker-auth"
CI_SMOKE_IMAGE="${REGISTRY_HOST}/${REGISTRY_OWNER}/${REGISTRY_REPOSITORY}-ci-smoke"

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

BEGIN_MARKER='# BEGIN VPS GUIDE CHAPTER 06'
END_MARKER='# END VPS GUIDE CHAPTER 06'
BLOCK_FILE="$(mktemp)"
OUTPUT_FILE="$(mktemp "${CONFIG_ENV}.tmp.XXXXXX")"

cleanup() {
  rm -f "$BLOCK_FILE" "$OUTPUT_FILE"
}

trap cleanup EXIT INT TERM

write_export() {
  local name="$1"
  local value="$2"

  printf 'export %s=%q\n' "$name" "$value" >> "$BLOCK_FILE"
}

{
  printf '%s\n' "$BEGIN_MARKER"
  printf '# GitHub / GHCR / deployment platform settings.\n'
  printf '# Contains no passwords, private keys or API tokens.\n'
} > "$BLOCK_FILE"

write_export GITHUB_OWNER "$GITHUB_OWNER"
write_export OPS_REPO_NAME "$OPS_REPO_NAME"
write_export GITHUB_REMOTE "$GITHUB_REMOTE"
write_export GITHUB_SSH_KEY "$GITHUB_SSH_KEY"
write_export REGISTRY_HOST "$REGISTRY_HOST"
write_export REGISTRY_OWNER "$REGISTRY_OWNER"
write_export REGISTRY_USERNAME "$REGISTRY_USERNAME"
write_export REGISTRY_DOCKER_CONFIG "$REGISTRY_DOCKER_CONFIG"
write_export CI_SMOKE_IMAGE "$CI_SMOKE_IMAGE"
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

printf '%s\n' "$END_MARKER" >> "$BLOCK_FILE"

python3 - \
  "$CONFIG_ENV" \
  "$BLOCK_FILE" \
  "$OUTPUT_FILE" \
  "$BEGIN_MARKER" \
  "$END_MARKER" <<'PY_CONFIG_MERGE'
from pathlib import Path
import re
import sys

config_path = Path(sys.argv[1])
block_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
begin = sys.argv[4]
end = sys.argv[5]

managed = {
    "GITHUB_OWNER",
    "OPS_REPO_NAME",
    "GITHUB_REMOTE",
    "GITHUB_SSH_KEY",
    "REGISTRY_HOST",
    "REGISTRY_OWNER",
    "REGISTRY_USERNAME",
    "REGISTRY_DOCKER_CONFIG",
    "CI_SMOKE_IMAGE",
    "DEPLOY_APPS_ROOT",
    "DEPLOY_STATE_ROOT",
    "DEPLOY_LOCK_TIMEOUT",
    "DEPLOY_WAIT_TIMEOUT",
    "DEPLOY_HTTP_ATTEMPTS",
    "DEPLOY_HTTP_DELAY",
    "DEPLOY_HTTP_TIMEOUT",
    "DEPLOY_HISTORY_LIMIT",
    "DEPLOY_TEST_STACK",
    "DEPLOY_TEST_DOMAIN",
    "DEPLOY_TEST_UPSTREAM",
    "DEPLOY_TEST_SERVICE",
}

pattern = re.compile(
    r"^\s*export\s+(" + "|".join(sorted(map(re.escape, managed))) + r")="
)

lines = config_path.read_text(encoding="utf-8").splitlines()
out = []
in_old_block = False

for line in lines:
    stripped = line.strip()

    if stripped == begin:
        in_old_block = True
        continue

    if in_old_block:
        if stripped == end:
            in_old_block = False
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
PY_CONFIG_MERGE

chmod 0600 "$OUTPUT_FILE"
mv -f "$OUTPUT_FILE" "$CONFIG_ENV"
chmod 0600 "$CONFIG_ENV"

LOADER_DIR="$HOME/.config/vps-guide"
LOADER_FILE="$LOADER_DIR/load-env.sh"
ZSH_LOADER_FILE="$LOADER_DIR/load-env.zsh"

install -d -m 0700 "$LOADER_DIR"

cat > "$LOADER_FILE" <<'EOF_LOADER'
if [ -r "$HOME/config.env" ]; then
  . "$HOME/config.env"
fi
EOF_LOADER

cat > "$ZSH_LOADER_FILE" <<'EOF_ZSH_LOADER'
if [[ -r "$HOME/.config/vps-guide/load-env.sh" ]]; then
  source "$HOME/.config/vps-guide/load-env.sh"
fi
EOF_ZSH_LOADER

chmod 0600 "$LOADER_FILE" "$ZSH_LOADER_FILE"

for rc_file in "$HOME/.bashrc" "$HOME/.zshrc"; do
  touch "$rc_file"

  if ! grep -Fq '$HOME/.config/vps-guide/load-env.sh' "$rc_file" && \
     ! grep -Fq '$HOME/.config/vps-guide/load-env.zsh' "$rc_file"; then
    cat >> "$rc_file" <<'EOF_RC'

# VPS Guide environment
if [ -r "$HOME/.config/vps-guide/load-env.sh" ]; then
  . "$HOME/.config/vps-guide/load-env.sh"
fi
EOF_RC
  fi
done

bash -n "$CONFIG_ENV"

printf 'Updated unified config: %s\n' "$CONFIG_ENV"
printf 'Updated loader: %s\n' "$LOADER_FILE"
printf 'Updated Zsh loader: %s\n' "$ZSH_LOADER_FILE"
EOF_CHAPTER_06_CONFIGURE

chmod 0750 "$OPS_ROOT/scripts/chapter-06-configure.sh"

bash -n "$OPS_ROOT/scripts/chapter-06-configure.sh"
shellcheck -x "$OPS_ROOT/scripts/chapter-06-configure.sh"
````

Для personal repository, когда GHCR PAT принадлежит тому же GitHub account, выполнить:

```bash
"$OPS_ROOT/scripts/chapter-06-configure.sh"
```

Если repository принадлежит Organization и PAT принадлежит другому GitHub login, передать login явно:

```bash
"$OPS_ROOT/scripts/chapter-06-configure.sh" "CHANGE_ME_GITHUB_LOGIN"
```

Не выполнять второй вариант, пока `CHANGE_ME_GITHUB_LOGIN` не заменён реальным GitHub login владельца PAT.

Загрузить единый конфигурационный файл:

```bash
source "$HOME/config.env"
```

Проверить:

```bash
printf '%s\n' \
  "GITHUB_OWNER=$GITHUB_OWNER" \
  "OPS_REPO_NAME=$OPS_REPO_NAME" \
  "GITHUB_REMOTE=$GITHUB_REMOTE" \
  "GITHUB_SSH_KEY=$GITHUB_SSH_KEY" \
  "REGISTRY_HOST=$REGISTRY_HOST" \
  "REGISTRY_OWNER=$REGISTRY_OWNER" \
  "REGISTRY_USERNAME=$REGISTRY_USERNAME" \
  "REGISTRY_DOCKER_CONFIG=$REGISTRY_DOCKER_CONFIG" \
  "CI_SMOKE_IMAGE=$CI_SMOKE_IMAGE" \
  "DEPLOY_APPS_ROOT=$DEPLOY_APPS_ROOT" \
  "DEPLOY_STATE_ROOT=$DEPLOY_STATE_ROOT" \
  "DEPLOY_TEST_STACK=$DEPLOY_TEST_STACK" \
  "DEPLOY_TEST_DOMAIN=$DEPLOY_TEST_DOMAIN"

stat -c '%A %U:%G %n' \
  "$HOME/config.env" \
  "$HOME/.config/vps-guide/load-env.sh" \
  "$HOME/.config/vps-guide/load-env.zsh"
```

Ожидаемые права:

```text
-rw------- alex:alex /home/alex/config.env
-rw------- alex:alex /home/alex/.config/vps-guide/load-env.sh
-rw------- alex:alex /home/alex/.config/vps-guide/load-env.zsh
```

Проверить автоматическую загрузку в новой Zsh-сессии:

```bash
zsh -lic 'printf "OPS_ROOT=%s\nREGISTRY_HOST=%s\nCI_SMOKE_IMAGE=%s\n" "$OPS_ROOT" "$REGISTRY_HOST" "$CI_SMOKE_IMAGE"'
```

Все три значения должны быть непустыми.

---

## 9. Перевести deployment scripts на единый `config.env`

Скрипты главы 05 были созданы по старой схеме и могли читать `/etc/vps-guide/config.env` и `/etc/vps-guide/platform.env`. Перевести используемые production-скрипты на единый `$HOME/config.env` и удалить больше не нужный генератор `platform.env` из repository.

Выполнить:

````bash
python3 - \
  "$OPS_ROOT/scripts/lib/app-common.sh" \
  "$OPS_ROOT/scripts/caddy-add-site.sh" \
  "$OPS_ROOT/scripts/caddy-remove-site.sh" <<'PY_MIGRATE_CONFIG'
from pathlib import Path
import sys

app_common = Path(sys.argv[1])
caddy_add = Path(sys.argv[2])
caddy_remove = Path(sys.argv[3])

old_app_common = '''# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env
# shellcheck source=/etc/vps-guide/platform.env
source /etc/vps-guide/platform.env
'''

new_app_common = '''VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"

: "${REGISTRY_DOCKER_CONFIG:?REGISTRY_DOCKER_CONFIG is not set}"
export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"
'''

old_single = '''# shellcheck source=/etc/vps-guide/config.env
source /etc/vps-guide/config.env
'''

new_single = '''VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"

[[ -r "$VPS_GUIDE_CONFIG" ]] || {
  printf 'ERROR: config file is not readable: %s\\n' "$VPS_GUIDE_CONFIG" >&2
  exit 1
}

# shellcheck source=/dev/null
source "$VPS_GUIDE_CONFIG"
'''


def replace_once(path: Path, old: str, new: str, already: str) -> None:
    text = path.read_text(encoding="utf-8")

    if already in text:
        print(f"Already migrated: {path}")
        return

    if old not in text:
        raise SystemExit(f"ERROR: expected legacy config block not found: {path}")

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Migrated: {path}")


replace_once(
    app_common,
    old_app_common,
    new_app_common,
    'source "$VPS_GUIDE_CONFIG"',
)

for path in (caddy_add, caddy_remove):
    replace_once(
        path,
        old_single,
        new_single,
        'source "$VPS_GUIDE_CONFIG"',
    )
PY_MIGRATE_CONFIG

rm -f "$OPS_ROOT/scripts/platform-configure.sh"
````

Проверить начало общей deployment-библиотеки:

```bash
sed -n '1,35p' "$OPS_ROOT/scripts/lib/app-common.sh"
```

Должны присутствовать:

```bash
VPS_GUIDE_CONFIG="${VPS_GUIDE_CONFIG:-$HOME/config.env}"
source "$VPS_GUIDE_CONFIG"
export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"
```

Проверить, что production-скрипты больше не зависят от старой конфигурационной схемы:

```bash
if grep -nE '/etc/vps-guide/(config|platform)\.env' \
  "$OPS_ROOT/scripts/lib/app-common.sh" \
  "$OPS_ROOT/scripts/caddy-add-site.sh" \
  "$OPS_ROOT/scripts/caddy-remove-site.sh"; then
  printf 'ERROR: legacy config reference still exists\n' >&2
  exit 1
fi
```

Static checks:

```bash
(
  cd "$OPS_ROOT/scripts"

  bash -n \
    chapter-06-configure.sh \
    app-deploy.sh \
    app-rollback.sh \
    app-health.sh \
    app-status.sh \
    app-compose.sh \
    caddy-add-site.sh \
    caddy-remove-site.sh \
    lib/app-common.sh

  shellcheck -x \
    chapter-06-configure.sh \
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

---

## 10. Создать отдельный Docker config для registry credentials

Registry authentication не хранится в `$HOME/config.env`. В конфигурации находится только путь:

```text
REGISTRY_DOCKER_CONFIG=/opt/data/docker-auth
```

Сам Docker credential будет храниться в:

```text
/opt/data/docker-auth/config.json
```

Создать каталог:

```bash
source "$HOME/config.env"

sudo install -d \
  -o "$ADMIN_USER" \
  -g "$OPS_GROUP" \
  -m 0700 \
  "$REGISTRY_DOCKER_CONFIG"
```

Проверить:

```bash
stat -c '%A %U:%G %n' "$REGISTRY_DOCKER_CONFIG"
```

Ожидается:

```text
drwx------ alex:ops /opt/data/docker-auth
```

---
## 11. Создать команду registry login

```bash
cat > "$OPS_ROOT/scripts/registry-login.sh" <<'EOF_REGISTRY_LOGIN'
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

: "${REGISTRY_HOST:?REGISTRY_HOST is not set}"
: "${REGISTRY_OWNER:?REGISTRY_OWNER is not set}"
: "${REGISTRY_USERNAME:?REGISTRY_USERNAME is not set}"
: "${REGISTRY_DOCKER_CONFIG:?REGISTRY_DOCKER_CONFIG is not set}"

command -v docker >/dev/null 2>&1 || {
  printf 'ERROR: docker is not installed\n' >&2
  exit 1
}

[[ -d "$REGISTRY_DOCKER_CONFIG" ]] || {
  printf 'ERROR: Docker config directory does not exist: %s\n' \
    "$REGISTRY_DOCKER_CONFIG" >&2
  exit 1
}

[[ -w "$REGISTRY_DOCKER_CONFIG" ]] || {
  printf 'ERROR: Docker config directory is not writable: %s\n' \
    "$REGISTRY_DOCKER_CONFIG" >&2
  exit 1
}

export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"

TOKEN=''

cleanup() {
  TOKEN=''
  unset TOKEN
}

trap cleanup EXIT INT TERM

printf 'Registry: %s\n' "$REGISTRY_HOST"
printf 'User:     %s\n' "$REGISTRY_USERNAME"
printf 'Token is read without echo and is not stored in shell history.\n'

IFS= read -r -s -p 'GHCR read token: ' TOKEN
printf '\n'

[[ -n "$TOKEN" ]] || {
  printf 'ERROR: empty token\n' >&2
  exit 1
}

printf '%s' "$TOKEN" |
  docker login \
    "$REGISTRY_HOST" \
    --username "$REGISTRY_USERNAME" \
    --password-stdin

if [[ -f "$REGISTRY_DOCKER_CONFIG/config.json" ]]; then
  chmod 0600 "$REGISTRY_DOCKER_CONFIG/config.json"
  chgrp "$OPS_GROUP" "$REGISTRY_DOCKER_CONFIG/config.json"
fi

printf 'Registry login completed.\n'
EOF_REGISTRY_LOGIN

chmod 0750 "$OPS_ROOT/scripts/registry-login.sh"

bash -n "$OPS_ROOT/scripts/registry-login.sh"
shellcheck -x "$OPS_ROOT/scripts/registry-login.sh"
```

---

## 12. Создать GitHub PAT только для чтения private GHCR package

Для private GHCR package создать в GitHub **Personal access token (classic)** от account, указанного в `REGISTRY_USERNAME`. GitHub Packages для внешнего CLI login использует именно PAT classic.

Открыть в GitHub account:

```text
Settings
  -> Developer settings
  -> Personal access tokens
  -> Tokens (classic)
  -> Generate new token (classic)
```

Рекомендуемые параметры:

```text
Note:       server-ghcr-read
Expiration: 90 days
Scope:      read:packages
```

Не добавлять `write:packages`, `delete:packages` и `repo`, если они отдельно не нужны. Если GitHub Organization требует SSO authorization, авторизовать созданный token для этой Organization.

Скопировать token сразу после создания: GitHub повторно его не покажет.

Не записывать PAT:

- в `$HOME/config.env`;
- в `.env`;
- в Git;
- в README;
- в shell command line.

Выполнить:

```bash
"$OPS_ROOT/scripts/registry-login.sh"
```

Проверить:

```bash
source "$HOME/config.env"

stat -c '%A %U:%G %n' \
  "$REGISTRY_DOCKER_CONFIG" \
  "$REGISTRY_DOCKER_CONFIG/config.json"

case "$REGISTRY_DOCKER_CONFIG" in
  "$OPS_ROOT"|"$OPS_ROOT"/*)
    printf 'ERROR: registry auth must not live under OPS_ROOT\n' >&2
    exit 1
    ;;
esac
```

Ожидаемые права не шире:

```text
drwx------ alex:ops /opt/data/docker-auth
-rw------- alex:ops /opt/data/docker-auth/config.json
```

---

## 13. Создать CI smoke image context

```bash
install -d -m 0755 \
  "$OPS_ROOT/examples/ci-smoke" \
  "$OPS_ROOT/examples/ci-smoke/site" \
  "$OPS_ROOT/.github/workflows"
```

Dockerfile с exact base digest:

```bash
cat > "$OPS_ROOT/examples/ci-smoke/Dockerfile" <<'EOF_CI_SMOKE_DOCKERFILE'
FROM busybox:1.38.0@sha256:fd8d9aa63ba2f0982b5304e1ee8d3b90a210bc1ffb5314d980eb6962f1a9715d

LABEL org.opencontainers.image.title="vps-guide-ci-smoke"
LABEL org.opencontainers.image.description="CI supply-chain smoke image"

COPY site/ /www/

EXPOSE 8080

HEALTHCHECK \
  --interval=5s \
  --timeout=3s \
  --start-period=5s \
  --retries=6 \
  CMD wget -q -O - http://127.0.0.1:8080/health || exit 1

CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
EOF_CI_SMOKE_DOCKERFILE
```

Site:

```bash
cat > "$OPS_ROOT/examples/ci-smoke/site/index.html" <<'EOF_CI_SMOKE_INDEX'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CI supply chain smoke</title>
</head>
<body>
  <main>
    <h1>CI supply chain image works</h1>
  </main>
</body>
</html>
EOF_CI_SMOKE_INDEX

printf 'ci-supply-chain-ok\n' \
  > "$OPS_ROOT/examples/ci-smoke/site/health"

cat > "$OPS_ROOT/examples/ci-smoke/.dockerignore" <<'EOF_CI_SMOKE_DOCKERIGNORE'
.git
*.log
*.tmp
*.bak
*.bak.*
EOF_CI_SMOKE_DOCKERIGNORE

find "$OPS_ROOT/examples/ci-smoke" \
  -type d -exec chmod 0755 {} +

find "$OPS_ROOT/examples/ci-smoke" \
  -type f -exec chmod 0644 {} +
```

Build check:

```bash
docker buildx build \
  --check \
  "$OPS_ROOT/examples/ci-smoke"
```

Local smoke test:

```bash
LOCAL_CI_SMOKE_TAG="vps-guide/ci-smoke:local"

docker build \
  --pull \
  --tag "$LOCAL_CI_SMOKE_TAG" \
  "$OPS_ROOT/examples/ci-smoke"

docker rm -f ci-smoke-local >/dev/null 2>&1 || true

docker run \
  --detach \
  --name ci-smoke-local \
  "$LOCAL_CI_SMOKE_TAG" >/dev/null

for attempt in {1..12}; do
  if docker exec ci-smoke-local \
      wget -q -O - http://127.0.0.1:8080/health |
      grep -Fx 'ci-supply-chain-ok'; then
    break
  fi

  if (( attempt == 12 )); then
    docker logs ci-smoke-local >&2 || true
    docker rm -f ci-smoke-local >/dev/null 2>&1 || true
    printf 'ERROR: local CI smoke image did not become healthy\n' >&2
    exit 1
  fi

  sleep 2
done

docker rm -f ci-smoke-local >/dev/null
```

---

## 14. Создать GitHub Actions workflow

Workflow намеренно:

- не использует `pull_request_target`;
- не содержит VPS secrets и SSH;
- не публикует `latest`;
- использует full Git SHA tag;
- checkout pinned на полный commit SHA;
- выполняет vulnerability scan **до** registry push;
- добавляет SBOM и provenance;
- печатает точный digest.

````bash
cat > "$OPS_ROOT/.github/workflows/container-ci.yml" <<'EOF_CONTAINER_CI'
name: container-ci

on:
  workflow_dispatch:
  push:
    branches:
      - main
    paths:
      - examples/ci-smoke/**
      - .github/workflows/container-ci.yml

permissions:
  contents: read
  packages: write

concurrency:
  group: container-ci-${{ github.ref }}
  cancel-in-progress: false

jobs:
  build-scan-publish:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - name: Checkout repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Validate runner tooling
        shell: bash
        run: |
          set -Eeuo pipefail
          docker version
          docker buildx version
          jq --version

      - name: Derive immutable image coordinates
        id: image
        shell: bash
        run: |
          set -Eeuo pipefail

          owner="${GITHUB_REPOSITORY_OWNER,,}"
          repository="${GITHUB_REPOSITORY#*/}"
          repository="${repository,,}"

          image="ghcr.io/${owner}/${repository}-ci-smoke"
          tag="sha-${GITHUB_SHA}"

          [[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]

          printf 'image=%s\n' "$image" >> "$GITHUB_OUTPUT"
          printf 'tag=%s\n' "$tag" >> "$GITHUB_OUTPUT"

      - name: Login to GHCR
        shell: bash
        env:
          GHCR_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -Eeuo pipefail

          printf '%s' "$GHCR_TOKEN" |
            docker login ghcr.io \
              --username "$GITHUB_ACTOR" \
              --password-stdin

      - name: Create Buildx builder
        shell: bash
        run: |
          set -Eeuo pipefail

          docker buildx create \
            --name vps-guide-ci \
            --driver docker-container \
            --driver-opt "image=moby/buildkit:v0.30.0@sha256:0168606be2315b7c807a03b3d8aa79beefdb31c98740cebdffdfeebf31190c9f" \
            --use

          docker buildx inspect --bootstrap

      - name: Build scan candidate
        shell: bash
        env:
          IMAGE: ${{ steps.image.outputs.image }}
          TAG: ${{ steps.image.outputs.tag }}
        run: |
          set -Eeuo pipefail

          docker buildx build \
            --pull \
            --load \
            --tag "${IMAGE}:${TAG}" \
            --label "org.opencontainers.image.source=${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}" \
            --label "org.opencontainers.image.revision=${GITHUB_SHA}" \
            examples/ci-smoke

      - name: Report HIGH and CRITICAL vulnerabilities
        shell: bash
        env:
          IMAGE: ${{ steps.image.outputs.image }}
          TAG: ${{ steps.image.outputs.tag }}
        run: |
          set -Eeuo pipefail

          docker run --rm \
            --volume /var/run/docker.sock:/var/run/docker.sock \
            docker.io/aquasec/trivy@sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f \
            image \
            --scanners vuln \
            --severity HIGH,CRITICAL \
            --exit-code 0 \
            "${IMAGE}:${TAG}"

      - name: Block fixable HIGH and CRITICAL vulnerabilities
        shell: bash
        env:
          IMAGE: ${{ steps.image.outputs.image }}
          TAG: ${{ steps.image.outputs.tag }}
        run: |
          set -Eeuo pipefail

          docker run --rm \
            --volume /var/run/docker.sock:/var/run/docker.sock \
            docker.io/aquasec/trivy@sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f \
            image \
            --scanners vuln \
            --ignore-unfixed \
            --severity HIGH,CRITICAL \
            --exit-code 1 \
            "${IMAGE}:${TAG}"

      - name: Build and publish attested image
        id: publish
        shell: bash
        env:
          IMAGE: ${{ steps.image.outputs.image }}
          TAG: ${{ steps.image.outputs.tag }}
        run: |
          set -Eeuo pipefail

          metadata_file="$RUNNER_TEMP/build-metadata.json"

          docker buildx build \
            --pull \
            --push \
            --sbom=true \
            --provenance=mode=max \
            --metadata-file "$metadata_file" \
            --tag "${IMAGE}:${TAG}" \
            --label "org.opencontainers.image.source=${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}" \
            --label "org.opencontainers.image.revision=${GITHUB_SHA}" \
            examples/ci-smoke

          digest="$(
            jq -r '."containerimage.digest" // empty' \
              "$metadata_file"
          )"

          [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || {
            printf 'Invalid build digest: %s\n' "$digest" >&2
            exit 1
          }

          image_ref="${IMAGE}@${digest}"

          printf 'digest=%s\n' "$digest" >> "$GITHUB_OUTPUT"
          printf 'image-ref=%s\n' "$image_ref" >> "$GITHUB_OUTPUT"

          {
            printf '## Published immutable image\n\n'
            printf '`%s`\n\n' "$image_ref"
            printf -- '- commit: `%s`\n' "$GITHUB_SHA"
            printf -- '- tag: `%s:%s`\n' "$IMAGE" "$TAG"
            printf -- '- SBOM: enabled\n'
            printf -- '- provenance: `mode=max`\n'
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Verify published digest
        shell: bash
        env:
          IMAGE_REF: ${{ steps.publish.outputs.image-ref }}
        run: |
          set -Eeuo pipefail

          [[ "$IMAGE_REF" =~ @sha256:[a-f0-9]{64}$ ]]
          docker buildx imagetools inspect "$IMAGE_REF"

      - name: Logout from GHCR
        if: always()
        shell: bash
        run: |
          docker logout ghcr.io >/dev/null 2>&1 || true
EOF_CONTAINER_CI
````

BuildKit запускается через `docker-container` driver на pinned image `moby/buildkit:v0.30.0@sha256:...`, поэтому builder не подтягивается по mutable `buildx-stable-1`.

Trivy здесь запускается как official container, pinned на exact multi-platform image digest (`0.72.0`), а не по mutable tag и не как дополнительный GitHub Action. Единственный `uses:` — immutable pin `actions/checkout`.

---

## 15. Добавить Dependabot для action pins

```bash
cat > "$OPS_ROOT/.github/dependabot.yml" <<'EOF_DEPENDABOT'
version: 2

updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
EOF_DEPENDABOT

chmod 0644 \
  "$OPS_ROOT/.github/workflows/container-ci.yml" \
  "$OPS_ROOT/.github/dependabot.yml"
```

---

## 16. Локально проверить workflow до commit

GitHub Actions expressions `${{ ... }}` не являются shell variables. Не выполнять workflow вручную как Bash.

Проверить YAML:

```bash
python3 - "$OPS_ROOT/.github/workflows/container-ci.yml" <<'PY_VALIDATE_WORKFLOW'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit(
        "ERROR: Python module PyYAML is missing. "
        "Install python3-yaml and retry."
    )

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "\t" in text:
    raise SystemExit("ERROR: workflow contains TAB characters")

data = yaml.safe_load(text)

if not isinstance(data, dict):
    raise SystemExit("ERROR: workflow root must be a mapping")

jobs = data.get("jobs")

if not isinstance(jobs, dict) or "build-scan-publish" not in jobs:
    raise SystemExit("ERROR: build-scan-publish job is missing")

print(f"YAML parsed successfully: {path}")
PY_VALIDATE_WORKFLOW
```

Если `PyYAML` отсутствует:

```bash
sudo apt-get update
sudo apt-get install -y python3-yaml
```

Повторить YAML validation.

Проверить отсутствие VPS credentials:

```bash
if grep -En \
  '(SSH_PRIVATE|SERVER_IP|TAILSCALE_AUTH|TS_OAUTH|PASSWORD|PRIVATE_KEY)' \
  "$OPS_ROOT/.github/workflows/container-ci.yml"; then
  printf 'ERROR: workflow appears to contain deployment credentials\n' >&2
  exit 1
fi
```

Проверить immutable action pins:

```bash
python3 - "$OPS_ROOT/.github/workflows/container-ci.yml" <<'PY_VALIDATE_ACTION_PINS'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

uses = re.findall(r"(?m)^[ \t]*uses:[ \t]*([^ \t#]+)", text)

for value in uses:
    if value.startswith("./"):
        continue

    if "@" not in value:
        raise SystemExit(f"ERROR: action is not pinned: {value}")

    action, ref = value.rsplit("@", 1)

    if not re.fullmatch(r"[a-f0-9]{40}", ref):
        raise SystemExit(
            f"ERROR: action must use a full 40-character SHA: {value}"
        )

    print(f"Pinned: {action}@{ref}")
PY_VALIDATE_ACTION_PINS
```

Dockerfile check:

```bash
docker buildx build \
  --check \
  "$OPS_ROOT/examples/ci-smoke"
```

---

## 17. Проверить изменения перед первым CI commit

```bash
git -C "$OPS_ROOT" status --short
```

Добавить только ожидаемые файлы:

```bash
git -C "$OPS_ROOT" add \
  .github/workflows/container-ci.yml \
  .github/dependabot.yml \
  examples/ci-smoke \
  scripts/chapter-06-configure.sh \
  scripts/caddy-add-site.sh \
  scripts/caddy-remove-site.sh \
  scripts/lib/app-common.sh \
  scripts/registry-login.sh

git -C "$OPS_ROOT" add -u -- \
  scripts/platform-configure.sh
```

`$HOME/config.env` и `/opt/data/docker-auth` находятся вне `/opt/ops` и в Git не добавляются.

Проверить:

```bash
git -C "$OPS_ROOT" diff --cached --stat
git -C "$OPS_ROOT" diff --cached --check
```

### Исправленная проверка runtime/backup-файлов

Проверяем только `Added`, `Copied`, `Modified`, `Renamed`, но не staged deletion:

```bash
if git -C "$OPS_ROOT" \
    diff --cached --diff-filter=ACMR --name-only |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|.*\.bak(?:\..*)?)$'; then
  printf 'ERROR: runtime env or backup is being added/modified in Git\n' >&2
  exit 1
fi
```

Проверить Docker credentials:

```bash
if git -C "$OPS_ROOT" \
    diff --cached --diff-filter=ACMR --name-only |
  grep -E '(^|/)(config\.json|docker-auth)(/|$)'; then
  printf 'ERROR: Docker registry credentials are staged\n' >&2
  exit 1
fi
```

Посмотреть staged names:

```bash
git -C "$OPS_ROOT" diff --cached --name-status
```

---

## 18. Создать первый commit итерации 06

```bash
git -C "$OPS_ROOT" commit \
  -m 'Add GHCR container CI supply chain'
```

Проверить:

```bash
git -C "$OPS_ROOT" log -1 --oneline
git -C "$OPS_ROOT" status --short
```

---

## 19. Отправить commit в GitHub

```bash
CURRENT_BRANCH="$(git -C "$OPS_ROOT" branch --show-current)"

printf 'Current branch: %s\n' "$CURRENT_BRANCH"

[[ "$CURRENT_BRANCH" == "main" ]] || {
  printf 'ERROR: this chapter expects the main branch\n' >&2
  exit 1
}
```

Push:

```bash
git -C "$OPS_ROOT" push origin main
```

Сверить local/remote HEAD:

```bash
LOCAL_HEAD="$(git -C "$OPS_ROOT" rev-parse HEAD)"
REMOTE_HEAD="$(
  git -C "$OPS_ROOT" \
    ls-remote origin refs/heads/main |
  awk '{print $1}'
)"

printf '%s\n' \
  "LOCAL_HEAD=$LOCAL_HEAD" \
  "REMOTE_HEAD=$REMOTE_HEAD"

[[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]]
```

Если push не проходит из-за GitHub authentication, не добавлять token в remote URL и не передавать PAT прямо в command line.

---

## 20. Проверить GitHub Actions run

В GitHub открыть:

```text
Repository -> Actions -> container-ci
```

Должны успешно пройти:

```text
Checkout repository
Validate runner tooling
Derive immutable image coordinates
Login to GHCR
Create Buildx builder
Build scan candidate
Report HIGH and CRITICAL vulnerabilities
Block fixable HIGH and CRITICAL vulnerabilities
Build and publish attested image
Verify published digest
Logout from GHCR
```

В Job Summary должен появиться:

```text
Published immutable image

ghcr.io/<owner>/<repo>-ci-smoke@sha256:<64 hex chars>
```

Если GHCR push падает с `403`:

1. проверить `permissions: packages: write`;
2. проверить, что Actions разрешены для repository;
3. если package с таким именем существовал раньше — проверить repository linkage и Actions access;
4. не расширять `GITHUB_TOKEN` до ненужных permissions.

---

## 21. Проверить registry image с VPS

После успешного workflow:

```bash
source "$HOME/config.env"

export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"
```

Если registry authentication потеряна:

```bash
"$OPS_ROOT/scripts/registry-login.sh"
```

Определить commit/tag:

```bash
CI_SHA="$(git -C "$OPS_ROOT" rev-parse HEAD)"
CI_TAG="sha-${CI_SHA}"

[[ "$CI_SHA" =~ ^[a-f0-9]{40}$ ]]

printf '%s\n' \
  "CI_SHA=$CI_SHA" \
  "CI_TAG=$CI_TAG" \
  "CI_SMOKE_IMAGE=$CI_SMOKE_IMAGE"
```

Pull:

```bash
docker pull "${CI_SMOKE_IMAGE}:${CI_TAG}"
```

Получить exact digest:

```bash
CI_IMAGE_REF="$(
  docker image inspect \
    "${CI_SMOKE_IMAGE}:${CI_TAG}" \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' |
  grep -F "${CI_SMOKE_IMAGE}@sha256:" |
  head -n 1
)"

[[ "$CI_IMAGE_REF" =~ ^[^[:space:]]+@sha256:[a-f0-9]{64}$ ]] || {
  printf 'ERROR: immutable GHCR digest was not found\n' >&2
  exit 1
}

printf 'CI_IMAGE_REF=%s\n' "$CI_IMAGE_REF"
```

Ожидаемый формат:

```text
ghcr.io/<owner>/<repo>-ci-smoke@sha256:<64 hex chars>
```

---

## 22. Убедиться, что mutable tags production не принимает

Тест должен остановиться до `docker pull` и ничего не менять:

```bash
source "$HOME/config.env"

CI_SHA="$(git -C "$OPS_ROOT" rev-parse HEAD)"
CI_TAG="sha-${CI_SHA}"

set +e

"$OPS_ROOT/scripts/app-deploy.sh" \
  "$DEPLOY_TEST_STACK" \
  "${CI_SMOKE_IMAGE}:${CI_TAG}"

status=$?

set -e

[[ "$status" -ne 0 ]] || {
  printf 'ERROR: mutable image tag was unexpectedly accepted\n' >&2
  exit 1
}

printf 'Mutable tag correctly rejected.\n'
```

Ожидается ошибка:

```text
Image must be an exact sha256 digest
```

Убедиться, что active release не изменился:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3
```

---

## 23. Выполнить production deploy GHCR image по digest

Снова получить все переменные в одном блоке, не полагаясь на старую shell session:

```bash
source "$HOME/config.env"

export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"

CI_SHA="$(git -C "$OPS_ROOT" rev-parse HEAD)"
CI_TAG="sha-${CI_SHA}"

docker pull "${CI_SMOKE_IMAGE}:${CI_TAG}"

CI_IMAGE_REF="$(
  docker image inspect \
    "${CI_SMOKE_IMAGE}:${CI_TAG}" \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' |
  grep -F "${CI_SMOKE_IMAGE}@sha256:" |
  head -n 1
)"

[[ "$CI_IMAGE_REF" =~ ^[^[:space:]]+@sha256:[a-f0-9]{64}$ ]]

"$OPS_ROOT/scripts/app-deploy.sh" \
  "$DEPLOY_TEST_STACK" \
  "$CI_IMAGE_REF"
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

Running image:

```bash
docker inspect deploy-test-app-1 \
  --format 'Image={{.Config.Image}}'
```

`Current` должен содержать `ghcr.io/...@sha256:...`, а не tag.

---

## 24. Проверить rollback после registry deploy

Сначала статус:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
```

Rollback:

```bash
"$OPS_ROOT/scripts/app-rollback.sh" \
  "$DEPLOY_TEST_STACK"
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

History:

```bash
column -t -s $'\t' \
  "$DEPLOY_STATE_ROOT/$DEPLOY_TEST_STACK/deploy/history.tsv"
```

Новые записи должны отражать `deploy` GHCR digest и затем `rollback` к предыдущему digest.

---

## 25. Проверить registry auth isolation

```bash
source "$HOME/config.env"

stat -c '%A %U:%G %n' \
  "$REGISTRY_DOCKER_CONFIG" \
  "$REGISTRY_DOCKER_CONFIG/config.json"
```

Проверить физический путь:

```bash
REGISTRY_CONFIG_REAL="$(
  realpath "$REGISTRY_DOCKER_CONFIG/config.json"
)"

OPS_ROOT_REAL="$(realpath "$OPS_ROOT")"

case "$REGISTRY_CONFIG_REAL" in
  "$OPS_ROOT_REAL"|"$OPS_ROOT_REAL"/*)
    printf 'ERROR: registry credential file is inside Git repository\n' >&2
    exit 1
    ;;
esac

printf 'Registry credential location is outside Git: %s\n' \
  "$REGISTRY_CONFIG_REAL"
```

---

## 26. Обновить README инфраструктуры

Внешний fence этого блока использует **четыре** обратные кавычки, потому что создаваемый README сам содержит тройные Markdown fences.

````bash
cat > "$OPS_ROOT/README.md" <<'EOF_OPS_README'
# VPS operations repository

## Layout

- `compose/edge/` — global Caddy edge
- `compose/apps/` — production application Compose projects
- `compose/_templates/` — reference templates
- `config/` — versioned service configuration
- `examples/` — infrastructure validation fixtures
- `.github/workflows/` — CI workflows
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

GitHub/GHCR non-secret configuration:

```text
/home/alex/config.env
```

Registry authentication:

```text
/opt/data/docker-auth/config.json
```

The registry credential file is runtime-only and must never be committed.

## Production commands

```bash
/opt/ops/scripts/app-deploy.sh APP IMAGE@sha256:DIGEST
/opt/ops/scripts/app-rollback.sh APP
/opt/ops/scripts/app-status.sh APP
/opt/ops/scripts/app-health.sh APP
/opt/ops/scripts/app-compose.sh APP logs --tail=100 SERVICE
/opt/ops/scripts/registry-login.sh
```

## CI supply chain

The repository contains a CI smoke image used to validate the image supply chain:

```text
examples/ci-smoke/
.github/workflows/container-ci.yml
```

The CI contract is:

```text
source commit
  -> build
  -> vulnerability scan
  -> GHCR publish
  -> SBOM + provenance
  -> exact image digest
```

Production never builds application source code.

Production deploy accepts only:

```text
registry/repository@sha256:<digest>
```

Mutable tags such as `latest`, `main` or `sha-<commit>` may be used for registry discovery but are never passed to `app-deploy.sh`.

GitHub Actions does not receive VPS SSH credentials in this iteration. Deployment remains an explicit server-side operation through the production deploy contract.
EOF_OPS_README
````

Проверить:

```bash
sed -n '1,300p' "$OPS_ROOT/README.md"
```

---

## 27. Выполнить финальные static checks

Bash:

```bash
(
  cd "$OPS_ROOT/scripts"

  bash -n \
    chapter-06-configure.sh \
    app-deploy.sh \
    app-rollback.sh \
    app-health.sh \
    app-status.sh \
    app-compose.sh \
    caddy-add-site.sh \
    caddy-remove-site.sh \
    registry-login.sh \
    lib/app-common.sh
)
```

ShellCheck:

```bash
(
  cd "$OPS_ROOT/scripts"

  shellcheck -x \
    chapter-06-configure.sh \
    app-deploy.sh \
    app-rollback.sh \
    app-health.sh \
    app-status.sh \
    app-compose.sh \
    caddy-add-site.sh \
    caddy-remove-site.sh \
    registry-login.sh \
    lib/app-common.sh
)
```

Workflow:

```bash
python3 - "$OPS_ROOT/.github/workflows/container-ci.yml" <<'PY_FINAL_WORKFLOW'
import re
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
data = yaml.safe_load(text)

if not isinstance(data, dict):
    raise SystemExit("ERROR: invalid workflow root")

if "\t" in text:
    raise SystemExit("ERROR: TAB found in workflow")

uses = re.findall(r"(?m)^[ \t]*uses:[ \t]*([^ \t#]+)", text)

for value in uses:
    if value.startswith("./"):
        continue

    _, ref = value.rsplit("@", 1)

    if not re.fullmatch(r"[a-f0-9]{40}", ref):
        raise SystemExit(f"ERROR: mutable action reference: {value}")

print("Workflow YAML and action pins are valid.")
PY_FINAL_WORKFLOW
```

Dockerfile:

```bash
docker buildx build \
  --check \
  "$OPS_ROOT/examples/ci-smoke"
```

---

## 28. Финальная runtime проверка

```bash
source "$HOME/config.env"
```

App:

```bash
"$OPS_ROOT/scripts/app-status.sh" "$DEPLOY_TEST_STACK"
"$OPS_ROOT/scripts/app-health.sh" "$DEPLOY_TEST_STACK" 3
```

Public health:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  "https://${DEPLOY_TEST_DOMAIN}/health" |
grep -Fx 'deploy-test-ok'
```

Caddy:

```bash
cd "$OPS_ROOT/compose/edge"

docker compose ps

docker compose exec -T caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Containers:

```bash
docker ps --format \
  'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

Listeners и systemd:

```bash
sudo ss -lntup | grep -E ':(80|443)\b'
sudo systemctl --failed
```

Registry config:

```bash
stat -c '%A %U:%G %n' \
  "$REGISTRY_DOCKER_CONFIG" \
  "$REGISTRY_DOCKER_CONFIG/config.json"
```

---

## 29. Git-фиксация после runtime validation

```bash
git -C "$OPS_ROOT" status --short
```

Добавить явно только README:

```bash
git -C "$OPS_ROOT" add README.md
```

Проверки:

```bash
git -C "$OPS_ROOT" diff --cached --stat
git -C "$OPS_ROOT" diff --cached --check
git -C "$OPS_ROOT" diff --cached --name-status
```

Проверка staged файлов не считает deletion ошибкой:

```bash
if git -C "$OPS_ROOT" \
    diff --cached --diff-filter=ACMR --name-only |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|.*\.bak(?:\..*)?|config\.json)$'; then
  printf 'ERROR: runtime, credential or backup file is staged\n' >&2
  exit 1
fi
```

Commit:

```bash
git -C "$OPS_ROOT" commit \
  -m 'Document immutable container CI contract'
```

Push:

```bash
git -C "$OPS_ROOT" push origin main
```

Второй commit меняет только `README.md`, поэтому `container-ci` повторно запускаться не должен: workflow ограничен `paths` для `examples/ci-smoke/**` и самого workflow.

---

## 30. Проверить чистоту репозитория и секретов

```bash
git -C "$OPS_ROOT" status --short
```

Должно быть пусто.

Проверить tracked suspicious filenames:

```bash
if git -C "$OPS_ROOT" ls-files |
  grep -E \
    '(^|/)(\.env|current\.env|previous\.env|history\.tsv|deploy\.lock|config\.json|.*\.bak(?:\..*)?)$'; then
  printf 'ERROR: suspicious runtime/credential/backup file is tracked\n' >&2
  exit 1
fi
```

Проверить backups:

```bash
find "$OPS_ROOT" \
  -type f \
  \( -name '*.bak' -o -name '*.bak.*' \) \
  -print
```

Ожидается пустой вывод.

Последние commits:

```bash
git -C "$OPS_ROOT" log -3 --oneline
```

---

## 31. Критерии завершения главы

Глава 06 считается завершённой только когда одновременно выполняются все условия:

1. Глава 05 по-прежнему проходит production health-check.
2. Создан отдельный private GitHub repository без посторонней initial history.
3. VPS использует отдельный Ed25519 Deploy Key, ограниченный этим repository.
4. `origin` `/opt/ops` указывает на правильный GitHub repository и `origin/main` совпадает с локальным `main`.
5. `GITHUB_OWNER`, `OPS_REPO_NAME`, `GITHUB_REMOTE`, `GITHUB_SSH_KEY`, `REGISTRY_HOST`, `REGISTRY_OWNER`, `REGISTRY_USERNAME`, `REGISTRY_DOCKER_CONFIG`, `CI_SMOKE_IMAGE` и deployment defaults находятся в едином `/home/alex/config.env`.
6. Registry PAT отсутствует в `$HOME/config.env` и Git; private GitHub Deploy Key находится только в `$HOME/.ssh/github_ops_ed25519`.
7. `/opt/data/docker-auth/config.json` имеет права `0600`.
8. `app-common.sh` экспортирует `DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"`.
9. `chapter-06-configure.sh` и `registry-login.sh` проходят `bash -n` и ShellCheck.
10. `examples/ci-smoke` локально собирается и проходит health-check.
11. Workflow корректно парсится как YAML.
12. Все external `uses:` pinned на полный 40-character commit SHA.
13. Workflow не содержит SSH/VPS credentials.
14. GitHub Actions build успешен.
15. Vulnerability scan выполняется до publish.
16. GHCR image публикуется с tag `sha-<full-git-sha>`.
17. Buildx выдаёт точный `sha256` digest.
18. Registry publish содержит SBOM и provenance attestations.
19. VPS authenticates к private GHCR под `REGISTRY_USERNAME`.
20. VPS успешно pull'ит image.
21. `app-deploy.sh` отвергает mutable tag.
22. `app-deploy.sh` успешно принимает GHCR `IMAGE@sha256:DIGEST`.
23. Публичный `/health` после GHCR deploy возвращает `deploy-test-ok`.
24. Rollback после GHCR deploy успешен.
25. Caddy остаётся healthy.
26. `systemctl --failed` пуст.
27. Runtime/credential/backup-файлы не tracked в Git.
28. `git status --short` пуст.
29. Оба commit главы 06 отправлены в `origin/main`.

---

## 32. Диагностика типовых ошибок

### `git ls-remote origin` возвращает `Permission denied (publickey)`

Проверить remote и repo-local SSH command:

```bash
git -C "$OPS_ROOT" remote -v
git -C "$OPS_ROOT" config --get core.sshCommand

stat -c '%A %U:%G %n' \
  "$HOME/.ssh/github_ops_ed25519" \
  "$HOME/.ssh/github_ops_ed25519.pub" \
  "$HOME/.ssh/known_hosts"
```

Проверить, что public key из:

```bash
cat "$HOME/.ssh/github_ops_ed25519.pub"
```

добавлен именно в:

```text
Repository -> Settings -> Deploy keys
```

и что включён `Allow write access`.

Не заменять Deploy Key на PAT в Git remote URL.

---

### Первый `git push -u origin main` отклонён как non-fast-forward

Remote repository должен был быть создан пустым.

Проверить remote refs:

```bash
git -C "$OPS_ROOT" ls-remote --heads origin
```

Если repository был случайно инициализирован README/license/.gitignore через GitHub UI, не выполнять `git push --force` вслепую. Для новой главы проще удалить ошибочно созданный пустой GitHub repository, создать его заново без initialization и повторить шаги 5–6.

---

### `REGISTRY_OWNER=` снова пустой

Проверить единый config:

```bash
grep -E '^export REGISTRY_(HOST|OWNER|USERNAME)=' \
  "$HOME/config.env"
```

Повторно построить managed-блок главы 06:

```bash
source "$HOME/config.env"

: "${REGISTRY_USERNAME:?REGISTRY_USERNAME is not set}"

"$OPS_ROOT/scripts/chapter-06-configure.sh" "$REGISTRY_USERNAME"

source "$HOME/config.env"

printf '%s\n' \
  "REGISTRY_HOST=$REGISTRY_HOST" \
  "REGISTRY_OWNER=$REGISTRY_OWNER" \
  "REGISTRY_USERNAME=$REGISTRY_USERNAME"
```

---
### `denied: permission_denied` или HTTP 403 при GitHub Actions push

Проверить:

```yaml
permissions:
  contents: read
  packages: write
```

Если package существовал раньше и не связан с repository — проверить package settings и repository access.

Не заменять `GITHUB_TOKEN` на постоянный write PAT без необходимости.

---

### VPS получает `unauthorized` при `docker pull`

```bash
source "$HOME/config.env"
export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"

"$OPS_ROOT/scripts/registry-login.sh"
```

PAT должен иметь `read:packages`. `REGISTRY_USERNAME` должен быть login владельца этого PAT, а GitHub account должен иметь read access к private package.

---

### `app-deploy.sh` не видит registry login

```bash
grep -n 'DOCKER_CONFIG' \
  "$OPS_ROOT/scripts/lib/app-common.sh"

source "$HOME/config.env"

stat "$REGISTRY_DOCKER_CONFIG/config.json"
```

В `app-common.sh` должен быть:

```bash
export DOCKER_CONFIG="$REGISTRY_DOCKER_CONFIG"
```

---

### GitHub workflow публикует image, но digest не найден

Workflow читает `containerimage.digest` из Buildx `--metadata-file`.

Digest должен иметь форму:

```text
sha256:<64 lowercase hex characters>
```

---

### Trivy блокирует workflow

В этой главе:

- `HIGH` и `CRITICAL` выводятся в отчёте;
- workflow блокируется на fixable `HIGH` и `CRITICAL`, потому что gate использует `--ignore-unfixed`.

Не отключать scan ради зелёного workflow. Обновить base image digest и повторить build.

---

### `docker buildx build --check` не поддерживается

```bash
docker buildx version
```

Не обходить validation. Обновление Docker/Buildx выполнять отдельно и только потом продолжать главу.

---

### Git снова ругается на удаляемый backup

Правильная проверка:

```bash
git diff --cached --diff-filter=ACMR --name-only
```

`D` намеренно отсутствует:

- добавление backup запрещено;
- modification backup запрещена;
- удаление старого tracked backup разрешено.

---

### README-only commit запускает `container-ci`

Не должен.

Workflow `paths` ограничен:

```text
examples/ci-smoke/**
.github/workflows/container-ci.yml
```

Проверить фактический diff commit.

---

## 33. Что намеренно не входит в итерацию 06

Глава не добавляет:

- GitHub-hosted runner в tailnet;
- Tailscale workload identity/OAuth credentials в GitHub;
- SSH private key в GitHub Secrets;
- автоматический production deploy после push;
- GitHub Environment `production`;
- required reviewers production;
- remote rollback из Actions;
- self-hosted runner на VPS.

Граница после итерации:

```text
CI owns:
source -> build -> scan -> publish -> digest

VPS owns:
digest -> deploy -> health -> rollback
```

Это намеренная граница безопасности: compromise CI workflow не должен автоматически означать немедленный production deploy.

---

## 34. Актуальные технические ориентиры

При подготовке главы использованы актуальные на 2026-08-07 механизмы:

- GitHub Container Registry (`ghcr.io`);
- job-scoped `GITHUB_TOKEN` с `packages: write` для publish;
- PAT classic с `read:packages` для private package pull вне GitHub Actions;
- Docker Buildx `--metadata-file` для `containerimage.digest`;
- BuildKit SBOM через `--sbom=true`;
- BuildKit provenance через `--provenance=mode=max`;
- BuildKit `v0.30.0` builder image, pinned на exact Docker Hub multi-platform index digest;
- BusyBox `1.38.0` official image, pinned на exact Docker Hub multi-platform index digest;
- Trivy `0.72.0` official container, pinned на exact Docker Hub index digest, для vulnerability scan;
- полный immutable commit SHA `3d3c42e5aac5ba805825da76410c181273ba90b1` для `actions/checkout` v7.0.1.

Справочная документация:

```text
https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images
https://docs.github.com/en/actions/reference/security/secure-use
https://docs.docker.com/build/metadata/attestations/
https://docs.docker.com/build/ci/github-actions/attestations/
https://docs.docker.com/reference/cli/docker/buildx/build/
https://docs.docker.com/build/builders/drivers/docker-container/
https://hub.docker.com/r/moby/buildkit/tags
https://hub.docker.com/_/busybox
https://hub.docker.com/r/aquasec/trivy/tags
https://trivy.dev/docs/latest/ecosystem/cicd/
```

Перед будущим обновлением action/tool versions проверять текущие official release notes, а не копировать старые version tags из этой главы вслепую.
