# Глава 1. Первоначальная настройка Ubuntu VPS

> **Цель:** подготовить Ubuntu Server 24.04 для дальнейшего размещения Docker-сервисов: создать администратора, настроить SSH по ключу, firewall, обновления, swap, рабочую оболочку и единую постоянную конфигурацию для всех четырёх глав.

> **Результат:** параметры настройки сохраняются на Windows и Linux и автоматически загружаются после перезапуска PowerShell, SSH или Zsh. Каталоги `/opt` имеют предсказуемые права, а сервер готов к установке Docker.

---

## 1. Общая схема настройки

В инструкциях используются два постоянных конфигурационных файла:

```text
Windows: %USERPROFILE%\.config\vps-guide\config.ps1
Linux:   /etc/vps-guide/config.env
```

Они содержат только несекретные параметры: адрес сервера, имя пользователя, домены, пути, порты и лимиты. Пароли, приватные SSH-ключи, API-токены и другие секреты в эти файлы не записываются.

Все изменяемые пользователем значения задаются один раз в Windows-файле. Из него автоматически создаётся Linux env-файл для глав 1–4.

---

## 2. Создать постоянную конфигурацию на Windows

Откройте обычный PowerShell и создайте каталог:

```powershell
$GuideConfigDir = Join-Path $HOME ".config\vps-guide"
$GuideConfigPath = Join-Path $GuideConfigDir "config.ps1"

New-Item -ItemType Directory -Force -Path $GuideConfigDir | Out-Null
notepad $GuideConfigPath
```

Вставьте в открывшийся файл следующий код. Измените только блок `USER SETTINGS` в начале.

```powershell
# =============================================================================
# USER SETTINGS — измените только этот блок
# =============================================================================

$Global:VpsConfig = [ordered]@{
    ServerIp       = "CHANGE_ME_PUBLIC_IPV4"
    AdminUser      = "deploy"
    ServerHostname = "prod-vps-01"
    SshAlias       = "vps"
    Timezone       = "UTC"
    BaseDomain     = "CHANGE_ME_DOMAIN"
    AcmeEmail      = "CHANGE_ME_EMAIL"
    SshKeyName     = "vps_prod_ed25519"
}

# =============================================================================
# DEFAULTS — обычно менять не требуется
# =============================================================================

$VpsConfig["SshPort"]                  = 22
$VpsConfig["SwapSize"]                 = "4G"
$VpsConfig["OpsGroup"]                 = "ops"

$VpsConfig["OpsRoot"]                  = "/opt/ops"
$VpsConfig["AppsRoot"]                 = "/opt/apps"
$VpsConfig["DataRoot"]                 = "/opt/data"
$VpsConfig["BackupsRoot"]              = "/opt/backups"

$VpsConfig["EdgeNetwork"]              = "edge"
$VpsConfig["ObservabilityNetwork"]     = "observability"
$VpsConfig["DockerLogMaxSize"]         = "20m"
$VpsConfig["DockerLogMaxFile"]         = "5"
$VpsConfig["DockerDefaultBindIp"]      = "127.0.0.1"
$VpsConfig["SmokeStack"]               = "docker-smoke"
$VpsConfig["SmokePort"]                = 18080

$VpsConfig["TailscaleHostname"]        = $VpsConfig.ServerHostname
$VpsConfig["TailscaleUdpPort"]         = 41641
$VpsConfig["TailscalePolicySource"]    = "autogroup:admin"

$VpsConfig["EdgeTestDomain"]           = "edge-test.$($VpsConfig.BaseDomain)"
$VpsConfig["CaddyStack"]               = "edge"
$VpsConfig["CaddyImage"]               = "caddy:2.11.4-alpine"
$VpsConfig["CaddyBindIpv4"]            = "0.0.0.0"
$VpsConfig["CaddyMemoryLimit"]         = "256m"
$VpsConfig["CaddyCpuLimit"]            = "0.50"
$VpsConfig["EdgeTestStack"]            = "edge-test"
$VpsConfig["EdgeTestImage"]            = "nginx:alpine"
$VpsConfig["EdgeTestUpstream"]         = "edge-test-web:8080"

# =============================================================================
# DERIVED PATHS AND FUNCTIONS
# =============================================================================

$Global:VpsGuideConfigDir = Join-Path $HOME ".config\vps-guide"
$Global:VpsGuideConfigPath = Join-Path $VpsGuideConfigDir "config.ps1"
$Global:VpsGuideLinuxEnvPath = Join-Path $VpsGuideConfigDir "server.env"
$Global:VpsGuideSshDir = Join-Path $HOME ".ssh"
$Global:VpsGuidePrivateKey = Join-Path $VpsGuideSshDir $VpsConfig.SshKeyName
$Global:VpsGuidePublicKey = "$VpsGuidePrivateKey.pub"

function Assert-VpsGuideConfig {
    $required = @(
        "ServerIp",
        "AdminUser",
        "ServerHostname",
        "SshAlias",
        "Timezone",
        "BaseDomain",
        "AcmeEmail",
        "SshKeyName"
    )

    foreach ($name in $required) {
        $value = [string]$VpsConfig[$name]
        if ([string]::IsNullOrWhiteSpace($value) -or $value -like "CHANGE_ME*") {
            throw "Заполните VpsConfig.$name в $VpsGuideConfigPath"
        }
    }

    $parsedIp = $null
    if (-not [System.Net.IPAddress]::TryParse($VpsConfig.ServerIp, [ref]$parsedIp) -or
        $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw "ServerIp должен быть корректным публичным IPv4: $($VpsConfig.ServerIp)"
    }

    if ($VpsConfig.AdminUser -notmatch '^[a-z_][a-z0-9_-]*$') {
        throw "Некорректный AdminUser: $($VpsConfig.AdminUser)"
    }

    if ($VpsConfig.ServerHostname -notmatch '^[a-z0-9][a-z0-9.-]*$') {
        throw "Некорректный ServerHostname: $($VpsConfig.ServerHostname)"
    }

    if ($VpsConfig.SshAlias -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "Некорректный SshAlias: $($VpsConfig.SshAlias)"
    }

    if ($VpsConfig.BaseDomain -notmatch '\.' -or
        [System.Uri]::CheckHostName($VpsConfig.BaseDomain) -ne [System.UriHostNameType]::Dns) {
        throw "Некорректный BaseDomain: $($VpsConfig.BaseDomain)"
    }

    if ($VpsConfig.AcmeEmail -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') {
        throw "Некорректный AcmeEmail: $($VpsConfig.AcmeEmail)"
    }
}

function ConvertTo-BashSingleQuoted {
    param([Parameter(Mandatory)][string]$Value)
    $escapeSequence = ([string][char]39) + ([char]34) + ([char]39) + ([char]34) + ([char]39)
    return "'" + $Value.Replace("'", $escapeSequence) + "'"
}

function Export-VpsGuideLinuxEnv {
    Assert-VpsGuideConfig

    $linux = [ordered]@{
        SERVER_PUBLIC_IPV4       = [string]$VpsConfig.ServerIp
        ADMIN_USER              = [string]$VpsConfig.AdminUser
        SERVER_HOSTNAME         = [string]$VpsConfig.ServerHostname
        SSH_ALIAS               = [string]$VpsConfig.SshAlias
        SSH_PORT                = [string]$VpsConfig.SshPort
        TIMEZONE                = [string]$VpsConfig.Timezone
        SWAP_SIZE               = [string]$VpsConfig.SwapSize
        OPS_GROUP               = [string]$VpsConfig.OpsGroup

        OPS_ROOT                = [string]$VpsConfig.OpsRoot
        APPS_ROOT               = [string]$VpsConfig.AppsRoot
        DATA_ROOT               = [string]$VpsConfig.DataRoot
        BACKUPS_ROOT            = [string]$VpsConfig.BackupsRoot

        EDGE_NETWORK            = [string]$VpsConfig.EdgeNetwork
        OBSERVABILITY_NETWORK   = [string]$VpsConfig.ObservabilityNetwork
        DOCKER_LOG_MAX_SIZE     = [string]$VpsConfig.DockerLogMaxSize
        DOCKER_LOG_MAX_FILE     = [string]$VpsConfig.DockerLogMaxFile
        DOCKER_DEFAULT_BIND_IP  = [string]$VpsConfig.DockerDefaultBindIp
        SMOKE_STACK             = [string]$VpsConfig.SmokeStack
        SMOKE_PORT              = [string]$VpsConfig.SmokePort

        TAILSCALE_HOSTNAME      = [string]$VpsConfig.TailscaleHostname
        TAILSCALE_UDP_PORT      = [string]$VpsConfig.TailscaleUdpPort
        TAILSCALE_POLICY_SOURCE = [string]$VpsConfig.TailscalePolicySource

        BASE_DOMAIN             = ([string]$VpsConfig.BaseDomain).ToLowerInvariant()
        EDGE_TEST_DOMAIN        = ([string]$VpsConfig.EdgeTestDomain).ToLowerInvariant()
        CADDY_ACME_EMAIL        = [string]$VpsConfig.AcmeEmail
        CADDY_STACK             = [string]$VpsConfig.CaddyStack
        CADDY_IMAGE             = [string]$VpsConfig.CaddyImage
        CADDY_BIND_IPV4         = [string]$VpsConfig.CaddyBindIpv4
        CADDY_MEMORY_LIMIT      = [string]$VpsConfig.CaddyMemoryLimit
        CADDY_CPU_LIMIT         = [string]$VpsConfig.CaddyCpuLimit
        EDGE_TEST_STACK         = [string]$VpsConfig.EdgeTestStack
        EDGE_TEST_IMAGE         = [string]$VpsConfig.EdgeTestImage
        EDGE_TEST_UPSTREAM      = [string]$VpsConfig.EdgeTestUpstream
    }

    $lines = @(
        "# Generated from Windows: $VpsGuideConfigPath",
        "# Contains no passwords, private keys or API tokens."
    )

    foreach ($entry in $linux.GetEnumerator()) {
        $lines += "export $($entry.Key)=$(ConvertTo-BashSingleQuoted -Value $entry.Value)"
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $content = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($VpsGuideLinuxEnvPath, $content, $utf8NoBom)

    Write-Host "Создан Linux env с LF-окончаниями строк: $VpsGuideLinuxEnvPath"
}

function Install-VpsGuidePowerShellProfile {
    $profilePath = $PROFILE.CurrentUserAllHosts
    $profileDir = Split-Path -Parent $profilePath
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

    $loader = ". `"$VpsGuideConfigPath`""
    if (-not (Test-Path $profilePath) -or
        -not (Select-String -Path $profilePath -SimpleMatch $loader -Quiet)) {
        Add-Content -Path $profilePath -Value "`r`n# VPS guide configuration`r`n$loader`r`n"
    }

    Write-Host "PowerShell будет загружать конфигурацию автоматически."
}

function Set-VpsGuideSshConfig {
    param(
        [Parameter(Mandatory)][string]$PrimaryHost
    )

    Assert-VpsGuideConfig
    New-Item -ItemType Directory -Force -Path $VpsGuideSshDir | Out-Null

    $configPath = Join-Path $VpsGuideSshDir "config"
    $identity = $VpsGuidePrivateKey.Replace("\", "/")
    $begin = "# BEGIN VPS-GUIDE $($VpsConfig.SshAlias)"
    $end = "# END VPS-GUIDE $($VpsConfig.SshAlias)"

    $block = @"
$begin
Host $($VpsConfig.SshAlias)
    HostName $PrimaryHost
    User $($VpsConfig.AdminUser)
    Port $($VpsConfig.SshPort)
    IdentityFile "$identity"
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host $($VpsConfig.SshAlias)-public
    HostName $($VpsConfig.ServerIp)
    User $($VpsConfig.AdminUser)
    Port $($VpsConfig.SshPort)
    IdentityFile "$identity"
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
$end
"@

    $existing = if (Test-Path $configPath) {
        Get-Content -Raw -Path $configPath
    } else {
        ""
    }

    $pattern = "(?ms)^$([regex]::Escape($begin))\r?\n.*?^$([regex]::Escape($end))\r?\n?"
    if ([regex]::IsMatch($existing, $pattern)) {
        $updated = [regex]::Replace($existing, $pattern, "$block`r`n")
    } else {
        $updated = $existing.TrimEnd() + "`r`n`r`n$block`r`n"
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configPath, $updated, $utf8NoBom)
    Write-Host "Обновлён SSH config: $configPath"
}

Assert-VpsGuideConfig
```

Сохраните файл и выполните:

```powershell
. $GuideConfigPath
Install-VpsGuidePowerShellProfile
Export-VpsGuideLinuxEnv
```

После этого конфигурация будет автоматически загружаться в новых окнах PowerShell.

---

## 3. Подготовить SSH-ключ на Windows

Проверить OpenSSH:

```powershell
Get-Command ssh
ssh -V
```

Если клиент отсутствует, откройте PowerShell от имени администратора:

```powershell
Add-WindowsCapability -Online -Name "OpenSSH.Client~~~~0.0.1.0"
```

Создать отдельный ключ:

```powershell
New-Item -ItemType Directory -Force -Path $VpsGuideSshDir | Out-Null

if (-not (Test-Path $VpsGuidePrivateKey)) {
    ssh-keygen `
        -t ed25519 `
        -a 100 `
        -f $VpsGuidePrivateKey `
        -C "$env:USERNAME@$env:COMPUTERNAME:$($VpsConfig.SshAlias)"
}
```

Укажите надёжную passphrase. Приватный файл без расширения `.pub` не копируется на сервер и не передаётся другим людям.

Подключить ключ к `ssh-agent`. Первый блок выполняется в PowerShell от имени администратора:

```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```

Затем в обычном PowerShell:

```powershell
ssh-add $VpsGuidePrivateKey
ssh-add -l
```

---

## 4. Передать общую конфигурацию на VPS

Сгенерировать актуальный Linux env и скопировать его на сервер:

```powershell
Export-VpsGuideLinuxEnv

scp `
    -P $VpsConfig.SshPort `
    $VpsGuideLinuxEnvPath `
    "root@$($VpsConfig.ServerIp):/tmp/vps-guide.env"
```

Подключиться под `root`:

```powershell
ssh -p $VpsConfig.SshPort "root@$($VpsConfig.ServerIp)"
```

Не закрывайте эту сессию, пока вход новым пользователем по ключу не будет проверен в отдельном окне.

---

## 5. Установить постоянную конфигурацию на Linux

В root-сессии:

```bash
install -d -o root -g root -m 0755 /etc/vps-guide
install -o root -g root -m 0644 /tmp/vps-guide.env /etc/vps-guide/config.env
rm -f /tmp/vps-guide.env

cat > /etc/profile.d/vps-guide.sh <<'EOF_PROFILE'
if [ -r /etc/vps-guide/config.env ]; then
  . /etc/vps-guide/config.env
fi
EOF_PROFILE

chmod 0644 /etc/profile.d/vps-guide.sh
. /etc/vps-guide/config.env
```

Файл принадлежит `root` и недоступен для случайной перезаписи обычным пользователем. Все последующие служебные скрипты явно загружают его перед использованием переменных.

---

## 6. Настроить имя сервера и время

```bash
hostnamectl set-hostname "$SERVER_HOSTNAME"
timedatectl set-timezone "$TIMEZONE"
timedatectl set-ntp true

if grep -qE '^127\.0\.1\.1[[:space:]]+' /etc/hosts; then
  sed -i -E "s/^127\.0\.1\.1[[:space:]]+.*/127.0.1.1 ${SERVER_HOSTNAME}/" /etc/hosts
else
  printf '127.0.1.1 %s\n' "$SERVER_HOSTNAME" >> /etc/hosts
fi
```

---

## 7. Обновить систему и установить базовые пакеты

```bash
apt update
apt full-upgrade -y

apt install -y \
  acl \
  ca-certificates \
  curl \
  etckeeper \
  fail2ban \
  git \
  gnupg \
  htop \
  jq \
  lsof \
  nano \
  openssh-server \
  ripgrep \
  rsync \
  tmux \
  unattended-upgrades \
  unzip \
  vim \
  zsh \
  zsh-autosuggestions \
  zsh-syntax-highlighting
```

---

## 8. Создать администратора и группу эксплуатации

```bash
getent group "$OPS_GROUP" >/dev/null || groupadd "$OPS_GROUP"

if ! id "$ADMIN_USER" >/dev/null 2>&1; then
  adduser --gecos "" "$ADMIN_USER"
fi

usermod -aG sudo,"$OPS_GROUP" "$ADMIN_USER"
```

Создать структуру `/opt` с setgid-битом. Новые файлы будут наследовать группу `ops`:

```bash
install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT" \
  "$APPS_ROOT"

install -d -o root -g "$OPS_GROUP" -m 2770 \
  "$DATA_ROOT" \
  "$BACKUPS_ROOT"

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2770 \
  "$OPS_ROOT/secrets"

install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT/compose" \
  "$OPS_ROOT/config" \
  "$OPS_ROOT/docs" \
  "$OPS_ROOT/scripts"

find "$OPS_ROOT" "$APPS_ROOT" -type d -exec \
  setfacl -m g:"$OPS_GROUP":rwx,d:g:"$OPS_GROUP":rwx,o::rx,d:o::rx {} +

find "$DATA_ROOT" "$BACKUPS_ROOT" -type d -exec \
  setfacl -m g:"$OPS_GROUP":rwx,d:g:"$OPS_GROUP":rwx,o::---,d:o::--- {} +

setfacl -m g:"$OPS_GROUP":rwx,d:g:"$OPS_GROUP":rwx,o::---,d:o::--- \
  "$OPS_ROOT/secrets"
```

Эта схема предотвращает появление случайных root-only каталогов внутри `/opt/ops`, но конфигурации, которые должны читаться контейнерами, позднее всё равно получают явные права `0755/0644`.

---

## 9. Установить SSH-ключ администратору

На Windows в новом PowerShell:

```powershell
scp `
    -P $VpsConfig.SshPort `
    $VpsGuidePublicKey `
    "root@$($VpsConfig.ServerIp):/tmp/admin_authorized_key.pub"
```

В root-сессии:

```bash
ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"

install -d -o "$ADMIN_USER" -g "$ADMIN_USER" -m 0700 "$ADMIN_HOME/.ssh"
install -o "$ADMIN_USER" -g "$ADMIN_USER" -m 0600 \
  /tmp/admin_authorized_key.pub \
  "$ADMIN_HOME/.ssh/authorized_keys"
rm -f /tmp/admin_authorized_key.pub
```

Создать автоматическую загрузку Linux-конфигурации для Bash и Zsh:

```bash
install -d -o "$ADMIN_USER" -g "$ADMIN_USER" -m 0700 "$ADMIN_HOME/.config/vps-guide"

cat > "$ADMIN_HOME/.config/vps-guide/load-env.sh" <<'EOF_LOADER'
if [ -r /etc/vps-guide/config.env ]; then
  . /etc/vps-guide/config.env
fi
EOF_LOADER

chown "$ADMIN_USER:$ADMIN_USER" "$ADMIN_HOME/.config/vps-guide/load-env.sh"
chmod 0600 "$ADMIN_HOME/.config/vps-guide/load-env.sh"

for rc_file in "$ADMIN_HOME/.bashrc" "$ADMIN_HOME/.zshrc"; do
  touch "$rc_file"
  if ! grep -Fq '. "$HOME/.config/vps-guide/load-env.sh"' "$rc_file"; then
    cat >> "$rc_file" <<'EOF_RC'

# VPS guide environment
if [ -r "$HOME/.config/vps-guide/load-env.sh" ]; then
  . "$HOME/.config/vps-guide/load-env.sh"
fi
EOF_RC
  fi
  chown "$ADMIN_USER:$ADMIN_USER" "$rc_file"
done
```

На Windows создать SSH alias, пока направленный на публичный IP:

```powershell
Set-VpsGuideSshConfig -PrimaryHost $VpsConfig.ServerIp
ssh $VpsConfig.SshAlias
```

В новом сеансе проверить `sudo`:

```bash
sudo -v
sudo whoami
```

Ожидаемый результат последней команды: `root`.

---

## 10. Усилить SSH

Вернитесь в первоначальную root-сессию и создайте drop-in:

```bash
cat > /etc/ssh/sshd_config.d/60-vps-hardening.conf <<EOF_SSHD
Port ${SSH_PORT}
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
PermitEmptyPasswords no
X11Forwarding no
AllowUsers ${ADMIN_USER}
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 4
LoginGraceTime 30
EOF_SSHD

sshd -t
systemctl reload ssh.service
```

Откройте ещё одно окно PowerShell и повторно выполните:

```powershell
ssh $VpsConfig.SshAlias
```

Закрывать root-сессию можно только после успешного повторного входа и команды `sudo -v`.

---

## 11. Настроить UFW

До установки Tailscale SSH временно разрешается на публичном интерфейсе:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp" comment 'Temporary public SSH'
ufw --force enable
```

Глава 3 добавит правило только для `tailscale0` и удалит временное публичное правило.

---

## 12. Настроить Fail2ban

```bash
cat > /etc/fail2ban/jail.d/sshd.local <<EOF_FAIL2BAN
[DEFAULT]
banaction = ufw
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ${SSH_PORT}
backend = systemd
EOF_FAIL2BAN

fail2ban-client -t
systemctl enable --now fail2ban.service
```

---

## 13. Автоматические security-обновления

```bash
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF_AUTO_UPGRADES'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF_AUTO_UPGRADES

cat > /etc/apt/apt.conf.d/52unattended-upgrades-local <<'EOF_UNATTENDED'
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::SyslogEnable "true";
EOF_UNATTENDED

systemctl enable --now unattended-upgrades.service
```

Автоматическая перезагрузка оставлена выключенной: сервер перезагружается вручную после проверки сервисов.

---

## 14. Настроить swap

```bash
if [ -z "$(swapon --show --noheadings)" ]; then
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 0600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -qE '^/swapfile[[:space:]]' /etc/fstab || \
    printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi

cat > /etc/sysctl.d/60-vps-memory.conf <<'EOF_MEMORY'
vm.swappiness = 10
vm.vfs_cache_pressure = 50
EOF_MEMORY

sysctl --system
```

---

## 15. Настроить Zsh и tmux

Создать предсказуемый `.zshrc`. Конструкция `${VIRTUAL_ENV-}` безопасна даже при включённом `nounset` внутри отдельных скриптов:

```bash
ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"

cat > "$ADMIN_HOME/.zshrc" <<'EOF_ZSHRC'
HISTFILE="$HOME/.zsh_history"
HISTSIZE=20000
SAVEHIST=20000

setopt APPEND_HISTORY SHARE_HISTORY HIST_IGNORE_DUPS HIST_REDUCE_BLANKS
setopt INTERACTIVE_COMMENTS AUTO_CD AUTO_PUSHD PUSHD_IGNORE_DUPS
bindkey -e

autoload -Uz compinit colors vcs_info
compinit -d "$HOME/.zcompdump"
colors
zstyle ':vcs_info:git:*' formats '%F{yellow}git:(%b)%f'

precmd() { vcs_info }
virtualenv_info() {
  if [[ -n "${VIRTUAL_ENV-}" ]]; then
    print -n "%F{magenta}venv:$(basename "$VIRTUAL_ENV")%f "
  fi
}

setopt PROMPT_SUBST
PROMPT='%F{cyan}%n@%m%f %F{blue}%~%f ${vcs_info_msg_0_} $(virtualenv_info)%(?.%F{green}❯%f.%F{red}❯%f) '
RPROMPT='%F{240}%D{%H:%M}%f'

export EDITOR="vim"
export VISUAL="vim"
export PAGER="less"
export LESS="-R -F -X"

if [[ -r "$HOME/.config/vps-guide/load-env.sh" ]]; then
  source "$HOME/.config/vps-guide/load-env.sh"
fi

source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
EOF_ZSHRC

cat > "$ADMIN_HOME/.tmux.conf" <<'EOF_TMUX'
set -g mouse on
set -g history-limit 50000
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g status-interval 5
set -g escape-time 10
bind r source-file ~/.tmux.conf \; display-message "tmux config reloaded"
EOF_TMUX

chown "$ADMIN_USER:$ADMIN_USER" "$ADMIN_HOME/.zshrc" "$ADMIN_HOME/.tmux.conf"
chmod 0600 "$ADMIN_HOME/.zshrc" "$ADMIN_HOME/.tmux.conf"
chsh -s /usr/bin/zsh "$ADMIN_USER"
```

Не выполняйте `set -Eeuo pipefail` непосредственно в интерактивном Zsh. Строгий режим используется только внутри файлов с `#!/usr/bin/env bash` или изолированных блоков `bash <<'BASH'`.

---

## 16. Включить etckeeper для `/etc`

`etckeeper` фиксирует изменения системной конфигурации в локальном Git-репозитории `/etc/.git`.

```bash
if [ ! -d /etc/.git ]; then
  etckeeper init
fi

git -C /etc config user.name 'etckeeper'
git -C /etc config user.email "root@${SERVER_HOSTNAME}"

if [ -n "$(git -C /etc status --porcelain)" ]; then
  etckeeper commit 'Initial VPS configuration'
fi
```

Не добавляйте удалённый публичный Git remote для `/etc`: в конфигурации могут появляться чувствительные данные.

---

## 17. Инициализировать Git-репозиторий инфраструктуры

```bash
sudo -u "$ADMIN_USER" git -C "$OPS_ROOT" init -b main
sudo -u "$ADMIN_USER" git -C "$OPS_ROOT" config user.name "$ADMIN_USER"
sudo -u "$ADMIN_USER" git -C "$OPS_ROOT" config user.email "$CADDY_ACME_EMAIL"

cat > "$OPS_ROOT/.gitignore" <<'EOF_GITIGNORE'
.env
*.env
*.key
*.pem
*.crt
*.p12
*.pfx
secrets/*
!secrets/.gitkeep
*.backup.*
EOF_GITIGNORE

cat > "$OPS_ROOT/README.md" <<'EOF_README'
# VPS operations repository

- `compose/` — Docker Compose stacks
- `config/` — versioned service configuration
- `scripts/` — operational scripts
- `docs/` — local documentation
- `secrets/` — never committed
EOF_README

touch "$OPS_ROOT/secrets/.gitkeep"
chown "$ADMIN_USER:$OPS_GROUP" "$OPS_ROOT/secrets/.gitkeep"
chmod 0664 "$OPS_ROOT/secrets/.gitkeep"

chown -R "$ADMIN_USER:$OPS_GROUP" "$OPS_ROOT"
chmod -R g+rwX "$OPS_ROOT"
find "$OPS_ROOT" -type d -exec chmod g+s {} +
```

---

## 18. Финальная перезагрузка

```bash
systemctl --failed
sshd -t
ufw status verbose
fail2ban-client status sshd
swapon --show

reboot
```

После перезагрузки на Windows:

```powershell
ssh $VpsConfig.SshAlias
```

На сервере переменные должны быть доступны без ручного `source`:

```bash
printf '%s\n' \
  "ADMIN_USER=$ADMIN_USER" \
  "OPS_ROOT=$OPS_ROOT" \
  "EDGE_NETWORK=$EDGE_NETWORK" \
  "BASE_DOMAIN=$BASE_DOMAIN"
```

---

# Диагностика и типичные проблемы

## A. Переменные пусты после нового SSH-сеанса

Проверить постоянный файл и loader:

```bash
ls -l /etc/vps-guide/config.env "$HOME/.config/vps-guide/load-env.sh"
. "$HOME/.config/vps-guide/load-env.sh"
```

Не создавайте отдельные `chapter-02.env`, `chapter-03.env` и `chapter-04.env`: единый `/etc/vps-guide/config.env` предотвращает расхождение и перезапись переменных пустыми значениями.

## B. Linux-конфигурация изменилась на Windows

После редактирования `config.ps1` загрузить файл через действующий SSH alias администратора:

```powershell
. $VpsGuideConfigPath
Export-VpsGuideLinuxEnv
scp $VpsGuideLinuxEnvPath "$($VpsConfig.SshAlias):/tmp/vps-guide.env"
ssh $VpsConfig.SshAlias
```

На сервере:

```bash
sudo install -o root -g root -m 0644 \
  /tmp/vps-guide.env \
  /etc/vps-guide/config.env
sudo rm -f /tmp/vps-guide.env
exec zsh
```

Изменение `ADMIN_USER`, `SSH_PORT` или hostname после завершения главы требует отдельной миграции и не должно выполняться простой заменой env-файла.

## C. `Permission denied` внутри `/opt/ops`

```bash
sudo chown -R root:"$OPS_GROUP" "$OPS_ROOT"
sudo chmod -R g+rwX "$OPS_ROOT"
sudo find "$OPS_ROOT" -type d -exec chmod g+s {} +
id -nG
```

Пользователь должен состоять в группе `ops`. После добавления в группу требуется новый SSH-сеанс.

## D. Невозможно выделить текст мышью в Windows Terminal

При включённой мыши в `tmux` используйте `Shift` + перетаскивание. Если терминал печатает escape-последовательности:

```bash
reset
printf '\033[?1000l\033[?1002l\033[?1003l\033[?1006l'
stty sane
```

Временно выключить мышь в tmux:

```bash
if [[ -n "${TMUX-}" ]]; then
  tmux set -g mouse off
fi
```

## E. Ошибки `POSTDISPLAY: parameter not set` или `VIRTUAL_ENV: parameter not set`

Они возникают, когда `set -u` включён в интерактивном Zsh. Перезапустить оболочку:

```bash
exec zsh
```

Строгий Bash-блок запускается так:

```bash
bash <<'BASH'
set -Eeuo pipefail
# команды
BASH
```

## F. Потерян SSH-доступ

Используйте web/serial/rescue console VPS-провайдера. Проверить:

```bash
sshd -t
systemctl status ssh.service --no-pager
ufw status numbered
cat /etc/ssh/sshd_config.d/60-vps-hardening.conf
```

Для временного восстановления публичного SSH:

```bash
ufw allow "${SSH_PORT}/tcp" comment 'Temporary SSH recovery'
systemctl reload ssh.service
```

После восстановления удалите временное правило.


## G. PowerShell не загружает `config.ps1`

Проверить политику выполнения:

```powershell
Get-ExecutionPolicy -List
```

Для локальных пользовательских скриптов обычно достаточно:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
. (Join-Path $HOME ".config\vps-guide\config.ps1")
```

Не используйте `Bypass` как постоянную системную политику.

---

## Официальная документация

- Ubuntu Server: https://documentation.ubuntu.com/server/
- OpenSSH: https://man.openbsd.org/sshd_config
- UFW: https://manpages.ubuntu.com/manpages/noble/en/man8/ufw.8.html
- Fail2ban: https://www.fail2ban.org/wiki/index.php/Main_Page
- unattended-upgrades: https://help.ubuntu.com/community/AutomaticSecurityUpdates
