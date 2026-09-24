# Отклонённый эксперимент Coolify-native Grafana Cloud log drain

> **Историческая / recovery reference.** Этот отклонённый путь Coolify-native **Custom FluentBit** **не является поддерживаемой схемой application logs**. Для новых установок используйте [Grafana Alloy + ограниченный Docker API proxy](observability.md).

Страница сохранена, потому что оператору, который раньше включил эксперимент, может понадобиться безопасно диагностировать или удалить его.

## Что делал эксперимент

Проверявшийся путь:

```text
Coolify application
  -> local Fluent Bit receiver at 127.0.0.1:24224
  -> Custom FluentBit configuration
  -> Grafana Cloud Loki
```

Конфигурация использовала `service_name` и выбранный `COOLIFY_APP_NAME`, чтобы application logs можно было искать в Grafana Cloud.

## Перед включением или диагностикой

Не включайте это на свежем Solo VPS только потому, что существует эта страница. Используйте её только для хоста, где историческая конфигурация уже есть, или для disposable reproduction.

Нужны существующий observability credential bundle и обычная установка Coolify. По возможности не оставляйте tokens в terminal history и clipboard history.

## Рабочая станция Windows: скопируйте конфигурацию без вывода token

Исторический helper:

```powershell
.\scripts\windows\copy-observability-log-drain.ps1
```

Вставляйте только в нужное поле Coolify, затем **очистите clipboard**.

## Настройте сервер в Coolify

В Coolify откройте:

**Configuration > Log Drains**

Используйте **Advanced** / Custom FluentBit configuration, относящуюся к эксперименту. Не расширяйте Docker или host exposure ради работы drain.

## Сначала включите log draining для одного приложения

Выберите одно disposable или low-risk приложение и включите **Drain Logs**. Запишите его `COOLIFY_APP_NAME`; не подключайте все workloads до доказательства single-app path.

## Проверьте локальный путь Coolify

Выполните:

```bash
make verify-observability-log-drain
```

Ожидаемый результат: ожидаемая Coolify-side configuration и opt-in выбранного приложения присутствуют, при этом local collector не опубликован наружу.

Если эксперимент отключён и вы проверяете cleanup:

```bash
make verify-observability-log-drain-disabled
```

## Независимо проверьте Grafana

Чтобы отдельно от Coolify доказать Grafana Cloud endpoint и credentials, можно отправить одну synthetic non-secret запись:

```bash
make test-observability-loki
```

Это **EXTERNAL WRITE**. Используйте только если намеренно хотите создать synthetic log entry.

## Диагностика отсутствующего receiver

Если Coolify настроен, но local receiver не появился на `127.0.0.1:24224`, выполните:

```bash
make diagnose-observability-log-drain
```

Не публикуйте receiver port и не меняйте host firewall rules как workaround. Отсутствующий loopback receiver — runtime/configuration problem, а не причина создавать public listener.

## Откат эксперимента

Отключите **Drain Logs** у подключённых приложений, удалите Custom FluentBit configuration через Coolify, затем докажите остановку historical collector:

```bash
make verify-observability-log-drain-disabled
```

Вернитесь к поддерживаемому пути в [руководстве по профессиональной observability](observability.md).
