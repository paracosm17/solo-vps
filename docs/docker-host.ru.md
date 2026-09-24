# Базовая конфигурация Docker-хоста

Solo VPS управляет конфигурацией Docker **на хосте**; Coolify управляет lifecycle приложений/контейнеров поверх неё.

## Поддерживаемая цель

Текущий alpha-контракт поддерживает:

- Ubuntu 24.04 LTS;
- host-архитектуры `x86_64` и `aarch64`;
- только Docker Engine **29.x**;
- Docker Compose plugin `2.24.4+` для текущей интеграции Coolify.

Lifecycle работает fail-closed за пределами поддерживаемого major Docker и не переходит молча на Docker 30.

## Что управляет Solo VPS

Docker role устанавливает пакеты из официального Ubuntu-репозитория Docker:

```text
docker-ce
docker-ce-cli
containerd.io
docker-buildx-plugin
docker-compose-plugin
```

Также он управляет `/etc/docker/daemon.json` с минимальной базовой конфигурацией:

```json
{
  "live-restore": true,
  "log-driver": "local",
  "log-opts": {
    "max-size": "20m",
    "max-file": "5"
  }
}
```

## Safety gate для существующего runtime

Свежая установка Solo VPS отказывается молча заменять конфликтующие distro/container runtime packages вроде `docker.io`, `podman-docker` или независимо управляемый стек `containerd`/`runc`.

Если на хосте уже есть container runtime, рассматривайте это как migration decision, а не пытайтесь протолкнуть через него роль для чистого хоста.

## Группа Docker

Управляемому администратору разрешена работа с Docker, потому что это требуется интеграции Coolify. Доступ к Docker group фактически эквивалентен root; Solo VPS выдаёт его только уже привилегированному управляемому администратору.

## Сетевая граница

Solo VPS не задаёт глобальный loopback bind default для application containers. За application networking и proxying отвечает Coolify.

Используйте `make audit`, чтобы проверить фактические host/Docker publications. Не считайте UFW полным описанием container exposure.

## Применить и проверить

Используйте обычный lifecycle:

```bash
make apply
make verify
make audit
```

## Обновления

Не используйте `make docker` как универсальный updater. Поддерживаемый lifecycle описан в [руководстве по обновлению](upgrades.md).
