# Фаервол и публичные порты

Solo VPS использует UFW как **базовую host-input защиту**. Текущий core-профиль поддерживает публичный SSH и HTTP/HTTPS edge, необходимый приложениям Coolify.

## Текущая политика

Управляемый SSH-порт:

```text
22/tcp
```

Настраиваемые публичные application ports сейчас ограничены:

```yaml
firewall:
  public_ports:
    - 80
    - 443
```

Произвольные публичные host ports намеренно не являются generic configuration feature в alpha-профиле.

## Применить и проверить

Фаервол применяется обычным lifecycle хоста:

```bash
make apply
make verify
make audit
```

Во время первого применения не закрывайте текущую provider-сессию и держите доступным provider console/rescue path.

## Docker — отдельная граница exposure

Списка правил UFW недостаточно, чтобы доказать приватность каждого Docker-published port. Solo VPS отдельно проверяет Docker publication.

Для стандартного профиля Coolify:

- `80/443` — публичный application edge;
- `8000/6001/6002` должны быть loopback-only;
- container ports приложений, например `8080`, обычно должны оставаться внутренними Docker ports, а не host publications.

## Provider firewall

Фаервол или security group облачного провайдера находится вне automation Solo VPS. Держите его согласованным с предполагаемым public edge и provider recovery model.

## Восстановление доступа

Если изменения фаервола сломали SSH, используйте provider console/rescue. Не расширяйте постоянную firewall policy, пока не поймёте, какое правило или publication вызвало проблему.

## Связанные страницы

- [Защита SSH](ssh-hardening.md)
- [Аудит безопасности](security-audit.md)
- [Установка Coolify](coolify-installation.md)
