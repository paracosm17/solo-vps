# Coolify dashboard через HTTPS

После первой регистрации через SSH tunnel используйте отдельный HTTPS hostname для обычного доступа к Coolify. Raw management ports должны оставаться приватными.

## 1. Создайте DNS record

Используйте hostname, например:

```text
coolify.example.com
```

Направьте его на VPS в соответствии с вашим DNS/proxy provider.

## 2. Укажите URL экземпляра Coolify

**Где: Coolify → Settings → Configuration → General**

Установите:

```text
https://coolify.example.com
```

Используйте этот HTTPS-домен для обычной панели, live logs, realtime features и browser terminal.

## Контракт безопасности

Предполагаемая exposure остаётся такой:

```text
public TCP:       22, 80, 443
loopback/private: 8000, 6001, 6002
```

**Raw management ports остаются приватными.** Не публикуйте `8000`, `6001` или `6002`, чтобы исправить browser-проблему.

## Сначала проверьте server-side path

**Где: VPS/контроллер**

```bash
make verify-coolify
make audit
```

Verifier проверяет loopback health endpoints и подтверждает, что raw `8000/6001/6002` недоступны через управляемый public target address.

## Включите browser terminal

**Где: Coolify**

```text
Servers
→ localhost
→ Security
→ Terminal Access
```

Включайте terminal access только если собираетесь им пользоваться. Открывайте terminal приложения/контейнера через HTTPS dashboard domain.

Минимальная non-mutating проверка:

```sh
id
pwd
printf 'terminal-ok\n'
```

Terminal использует HTTPS/realtime **websocket** path; публиковать raw realtime ports для этого не нужно.

## Если browser terminal не работает

1. выполните `make verify-coolify`;
2. убедитесь, что Terminal Access включён;
3. проверьте failed browser WebSocket request/status в developer tools;
4. не делитесь cookies, XSRF tokens, authorization headers, SSH keys или private API responses;
5. завершите любое проверенное server-side изменение командой `make audit`.

Server-side readiness PASS при ошибке browser websocket указывает на HTTPS proxy/session path, а не на необходимость публичного `6002`.

## Справка

- Coolify DNS configuration: <https://coolify.io/docs/knowledge-base/dns-configuration>
- Coolify terminal documentation: <https://coolify.io/docs/knowledge-base/internal/terminal>
