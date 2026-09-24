# Глава 3. Tailscale и приватный административный доступ

> **Цель:** подключить VPS и Windows-компьютер к одному tailnet, перевести обычный OpenSSH на приватный маршрут Tailscale и закрыть публичный SSH.

> **Результат:** ежедневное подключение выполняется командой `ssh vps`; Tailscale автоматически запускается вместе с Windows; публичный SSH-порт закрыт, но доступна аварийная консоль VPS-провайдера.

---

## 1. Архитектура

```text
Windows PC
    │
    │ Tailscale / WireGuard
    ▼
tailscale0 на VPS
    │
    ├── OpenSSH по существующему ключу
    ├── будущие приватные admin endpoints
    └── SSH tunnels к сервисам на 127.0.0.1
```

Используется Tailscale на host, а не в Docker. Tailscale SSH остаётся выключенным: аутентификацию продолжает выполнять OpenSSH с ключом из главы 1.

Перед закрытием публичного SSH должны одновременно выполняться условия:

- доступна web/serial/rescue console VPS-провайдера;
- открыт рабочий SSH-сеанс через Tailscale;
- в нём успешно выполняется `sudo -v`;
- первоначальная публичная SSH-сессия остаётся открытой до финальной проверки.

---

## 2. Установить Tailscale на Ubuntu

Добавить официальный stable repository для Ubuntu 24.04:

```bash
sudo install -d -m 0755 /usr/share/keyrings

curl --fail --silent --show-error --location \
  https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
  | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null

curl --fail --silent --show-error --location \
  https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list \
  | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null

sudo apt update
sudo apt install -y tailscale
sudo systemctl enable --now tailscaled.service
```

Подключить VPS к tailnet:

```bash
sudo tailscale up \
  --hostname="$TAILSCALE_HOSTNAME" \
  --accept-dns=true \
  --operator="$ADMIN_USER"
```

Команда выведет URL. Откройте его в браузере и авторизуйте сервер в нужном Tailscale-аккаунте.

Явно оставить Tailscale SSH выключенным и назначить оператора:

```bash
sudo tailscale set --ssh=false
sudo tailscale set --operator="$ADMIN_USER"
```

Разрешить стандартный UDP-порт для повышения вероятности прямого соединения:

```bash
sudo ufw allow \
  "${TAILSCALE_UDP_PORT}/udp" \
  comment 'Tailscale direct WireGuard'
```

---

## 3. Установить Tailscale на Windows

Откройте PowerShell от имени администратора:

```powershell
winget install `
    --id Tailscale.Tailscale `
    --exact `
    --accept-package-agreements `
    --accept-source-agreements
```

Запустить службу автоматически и подключить компьютер в unattended mode:

```powershell
Set-Service -Name Tailscale -StartupType Automatic
Start-Service -Name Tailscale

tailscale up --unattended=true
```

Если откроется браузер, войдите в тот же Tailscale-аккаунт, где был зарегистрирован VPS.

Unattended mode позволяет клиенту работать после выхода пользователя и автоматически восстанавливаться после перезагрузки Windows.

---

## 4. Включить MagicDNS и проверить связность

В Tailscale Admin Console откройте раздел DNS и включите **MagicDNS**.

На Windows в новом PowerShell конфигурация главы 1 загрузится автоматически:

```powershell
tailscale status
tailscale ping $VpsConfig.TailscaleHostname
Resolve-DnsName $VpsConfig.TailscaleHostname
```

Результат `via <endpoint>` означает прямое соединение. `via DERP(...)` также работоспособен, но использует relay.

Проверить SSH-порт:

```powershell
Test-NetConnection `
    -ComputerName $VpsConfig.TailscaleHostname `
    -Port $VpsConfig.SshPort
```

---

## 5. Перевести SSH alias на Tailscale

Не закрывая текущую публичную SSH-сессию, сначала проверить прямой вход:

```powershell
ssh `
    -p $VpsConfig.SshPort `
    -i $VpsGuidePrivateKey `
    "$($VpsConfig.AdminUser)@$($VpsConfig.TailscaleHostname)"
```

В новом сеансе:

```bash
sudo -v
whoami
hostname
ip -brief address show tailscale0
```

После успешной проверки обновить основной SSH alias:

```powershell
Set-VpsGuideSshConfig -PrimaryHost $VpsConfig.TailscaleHostname
ssh $VpsConfig.SshAlias
```

Функция сохраняет дополнительный alias `${SshAlias}-public` с публичным IP для диагностики. После закрытия публичного UFW-правила этот alias ожидаемо перестанет подключаться.

---

## 6. Ограничить SSH интерфейсом Tailscale

В рабочем приватном SSH-сеансе разрешить SSH на `tailscale0`:

```bash
sudo ufw allow in \
  on tailscale0 \
  to any \
  port "$SSH_PORT" \
  proto tcp \
  comment 'SSH over Tailscale'
```

Откройте ещё одно окно Windows Terminal и повторите:

```powershell
ssh $VpsConfig.SshAlias
```

Только после успешного второго приватного входа удалить временное публичное правило SSH.

Показать нумерованный список:

```bash
sudo ufw status numbered
```

Найдите правило вида `22/tcp ALLOW IN Anywhere` или `OpenSSH ALLOW IN Anywhere`. Не удаляйте правило с пометкой `on tailscale0`.

Удалить выбранный номер:

```bash
while true; do
  printf 'Номер публичного SSH-правила UFW: '
  IFS= read -r UFW_RULE_NUMBER

  case "$UFW_RULE_NUMBER" in
    ''|*[!0-9]*)
      echo 'Требуется положительный номер правила.' >&2
      ;;
    *)
      break
      ;;
  esac
done

sudo ufw delete "$UFW_RULE_NUMBER"
```

Перезагрузить конфигурацию SSH и снова проверить новый приватный вход:

```bash
sudo sshd -t
sudo systemctl reload ssh.service
```

На Windows:

```powershell
ssh $VpsConfig.SshAlias

Test-NetConnection `
    -ComputerName $VpsConfig.ServerIp `
    -Port $VpsConfig.SshPort
```

Для публичного IP ожидается `TcpTestSucceeded : False`.

---

## 7. Ежедневный рабочий процесс

После однократной настройки Tailscale запускается автоматически. Обычный вход:

```powershell
ssh $VpsConfig.SshAlias
```

Ручной `tailscale login` каждый день не требуется.

Быстрая проверка при проблеме:

```powershell
tailscale status
tailscale ping $VpsConfig.TailscaleHostname
Test-NetConnection $VpsConfig.TailscaleHostname -Port $VpsConfig.SshPort
```

Не используйте `tailscale logout` для обычного перезапуска: logout отключает устройство и аннулирует текущую авторизацию.

---

## 8. SSH tunnel к localhost-сервисам

Smoke test из главы 2 слушает только `127.0.0.1:18080`. Для доступа с Windows:

```powershell
ssh `
    -N `
    -L 18080:127.0.0.1:18080 `
    $VpsConfig.SshAlias
```

Пока tunnel активен, открыть:

```text
http://127.0.0.1:18080
```

Та же схема применяется для pgAdmin, Adminer, Dozzle, Grafana и других административных интерфейсов, которые не должны быть публичными.

---

## 9. Настройки Tailscale Admin Console

Для VPS рекомендуется:

- включить MagicDNS;
- проверить понятное имя машины и отсутствие дубликатов;
- включить MFA у identity provider;
- хранить доступ к console VPS-провайдера;
- для постоянно работающего удалённого VPS осознанно выбрать политику key expiry;
- удалить потерянные или неиспользуемые устройства.

Не запускайте `tailscale up --force-reauth` из единственного SSH-сеанса через Tailscale: соединение может оборваться до завершения повторной авторизации.

---

## 10. Опциональная access policy

Для одного личного сервера можно начать с текущей default policy: OpenSSH всё равно требует SSH-ключ. При появлении нескольких серверов рекомендуется tag-based policy.

Создать пример policy в Git:

```bash
install -d -o "$ADMIN_USER" -g "$OPS_GROUP" -m 2775 \
  "$OPS_ROOT/config/tailscale"

jq -n \
  --arg policy_source "$TAILSCALE_POLICY_SOURCE" \
  --arg ssh_capability "tcp:$SSH_PORT" \
  '{
    tagOwners: {
      "tag:server": [$policy_source]
    },
    grants: [
      {
        src: [$policy_source],
        dst: ["tag:server"],
        ip: [$ssh_capability]
      }
    ]
  }' \
  > "$OPS_ROOT/config/tailscale/policy.hujson.example"
```

Не применяйте пример вслепую к существующему tailnet. Объедините его с текущей policy и используйте проверку Admin Console до сохранения.

---

## 11. Создать инвентаризационный скрипт

```bash
cat > "$OPS_ROOT/scripts/tailscale-inventory.sh" <<'EOF_TS_INVENTORY'
#!/usr/bin/env bash
set -Eeuo pipefail

source /etc/vps-guide/config.env

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

printf '\n## Network check\n'
tailscale netcheck

printf '\n## Firewall\n'
sudo ufw status numbered
EOF_TS_INVENTORY

chmod 0750 "$OPS_ROOT/scripts/tailscale-inventory.sh"
```

---

## 12. Git-фиксация

```bash
git -C "$OPS_ROOT" add scripts/tailscale-inventory.sh

if [ -d "$OPS_ROOT/config/tailscale" ]; then
  git -C "$OPS_ROOT" add config/tailscale
fi

git -C "$OPS_ROOT" commit -m 'Configure Tailscale private access'
```

IP-адрес Tailscale и `/var/lib/tailscale/tailscaled.state` не добавляются в Git.

---

## 13. Финальная проверка

На VPS:

```bash
sudo systemctl is-active tailscaled.service
sudo systemctl --failed
tailscale status
sudo ufw status numbered
```

На Windows:

```powershell
Get-Service Tailscale | Format-Table Name, Status, StartType
tailscale status
tailscale ping $VpsConfig.TailscaleHostname
ssh $VpsConfig.SshAlias
```

---

# Диагностика и типичные проблемы

## A. Windows показывает `unexpected state: NoState`

Это означает, что локальная служба Tailscale не завершила запуск или зависла. Откройте PowerShell от имени администратора:

```powershell
Get-Service -Name Tailscale | Format-Table Name, Status, StartType

Set-Service -Name Tailscale -StartupType Automatic

$service = Get-Service -Name Tailscale
if ($service.Status -eq 'Running') {
    Restart-Service -Name Tailscale -Force
} else {
    Start-Service -Name Tailscale
}

Start-Sleep -Seconds 5
tailscale up --unattended=true
tailscale status
tailscale ip -4
```

Если откроется браузер, войдите в тот же аккаунт. Если `NoState` сохраняется, перезагрузите Windows и повторите команды.

## B. После сбоя Windows невозможно подключиться к серверу

Публичный SSH закрыт намеренно. Сначала восстанавливается Tailscale на Windows, затем выполняется обычный `ssh vps`. Не открывайте публичный SSH только из-за локально остановившейся службы Tailscale.

## C. Служба Tailscale не запускается

```powershell
Get-Service Tailscale
Get-WinEvent -LogName Application -MaxEvents 100 |
    Where-Object Message -Match 'Tailscale'
tailscale bugreport --diagnose
```

Логи Windows-клиента находятся в `%ProgramData%\Tailscale\Logs`.

## D. MagicDNS не разрешает имя

```powershell
tailscale status
tailscale dns status
Resolve-DnsName $VpsConfig.TailscaleHostname
```

Проверьте, что MagicDNS включён и обе машины находятся в одном tailnet.

Временно можно использовать Tailscale IPv4 из `tailscale status`, но не записывать его в Git и постоянные Compose-файлы без необходимости.

## E. `tailscale ping` работает, а SSH — нет

На VPS через console провайдера:

```bash
sudo systemctl status ssh.service --no-pager
sudo sshd -t
sudo ss -lntp | grep ":${SSH_PORT}\b"
sudo ufw status numbered
```

Должно существовать allow-правило `on tailscale0`.

## F. Соединение идёт через DERP

DERP является штатным fallback. Для попытки direct-соединения:

```bash
sudo ufw allow "${TAILSCALE_UDP_PORT}/udp" comment 'Tailscale direct WireGuard'
tailscale netcheck
```

На Windows повторить `tailscale ping`. Direct-маршрут не гарантируется при некоторых NAT и корпоративных сетях.

## G. Аварийно вернуть публичный SSH

Выполнить через web/serial console провайдера:

```bash
source /etc/vps-guide/config.env
sudo ufw allow "${SSH_PORT}/tcp" comment 'Temporary SSH recovery'
sudo sshd -t
sudo systemctl reload ssh.service
```

После восстановления Tailscale удалить временное правило.

## H. Повторная авторизация VPS

Используйте console провайдера или дополнительный независимый SSH-сеанс:

```bash
sudo tailscale up \
  --hostname="$TAILSCALE_HOSTNAME" \
  --accept-dns=true \
  --operator="$ADMIN_USER" \
  --force-reauth
```

Не выполнять из единственного активного Tailscale-сеанса.

---

## Официальная документация

- Install Tailscale on Linux: https://tailscale.com/kb/1031/install-linux
- Windows unattended mode: https://tailscale.com/kb/1088/run-unattended
- Tailscale CLI: https://tailscale.com/kb/1080/cli
- MagicDNS: https://tailscale.com/kb/1081/magicdns
- Access control: https://tailscale.com/kb/1018/acls
- Key expiry: https://tailscale.com/kb/1028/key-expiry
