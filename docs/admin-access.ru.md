# Настройка административного доступа

Solo VPS создаёт одного управляемого администратора без root-login и разделяет две SSH-идентичности:

- **automation identity** — используется контроллером;
- **human workstation identity** — используется вами для обычного SSH-доступа.

Приватный ключ человека должен оставаться на вашей рабочей станции.

## До `make apply`

Сначала выполните `make setup` и отредактируйте постоянную конфигурацию. Затем добавьте публичный ключ человека через поддерживаемый helper.

### Same-VPS/root-first сценарий

**Где: рабочая станция**

Linux/macOS shell:

```bash
cat ~/.ssh/id_ed25519.pub | ssh <provider-user>@<server> 'cd ~/solo-vps && make human-admin-key-stdin'
```

PowerShell:

```powershell
Get-Content -Raw "$HOME\.ssh\id_ed25519.pub" | ssh <provider-user>@<server> "cd ~/solo-vps && make human-admin-key-stdin"
```

### Отдельный checkout контроллера

**Где: контроллер/рабочая станция**

```bash
make human-admin-key-file HUMAN_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
```

Helper принимает ровно одну строку OpenSSH public key, атомарно обновляет постоянную конфигурацию и отклоняет private-key material.

## Что создаёт `make apply`

Настроенный `admin.user` получает:

- обычный home directory и login shell `/bin/bash`;
- членство в Ubuntu-группе `sudo`;
- режим `0700` для `~/.ssh`;
- оба настроенных публичных ключа в `authorized_keys` с режимом `0600`;
- управляемый fragment `/etc/sudoers.d/90-solo-vps-<user>` с passwordless sudo после проверки через `visudo`.

Этот этап намеренно только добавляет доступ. Он не усиливает SSH daemon, не отключает root login/passwords и не удаляет существующие admin keys.

## Докажите human login до hardening

После `make apply` откройте **новую** сессию с рабочей станции:

```bash
ssh <admin.user>@<server>
sudo -n id -u
```

Ожидаемый вывод:

```text
0
```

Также убедитесь, что доступен provider console/rescue. Текущую рабочую сессию не закрывайте.

Только после этого переходите к [усилению SSH](ssh-hardening.md).

## Если вход с рабочей станции не работает

Не исправляйте `authorized_keys` вручную наугад. Повторно запустите helper публичного ключа через рабочий provider/recovery path, затем снова примените additive identity state:

```bash
make bootstrap
make verify
```

Если вы уже используете five-command lifecycle, нормальная предпочтительная точка входа — `make apply`.

## Граница безопасности

На same-VPS установке automation- и human-ключи должны быть разными. Приватный ключ контроллера может находиться на VPS для локальной automation; приватный human-ключ — нет.

Solo VPS сохраняет существующий доступ на additive-этапе: удаление неизвестного рабочего ключа до доказательства нового пути может заблокировать вход. SSH-ограничения применяются только отдельным hardening-шагом с safety gate.
