# Переменные и секреты приложения в Coolify

Для обычной runtime-конфигурации приложения используйте Coolify. SOPS + age предназначен для infrastructure/recovery файлов и **не является эквивалентом Vault** или ежедневным редактором application secrets.

## Одна JSON-переменная — нормальный вариант

Не обязательно заводить отдельную environment variable на каждое JSON-поле. Если приложение естественно принимает единый конфигурационный документ, multiline-переменная вполне уместна:

```text
APP_CONFIG_JSON
```

Пример значения:

```json
{
  "payments": {
    "merchant_id": "<value>",
    "token": "<secret>"
  },
  "notifications": {
    "chat_id": "<value>"
  }
}
```

В Coolify включите **Multiline**, если значение занимает несколько строк. Приложение разбирает `APP_CONFIG_JSON` при старте.

## Разделяйте переменные, если у них разный lifecycle

Используйте независимые переменные, когда значения вращаются или меняются независимо:

```text
DATABASE_URL
STRIPE_API_KEY
SENTRY_DSN
SMTP_PASSWORD
```

Так проще понимать per-environment overrides и rotation.

## Build-time и Runtime

Сохраняйте границу явной:

- **Runtime** values передаются работающему приложению;
- **Build Variable** values существуют во время сборки image и не должны использоваться для secrets, если сборке они действительно не нужны;
- **Docker Build Secrets** предпочтительнее, когда build требует secret material без встраивания его в image layers.

Не копируйте runtime secret в image только потому, что Dockerfile может прочитать build argument.

## Locked secrets

Для чувствительных runtime values используйте locked/secret-механику Coolify. Ограничьте круг пользователей, которые могут просматривать/редактировать приложение в Coolify, и не вставляйте production values в issue reports, публичные логи или документацию.

## Shared variables

Coolify **Shared variables** уменьшают дублирование для значений, которые намеренно общие для нескольких resources/environments. Не используйте sharing вместо least privilege: secret, нужный только одному приложению, должен оставаться scoped к нему.

## CI-only secrets

Deployment/API credentials, которые используются только GitHub Actions, должны храниться в GitHub repository/environment secrets, а не в runtime variables приложения Coolify.

## Infrastructure/recovery secrets

S3 credentials, restic passwords и Grafana Cloud ingestion credentials, используемые host automation Solo VPS, следуют модели [SOPS + age](../secrets-sops-age.md), а не application-variable path.

## Config files

Если приложению действительно нужна файловая семантика, используйте проверенный механизм, который materializes значение во время runtime с ограничительными permissions. Не добавляйте постоянно работающий secret server только ради превращения статического JSON в файл на одном VPS.

## Справка

- Coolify environment variables: <https://coolify.io/docs/knowledge-base/environment-variables>
