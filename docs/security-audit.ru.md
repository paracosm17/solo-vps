# Аудит границы безопасности

`make audit` — read-only проверка, сфокусированная на security controls и сетевой exposure, важной для текущего профиля Solo VPS.

## Запустите audit

**Где: управляемый VPS/контроллер**

```bash
make audit
```

Ненулевой exit code — причина остановиться и разобраться с обнаруженной границей до следующего деплоя или изменения состояния.

## Для чего нужен audit

Audit отвечает, например, на такие вопросы:

- находится ли управляемая SSH-политика в ожидаемом состоянии?
- присутствуют ли host firewall controls?
- соответствуют ли Docker/Coolify publications предполагаемой модели exposure?
- не опубликованы ли случайно database/cache management ports?
- сохраняют ли опциональные observability-компоненты границу конфиденциальности, когда они включены?

## UFW — не вся сетевая граница

Docker-published ports могут взаимодействовать с packet filtering иначе, чем обычные host listeners. Поэтому Solo VPS отдельно проверяет Docker publication и не считает успешный статус UFW доказательством приватности каждого container port.

Loopback publications Coolify `8000/6001/6002` должны оставаться доступными только через `127.0.0.1` и быть недоступными по public-адресу хоста.

## Чего PASS не доказывает

Локальный audit не может доказать provider-firewall policy, корректность DNS, поведение WAF, реальную внешнюю доступность, recoverability backup или application-level authorization.

Для этих границ используйте внешние проверки.

## Связанные страницы

- [Фаервол](firewall.md)
- [Установка Coolify](coolify-installation.md)
- [Verification](verification.md)
- [Внешний uptime](operations/external-uptime.md)
