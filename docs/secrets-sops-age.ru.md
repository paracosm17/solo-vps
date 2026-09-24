# Управление infrastructure secrets через SOPS + age

Solo VPS использует SOPS + age для **небольшого набора infrastructure и recovery secrets**. Vault, второй сервер или постоянно работающий secrets service для этого не нужны.

Модель выглядит так:

```text
one home workstation (Windows or Linux)
  ├── one age private key
  ├── public SOPS policy/recipient
  └── encrypted Solo VPS secret bundles

one VPS
  └── only the root-only runtime credentials each feature needs
```

Обычные runtime secrets приложений хранятся в Coolify. CI-only secrets — в GitHub. Production age private key остаётся на рабочей станции.

## Что защищает SOPS

Текущие encrypted bundles:

```text
backup.enc.yaml           restic/S3 runtime credentials
observability.enc.yaml    Grafana Cloud Logs credentials
metrics.enc.yaml          Grafana Cloud Metrics credentials
```

Ciphertext и public recipient/policy metadata можно безопасно резервировать в соответствии с вашей operator policy. Если потерять все копии age private key, ciphertext станет невосстановимым.

## Рабочая станция Windows

Если PowerShell блокирует скрипты из скачанной из Интернета копии проекта, разблокируйте только Windows-скрипты Solo VPS:

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
```

Команда снимает с этих файлов метку происхождения из Интернета и не меняет политику выполнения PowerShell. `RemoteSigned` подходит; переключать её на `Unrestricted` не нужно. Если после разблокировки скрипты всё ещё не запускаются, выполните `Get-ExecutionPolicy -List`: заданные организацией `MachinePolicy` или `UserPolicy` имеют приоритет над локальными настройками, и менять их должен администратор этой политики.

Установите инструменты проекта с проверкой контрольных сумм:

```powershell
.\scripts\windows\install-secrets-tools.ps1
```

Подготовьте production age identity:

```powershell
.\scripts\windows\new-age-key.ps1
```

Команда идемпотентна: существующий ключ проверяется и сохраняется без замены. Скрипт также ограничивает NTFS ACL каталога и файла текущим пользователем, `SYSTEM` и локальными администраторами.

Приватный файл находится здесь:

```text
%USERPROFILE%\.config\solo-vps\age-key.txt
```

Сделайте его backup в контролируемом вами месте. Не коммитьте его и не копируйте на VPS.

Инициализируйте постоянную public SOPS policy:

```powershell
.\scripts\windows\init-sops-policy.ps1
```

Сгенерированное public policy/recipient state хранится вне Git checkout в `%LOCALAPPDATA%\solo-vps\state\sops\`. Повторный запуск с тем же ключом безопасен. Если сохранился state от другого ключа, helper показывает оба recipient и количество зашифрованных файлов. Для восстановления старых секретов нужен прежний private key. Если старые ciphertext-файлы не нужны в активной настройке и вы просто проходите setup заново, используйте `-StartFresh`: policy и `*.enc.yaml` будут перенесены в `%LOCALAPPDATA%\solo-vps\archive\workstation-secrets\<дата-время>\`, а текущий private key останется без изменений.

Проверьте production key на несекретных временных данных:

```powershell
.\scripts\windows\test-age-key.ps1
```

## Рабочая станция Linux

Установите/проверьте pinned tools в пользовательском cache Solo VPS:

```bash
make secrets-tools
make check-secrets-tools
```

Создайте один production age key на рабочей станции:

```bash
mkdir -p ~/.config/solo-vps
chmod 700 ~/.config/solo-vps
age-keygen -o ~/.config/solo-vps/age-key.txt
chmod 600 ~/.config/solo-vps/age-key.txt
```

Покажите public recipient:

```bash
age-keygen -y ~/.config/solo-vps/age-key.txt
```

Инициализируйте внешнюю public policy:

```bash
make init-sops-policy SOPS_AGE_RECIPIENT='age1...'
```

Для ручных SOPS operations укажите `SOPS_AGE_KEY_FILE` на workstation private key и используйте путь policy, который выводит `make paths`.

## Докажите отсутствие private key на VPS

**Где: VPS под управляемым администратором**

```bash
make verify-vps-secrets-boundary
```

Это read-only check. Он проверяет стандартные Solo VPS/SOPS locations для managed admin и root; произвольные файлы не сканируются и не удаляются.

Ожидаемый результат:

```text
production age private identity on VPS: absent
```

## Bundle backup credentials

Encrypted backup bundle называется `backup.enc.yaml`. Создавайте/проверяйте его на рабочей станции и передавайте на VPS только decrypted runtime values через SSH stdin.

Linux:

```bash
make backup-secrets-init
make backup-secrets-check
make backup-secrets-push BACKUP_VPS_HOST=<VPS-IP> BACKUP_VPS_USER=<admin-user>
```

Windows:

```powershell
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
.\scripts\windows\push-backup-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

**Age private key остаётся на рабочей станции.** См. [внешние backup через restic](backups-restic.md).

## Bundle Grafana Cloud credentials

Optional retained-log profile использует `observability.enc.yaml` для Grafana Cloud credentials.

Linux:

```bash
make observability-secrets-init
make observability-secrets-check
make observability-secrets-push OBSERVABILITY_VPS_HOST=<VPS-IP> OBSERVABILITY_VPS_USER=<admin-user>
```

Windows:

```powershell
.\scripts\windows\init-observability-secrets.ps1
.\scripts\windows\test-observability-secrets.ps1
.\scripts\windows\push-observability-secrets.ps1 -VpsHost <VPS-IP> -VpsUser <admin-user>
```

См. [профессиональная observability](operations/observability.md).

## Политика репозитория

Публичный репозиторий содержит только templates/placeholders вроде `.sops.yaml.example` и примеры public recipient. Operator-specific public recipients, encrypted personal infrastructure state и private keys не должны попадать в upstream source.

SOPS шифрует files at rest. Он не делает runtime credential невидимым для `root` на VPS после того, как credential был намеренно установлен для service.

## Recovery rule

Храните как минимум одну защищённую backup-копию workstation age private key. Disaster recovery может вернуть encrypted bundles из recovery kit/off-site copy, но без соответствующей private identity эти файлы бесполезны.
