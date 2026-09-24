# Проверка требований и подключения

Используйте `make doctor`, когда нужен read-only ответ на вопрос: **готов ли этот контроллер, может ли он подключиться к target и соответствует ли target текущим требованиям Solo VPS?**

## Поддерживаемый target первого запуска

Текущий alpha-путь рассчитан на:

- Ubuntu 24.04 LTS;
- Python 3.12+ на контроллере после `make setup`;
- OpenSSH client/tooling;
- явный SSH-доступ к настроенному target;
- Docker 29.x для текущего platform lifecycle;
- достаточно CPU, RAM и disk для Coolify readiness gate.

Точные resource checks application platform выполняются позже через `make platform` / `make coolify-readiness`.

## Первое требование к контроллеру

До того как проект сможет что-либо автоматизировать, установите GNU Make и получите исходники:

```bash
apt-get update
apt-get install -y make git
cd solo-vps
make setup
```

`make setup` готовит оставшиеся controller dependencies и persistent state.

## Запустите doctor

**Где: контроллер**

```bash
make doctor
```

`make doctor` — read-only команда. Она объединяет локальную диагностику контроллера, отчёт о platform capabilities и remote preflight для текущего inventory target.

## Что проверяется

Точный набор зависит от стадии lifecycle, но doctor должен обнаруживать такие проблемы, как:

- отсутствующие local config/inventory;
- неподдерживаемый или неполный controller tooling;
- некорректные пути к public keys;
- недоступный SSH target;
- несовпадение inventory/user;
- неподдерживаемые характеристики платформы;
- очевидные state conflicts до mutation.

## Требуемые локальные файлы

Mutable operator state хранится вне source checkout. Выполните:

```bash
make paths
```

чтобы увидеть активные директории config, inventory, toolchain, SOPS policy, evidence и state.

Подробнее: [структура постоянного состояния](state-layout.md).

## Контракт первоначального доступа

Для первой mutation нужен рабочий provider/bootstrap SSH path. Если provider user отличается от inventory user, normal lifecycle позволяет указать его явно:

```bash
make apply BOOTSTRAP_USER=ubuntu
```

После host baseline inventory переходит на настроенного `admin.user`. SSH hardening запрещён до тех пор, пока не доказаны свежий workstation login и provider recovery.

## Если `make doctor` завершился ошибкой

Исправьте первую actionable ошибку и только потом запускайте mutating commands. Не обходите check ручными изменениями firewall, SSH, Docker или Coolify, если этого прямо не требует документированная recovery procedure.

Полезные следующие страницы:

- [Доступ администратора](admin-access.md)
- [Усиление SSH](ssh-hardening.md)
- [Docker host](docker-host.md)
- [Установка Coolify](coolify-installation.md)
- [Справочник команд](command-reference.md)
