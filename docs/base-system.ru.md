# Базовая конфигурация системы

Base role намеренно оставляет Ubuntu-хост минимальным. Solo VPS устанавливает только пакеты, необходимые основному сценарию одного VPS, а зависимости приложений оставляет контейнерам/Coolify.

## Что управляется

`make apply` / `make bootstrap` могут:

- задать `server.hostname`;
- задать `server.timezone`;
- обновить устаревшие APT metadata;
- установить базовый набор пакетов:
  - `ca-certificates`
  - `curl`
  - `git`
  - `jq`
  - `lsof`
  - `rsync`
  - `sudo`
  - `tzdata`
  - `unzip`

Base role **не** выполняет full/dist upgrade.

## Настройте hostname и timezone

В постоянной конфигурации:

```yaml
server:
  host: YOUR_SERVER_IP
  hostname: solo-vps-01
  timezone: UTC
```

`server.host` — адрес, к которому подключается Ansible. `server.hostname` — Linux hostname. Не смешивайте эти понятия.

## Применить и проверить

Используйте обычный lifecycle вместо прямого запуска base role:

```bash
make apply
make verify
```

## Почему список пакетов короткий

Большой набор host-пакетов увеличивает поверхность обновлений и усложняет понимание состояния VPS. Runtime-зависимости приложений должны находиться в application images, если они действительно не нужны самому хосту.
