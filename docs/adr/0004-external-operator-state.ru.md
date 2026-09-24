# ADR-0004: Хранить состояние оператора/контроллера вне Git checkout

Статус: Принято  
Дата: 2026-08-14

## Контекст

Ранние PRE-ALPHA сборки хранили ignored `config.yml`, inventory, controller virtualenv, сгенерированную public SOPS policy и handoff markers внутри checkout Solo VPS. Это делало замену исходников хрупкой: archive/reclone мог незаметно удалить нужные локальные файлы, а будущий Git update осложнялся generated checkout-local state.

Публичный продукт должен легко обновляться и безопасно re-clone-иться. Per-installation state также должен переживать удаление source tree.

## Решение

Считать Git checkout одноразовым источником продукта.

В Linux mutable per-user controller/operator state Solo VPS по умолчанию хранится в:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/solo-vps
```

Этот root содержит persistent config/inventory и pinned controller QA/runtime toolchain. Generated public SOPS workstation policy также по умолчанию живёт вне checkout. Windows workstation helpers используют `%LOCALAPPDATA%\solo-vps\state` для generated public policy/recipient state. Private age key остаётся в защищённом key path рабочей станции и не переносится в public/operator data set.

System/runtime state продолжает использовать правильные service-owned locations, включая `/data/coolify` и Ansible-managed файлы в `/etc`.

Legacy checkout-local config/inventory могут быть скопированы вперёд через `make init`, но automated migration не удаляет оригиналы.

## Последствия

Плюсы:

- `git pull`, замена исходников и re-clone больше не зависят от ignored config/inventory внутри repository;
- controller toolchain state переживает замену исходников;
- гигиена публичного repository становится проще;
- backup/recovery может рассматривать product source и installation state как разные сущности.

Компромиссы:

- пользователю нужно знать один persistent data root в дополнение к source checkout;
- старым PRE-ALPHA установкам требуется одноразовая миграция через `make init`;
- пути в документации и contract tests не должны снова drift-ить к checkout-local defaults.

Это решение не добавляет второй controller, VPS, service или configuration database.
