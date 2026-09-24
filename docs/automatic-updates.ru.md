# Автоматические обновления безопасности

Solo VPS включает unattended security updates Ubuntu, но намеренно оставляет автоматическую перезагрузку выключенной.

## Политика

Управляемая политика `unattended-upgrades` разрешает Ubuntu release/security origins, используемые базовой конфигурацией хоста, и исключает из автоматического security-пути широкие `-updates`, `-proposed`, `-backports`, PPA и посторонние third-party репозитории.

Для Docker и Coolify действуют отдельные явные lifecycle-политики; Ubuntu `unattended-upgrades` не обновляет их незаметно.

## Политика перезагрузки

Автоматический reboot отключён. Если Ubuntu сообщает, что требуется перезагрузка, запланируйте её на момент, когда после неё сможете проверить платформу.

После reboot:

```bash
make verify
make audit
```

и снаружи проверьте public health endpoint вашего приложения.

## Применить и проверить

Политика обновлений входит в обычный lifecycle хоста:

```bash
make apply
make verify
```

## Почему политика консервативная

Security-патчи должны устанавливаться без превращения изменений версий хоста и платформы в неконтролируемую цепочку обновлений. Поэтому major-версии Docker, версии Coolify и зависимости проекта остаются осознанными upgrade-решениями.

## Справка

- Документация Ubuntu по unattended-upgrades: <https://help.ubuntu.com/community/AutomaticSecurityUpdates>
