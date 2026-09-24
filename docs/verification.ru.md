# Проверка управляемой платформы

`make verify` — стандартная read-only проверка уверенности после установки и после значимых изменений хоста/платформы.

## Запустите проверку

**Где: управляемый VPS/контроллер**

```bash
make verify
```

Target сначала запускает локальную диагностику возможностей, затем проверяет реализованное состояние хоста/платформы, не меняя desired configuration.

## Что проверяется

Составная verification проверяет части, которыми Solo VPS сейчас управляет или которые может безопасно инспектировать: управляемого администратора, SSH-related state, firewall/update baseline, Docker-хост и установленное состояние платформы.

Если нужен более узкий ответ, используйте subsystem-проверки:

```bash
make verify-ssh
make verify-coolify
```

## Verification — не тест доступности

Успешный `make verify` не доказывает, что:

- public DNS настроен правильно;
- приложение реально обслуживает трафик;
- внешний монитор видит сервис;
- внешние backup существуют;
- restore проходит успешно;
- уничтоженный VPS можно полностью восстановить.

Для этого нужны внешние или application-specific доказательства.

## Запускайте verification вместе с security audit

После provisioning, upgrades, recovery или сетевых изменений выполните:

```bash
make verify
make audit
```

Обе команды задуманы как read-only. Audit концентрируется на exposure и security controls, а не дублирует каждую verification-проверку.

## Связанные страницы

- [Аудит безопасности](security-audit.md)
- [Внешний uptime](operations/external-uptime.md)
- [Backup и recovery](backups-restic.md)
