# 7. Следите за CPU, памятью и диском в Grafana

Логи отвечают на вопрос «что произошло?». Метрики показывают, **что происходило с самим VPS во времени**: росла ли нагрузка на CPU, заканчивалась ли память и сколько места осталось на диске.

В этой главе не строим большой monitoring stack. Solo VPS запускает небольшой отдельный процесс Grafana Alloy, который читает только несколько метрик Linux-хоста и отправляет их в Grafana Cloud. Логи из главы 3 продолжают работать отдельно.

После главы вы должны уметь:

- найти CPU, память и диск в **Grafana → Drilldown → Metrics**;
- увидеть понятные проценты в Explore;
- получить тестовое email-уведомление от Grafana;
- реально перевести disk alert в `Firing`, получить письмо и вернуть alert в нормальное состояние.

## Перед началом

Нужны:

- работающий VPS после глав 1–2;
- локальная копия `solo-vps` на вашем компьютере;
- аккаунт Grafana Cloud. Если вы проходили главу 3, используйте **тот же stack**;
- рабочий SSH-доступ под настроенным `admin.user` на VPS.

Для метрик используется тот же закреплённый бинарник Alloy, но отдельный сервис `solo-vps-metrics.service`. Ему не нужен Docker socket и он не меняет конфигурацию `solo-vps-alloy.service` с логами.

## 1. Получите три значения Grafana Cloud Metrics

**В браузере:** откройте [Grafana Cloud Portal](https://grafana.com/), выберите свой stack и найдите карточку **Prometheus**. Нажмите **Details**.

Сохраните в менеджере паролей:

1. **Remote Write Endpoint** — HTTPS URL, который заканчивается на `/api/prom/push`;
2. **User** — числовой Metrics instance ID;
3. отдельный access-policy token только с правом **`metrics:write`**.

Для токена откройте Cloud access policies, создайте policy, например `solo-vps-metrics`, добавьте scope `metrics:write`, затем создайте token и скопируйте его. Сам токен показывается как секрет — не вставляйте его в issue, чат или Git.

[Официальная документация Grafana Cloud Metrics](https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/metrics/metrics-prometheus/query-http-api/) описывает тот же набор: Remote Write Endpoint и User берутся из **Prometheus → Details**, а token используется как пароль Basic Auth.

## 2. Подготовьте локальное шифрование, если ещё не делали этого

Если главы 3 или 6 уже пройдены на этом компьютере и `test-age-key` проходит, существующий age-ключ **не пересоздавайте**.

### Windows PowerShell

**На компьютере, в каталоге Solo VPS:**

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
.\scripts\windows\install-secrets-tools.ps1
.\scripts\windows\new-age-key.ps1
.\scripts\windows\init-sops-policy.ps1
.\scripts\windows\test-age-key.ps1
```

Повторный запуск безопасен: существующий рабочий ключ и policy переиспользуются. Ожидайте:

```text
PASS Solo VPS production age key SOPS roundtrip
```

Если `init-sops-policy.ps1` сообщает о несовпадении старого recipient, не удаляйте файлы вручную. Для намеренного чистого повторного прохождения используйте описанный ранее режим `-StartFresh`.

### Компьютер с Linux

**На компьютере, в каталоге Solo VPS:**

```bash
make secrets-tools
solo_age_keygen="$(python3 scripts/secrets_toolchain.py paths | sed -n 's/^age-keygen=//p')"
mkdir -p ~/.config/solo-vps
chmod 700 ~/.config/solo-vps
if [ ! -e ~/.config/solo-vps/age-key.txt ]; then
    "$solo_age_keygen" -o ~/.config/solo-vps/age-key.txt
fi
chmod 600 ~/.config/solo-vps/age-key.txt
make init-sops-policy SOPS_AGE_RECIPIENT="$("$solo_age_keygen" -y ~/.config/solo-vps/age-key.txt)"
```

Приватный age-ключ остаётся только на вашем компьютере и в вашей отдельной резервной копии. На VPS его не копируем.

## 3. Зашифруйте Metrics credentials и передайте их на VPS

### Windows PowerShell

**На компьютере, в каталоге Solo VPS:**

```powershell
$ServerIp = 'YOUR_SERVER_IP'
$AdminUser = 'YOUR_ADMIN_USER'
.\scripts\windows\init-metrics-secrets.ps1
.\scripts\windows\test-metrics-secrets.ps1
.\scripts\windows\push-metrics-secrets.ps1 -VpsHost $ServerIp -VpsUser $AdminUser
```

Первая команда запросит:

```text
Grafana Cloud Prometheus remote write URL
Grafana Cloud Metrics user ID
Grafana Cloud access-policy token (metrics:write)
```

Токен при вводе скрыт. Если `metrics.enc.yaml` уже существует и подходит текущему age-ключу, helper проверит и переиспользует его без перезаписи.

**Ожидаемый результат:**

```text
PASS workstation-to-VPS metrics credential delivery
```

На VPS появляется `/etc/solo-vps/metrics/grafana-cloud.json` с владельцем `root:root` и режимом `0600`. Значения в терминал не печатаются.

Если для SSH нужен отдельный ключ, добавьте `-IdentityFile "$env:USERPROFILE\.ssh\your-admin-key"`.

### Компьютер с Linux

**На компьютере, в каталоге Solo VPS:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
make metrics-secrets-init
make metrics-secrets-check
make metrics-secrets-push METRICS_VPS_HOST="$SERVER_IP" METRICS_VPS_USER="$ADMIN_USER"
```

При необходимости добавьте `METRICS_SSH_IDENTITY_FILE="$HOME/.ssh/your-admin-key"`.

## 4. Запустите сбор метрик

**Подключитесь к VPS:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
ssh "${ADMIN_USER}@${SERVER_IP}"
```

**На VPS:**

```bash
cd ~/solo-vps
make verify-metrics-credentials
make metrics-runtime
make verify-metrics-runtime
```

`make metrics-runtime` проверит закреплённый Alloy, создаст отдельного non-root пользователя `solo-vps-metrics`, установит конфигурацию и запустит сервис. В Grafana отправляется небольшой набор host metrics: CPU, filesystem, load average, memory и базовая информация о системе.

Ожидайте в конце проверки:

```text
service: running/enabled
collector: prometheus.exporter.unix
remote_write: Grafana Cloud Metrics
```

Проверить сервис вручную можно так:

```bash
systemctl status solo-vps-metrics.service --no-pager
```

Входящий публичный порт для метрик не открывается. Локальный HTTP-интерфейс Alloy слушает только `127.0.0.1:12346`.

## 5. Убедитесь, что метрики появились в Grafana

Подождите примерно 1–2 минуты после первого запуска.

**В Grafana:**

1. Откройте **Drilldown → Metrics**.
2. В **Data source** выберите Prometheus-источник своего stack.
3. В правом верхнем углу поставьте диапазон хотя бы **Last 15 minutes** или **Last 1 hour**.
4. В поиске метрик введите `node_uname_info`.
5. Если метрика не появилась сразу, нажмите справа сверху кнопку с **круговыми стрелками ↻** рядом с диапазоном времени. Это обычное обновление запроса Grafana; перезапускать Alloy из-за этого не нужно.
6. Затем по очереди найдите:

```text
node_cpu_seconds_total
node_memory_MemAvailable_bytes
node_filesystem_avail_bytes
```

Можно добавить label filter:

```text
job = integrations/node_exporter
```

Если после первого запуска график показывает только одну точку, это нормально: collector только начал отправлять samples. Через несколько минут нажмите **↻ Refresh** ещё раз — история начнёт заполняться.

**Ожидаемый результат:** метрики находятся и показывают свежие точки времени для вашего VPS. Значение label `instance` должно быть hostname сервера, например `prod-001`.

[Metrics Drilldown](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/simplified-exploration/metrics/drill-down-metrics/) предназначен именно для такого поиска без PromQL. Если после обновления данных нужной метрики всё ещё нет, проверьте `make verify-metrics-runtime` на VPS.

## 6. Посмотрите три полезных процента

Drilldown удобен для поиска метрик. Для вычисляемых процентов используем **Explore**.

**В Grafana:** откройте **Explore**, выберите тот же Prometheus data source и переключите редактор запроса в **Code**. В этой главе `Code` нужен именно здесь, а не в Drilldown.

### CPU busy, %

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{job="integrations/node_exporter",mode="idle"}[5m])) * 100)
```

### Использованная память, %

```promql
100 * (1 - node_memory_MemAvailable_bytes{job="integrations/node_exporter"} / node_memory_MemTotal_bytes{job="integrations/node_exporter"})
```

### Использованный корневой диск, %

```promql
100 * (1 - node_filesystem_avail_bytes{job="integrations/node_exporter",mountpoint="/"} / node_filesystem_size_bytes{job="integrations/node_exporter",mountpoint="/"})
```

Выполняйте запросы по одному. Нас интересует не «красивый dashboard», а ответы на три вопроса: хватает ли CPU, памяти и диска.

!!! note "Почему пока без готового dashboard"
    Dashboard имеет смысл, когда вы уже понимаете, какие графики реально используете. Для первого релиза Solo VPS поддерживает маленький набор host metrics и один полезный alert, а не десятки панелей ради самих панелей.

## 7. Настройте email для алертов Grafana

В текущем Grafana Cloud email contact point может отправлять письма только на адрес пользователя, который состоит в вашей Grafana Cloud organization. Поэтому самый простой вариант для этой главы — использовать **тот же email, которым вы входите в Grafana Cloud**.

Если хотите отправлять alert на другой адрес, сначала добавьте его как участника организации:

1. откройте **Grafana Cloud Portal** на `grafana.com` — это портал аккаунта, а не интерфейс конкретного stack;
2. откройте **Org Settings → Members**;
3. нажмите **Invite New Member**;
4. укажите нужный email и роль **Viewer**;
5. примите приглашение из этого почтового ящика;
6. вернитесь в свой Grafana stack и обновите страницу.

!!! warning "Участник получает доступ к Grafana organization"
    Не добавляйте случайный общий почтовый ящик только ради alert, если не хотите давать ему доступ к Grafana. Для базовой главы используйте email уже существующего участника организации.

Теперь в самом Grafana stack откройте **Alerts & IRM → Alerting → Notification configuration → Contact points** и нажмите **Create contact point** / **New contact point**.

Заполните:

```text
Name: solo-vps-email
Integration: Email
Addresses: email существующего участника Grafana organization
```

Нажмите **Save contact point**. Затем нажмите **Test** и отправьте тестовое уведомление.

Ожидайте письмо. Отдельный SMTP-сервер на VPS не нужен. **Проверьте папки «Спам» / Junk:** первое письмо от Grafana может попасть туда. Если это произошло, отметьте письмо как «Не спам», чтобы не пропустить настоящий alert позже.

Если Grafana показывает ошибку примерно такого вида:

```text
Failed to save the contact point
Invalid receiver: invalid email ... addresses ... are not members of this organization
```

это **не проблема SMTP и не проблема Solo VPS**. Указанный адрес не является участником текущей Grafana Cloud organization. Используйте email своего текущего Grafana-пользователя или сначала добавьте нужный адрес через **Org Settings → Members**.

Не отключайте resolved messages: после тестового `Firing` нам понадобится и уведомление о восстановлении.

[Управление участниками Grafana Cloud](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/account-management/cloud-portal/) описывает путь **Org Settings → Members → Invite New Member**.

## 8. Проверьте настоящий disk alert без заполнения диска

Сейчас проверим настоящий путь `metric → alert rule → email`, но **не будем забивать диск файлами**. На несколько минут поставим заведомо тестовый порог свободного места `< 101%`. На любом нормальном диске свободного места меньше 101%, поэтому правило гарантированно сработает.

В этой инструкции используем **обычный упрощённый редактор Grafana**. Переключатель **Advanced options** в секции 2 оставьте **выключенным**. В этом режиме Grafana сама берёт последнее значение query и сравнивает его с порогом — отдельные `Reduce` и `Threshold` expressions создавать не нужно.

### 8.1. Откройте создание правила

Откройте:

**Alerts & IRM → Alerting → Alert rules → New alert rule**.

На странице будут пронумерованные секции `1`–`6`.

В секции **1. Enter alert rule name** укажите:

```text
solo-vps-root-disk-low
```

### 8.2. Вставьте запрос свободного места

В секции **2. Define query and alert condition**:

1. в левом выпадающем списке выберите Prometheus data source вашего stack — тот же `...-prom`, который использовали в Explore;
2. справа над полем запроса нажмите **Code**;
3. вставьте:

```promql
100 * node_filesystem_avail_bytes{job="integrations/node_exporter",mountpoint="/"} / node_filesystem_size_bytes{job="integrations/node_exporter",mountpoint="/"}
```

4. нажмите **Run queries**.

Query возвращает **процент свободного места** на корневом диске `/`. Если сейчас свободно 85%, результат будет примерно `85`.

Если результата нет, сначала проверьте этот же PromQL в **Explore**, затем нажмите **Run queries** ещё раз. Для alert rule нужен реальный результат query — пустое значение сохранять не надо.

### 8.3. Поставьте тестовый порог

Сразу **под query** находится маленький блок **Alert condition**. В текущем интерфейсе он выглядит примерно так:

```text
WHEN QUERY   IS ABOVE   0
```

Настройте именно эту строку:

1. `WHEN QUERY` оставьте как есть;
2. нажмите на **IS ABOVE** и выберите **IS BELOW**;
3. число `0` замените на `101`.

Должно получиться:

```text
WHEN QUERY   IS BELOW   101
```

Никаких `Rule A`, `Reduce`, `Threshold expression` и дополнительных query создавать **не нужно**.

Нажмите **Preview alert rule condition**. Поскольку свободного места всегда меньше 101%, preview должен показать, что условие выполняется.

### 8.4. Выберите папку

В секции **3. Add folder and labels** нужно выбрать folder — без него Grafana не сохранит правило.

Если подходящей папки ещё нет:

1. нажмите **New folder**;
2. создайте папку `Solo VPS`;
3. выберите её для правила.

Labels для первого правила можно не добавлять.

### 8.5. Настройте частоту проверки

В секции **4. Set evaluation behavior**:

1. в **Select an evaluation group** выберите существующую группу с интервалом `1m`;
2. если такой группы нет, нажмите **New evaluation group**, назовите её `solo-vps-1m` и задайте **Evaluation interval: 1m**;
3. в **Pending period** нажмите **None**;
4. в **Keep firing for** оставьте **None**.

Для теста нам нужно, чтобы rule перешёл в `Firing` сразу после ближайшей минутной проверки.

### 8.6. Выберите получателя

В секции **5. Configure notifications** найдите **Contact point** и выберите:

```text
solo-vps-email
```

Если `solo-vps-email` отсутствует в списке, не продолжайте: сначала закончите шаг 7 и добейтесь успешного **Test**.

Переключатель **Advanced options** здесь тоже не нужен.

### 8.7. Сохраните и дождитесь Firing

Секция **6. Configure notification message** необязательна. Для понятного письма можно заполнить:

```text
Summary: Solo VPS root disk has low free space
Description: Free space on / crossed the configured threshold.
```

Нажмите **Save** внизу страницы.

Затем:

1. откройте **Alerts & IRM → Alerting → Alert rules**;
2. найдите `solo-vps-root-disk-low`;
3. подождите ближайшую evaluation — при интервале `1m` обычно достаточно одной-двух минут;
4. убедитесь, что состояние стало **Firing**;
5. дождитесь email на `solo-vps-email`; если его нет во входящих, обязательно проверьте папки **«Спам» / Junk**.

Если состояние не обновляется, нажмите кнопку **↻ Refresh** в интерфейсе Grafana и проверьте правило снова.

!!! warning "101% — только тест"
    Это специально неправильный production-порог, чтобы безопасно доказать доставку alert. Не оставляйте его после проверки.

### 8.8. Верните нормальный production-порог

После получения тестового письма откройте это же правило на редактирование.

В секции **2** измените только число в строке Alert condition:

```text
WHEN QUERY   IS BELOW   15
```

В секции **4** измените:

```text
Pending period: 5m
Keep firing for: None
```

Сохраните правило.

При обычном состоянии VPS, где на `/` свободно больше 15%, после следующей evaluation правило должно вернуться в **Normal**. Если resolved messages включены, Grafana также отправит сообщение о восстановлении. Такое письмо тоже может попасть в **«Спам» / Junk**.

Если на VPS уже меньше 15% свободного места, это не тестовая ошибка — сначала освободите место или увеличьте диск.

**Итоговый смысл правила:** предупредить, если на `/` остаётся меньше 15% свободного места не кратковременно, а минимум пять минут подряд.

## 9. Что смотреть потом

Для обычной проверки:

```bash
cd ~/solo-vps
make verify-metrics-runtime
```

В Grafana начинайте с **Drilldown → Metrics** и смотрите CPU, память и filesystem. В Explore переходите только когда нужен вычисляемый запрос или точное сравнение.

Не добавляйте alert на каждую метрику. Полезный alert должен означать конкретное действие. Например:

- мало места на `/` → найти растущие данные/логи и освободить место или увеличить диск;
- память стабильно близка к пределу → найти потребителя и решить, нужен ли больший VPS;
- CPU долго держится высоким → проверить нагрузку приложения и контейнеры.

Application-level метрики вроде числа HTTP `500`, latency или очередей требуют instrumentation самого приложения и **не входят** в эту базовую главу.

## Если метрик нет

**На VPS:**

```bash
cd ~/solo-vps
make verify-metrics-credentials
make verify-metrics-runtime
sudo journalctl -u solo-vps-metrics.service -n 100 --no-pager
```

Проверьте также, что в Grafana выбран **Prometheus**, а не Loki data source, и диапазон времени включает последние несколько минут.

Если Grafana отвечает `401`/`403`, заново проверьте Metrics User ID и что token имеет `metrics:write`. Не расширяйте token до admin-доступа ради устранения ошибки.

## Готово

Глава завершена, когда одновременно подтверждены четыре вещи:

1. `make verify-metrics-runtime` проходит без ошибок;
2. CPU, memory и filesystem metrics видны в **Drilldown → Metrics**;
3. тестовое письмо contact point приходит;
4. `solo-vps-root-disk-low` реально переходил в `Firing`, письмо пришло, после установки production-порога `15%` правило вернулось в нормальное состояние.

Теперь у сервера есть не только логи и внешний uptime-monitor: вы видите постепенное исчерпание ресурсов до того, как оно превратится в сбой.
