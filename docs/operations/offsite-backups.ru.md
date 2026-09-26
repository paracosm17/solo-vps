# 6. Вынесите резервные копии за пределы VPS

Локальный backup из главы 4 помогает после ошибки приложения или неудачной миграции. Если пропадёт сам VPS или его диск, локальная копия пропадёт вместе с ним.

В этой главе создадим внешнее S3-compatible хранилище и положим туда три разные части восстановления:

<div class="solo-delivery-flow" role="list" aria-label="Что хранится вне VPS">
  <div role="listitem"><span>1</span><div><strong>PostgreSQL · Coolify</strong><p>Logical backup данных приложения отправляется в Backblaze B2.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Coolify · control plane</strong><p>Отдельный backup сохраняет проекты, ресурсы, настройки и историю деплоев.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Solo VPS · restic</strong><p>Зашифрованный snapshot сохраняет нужные файлы /data/coolify вне сервера.</p></div></div>
  <div role="listitem"><span>4</span><div><strong>Ключи · вне VPS</strong><p>APP_KEY и age identity хранятся отдельно от сервера и самого bucket.</p></div></div>
</div>

Для основного маршрута используем **Backblaze B2**: это managed object storage с S3-compatible API. Для старта B2 не требует банковскую карту, а первые 10 GB хранилища бесплатны. Второй VPS не нужен.

Если Backblaze вам не подходит, [Cloudflare R2](../backup-storage-cloudflare-r2.md) остаётся поддерживаемой альтернативой. Основная глава использует B2, чтобы базовый путь не зависел от привязки международной карты.

## Перед началом

Нужны:

- работающий Coolify из главы 1;
- тестовая PostgreSQL из главы 4;
- локальная копия `solo-vps` на компьютере;
- age/SOPS setup из главы 3;
- аккаунт Backblaze B2.

Если тестовую БД из главы 4 уже удалили, сначала повторите её шаги 1–2. Restore в этой главе снова выполняем только в отдельную disposable БД.

Один приватный B2 bucket можно использовать и для Coolify, и для restic: они создают разные object paths. Для более строгого разделения позже можно использовать отдельные bucket/key.

## 1. Создайте аккаунт и приватный bucket в Backblaze B2

Откройте Backblaze и создайте бесплатный аккаунт B2 Cloud Storage. Банковская карта для старта не нужна.

При регистрации выберите регион аккаунта. Если VPS находится в Европе, выбирайте европейский регион, когда он доступен. Регион привязывается к аккаунту, поэтому потом bucket использует endpoint именно этого региона.

После входа откройте **B2 Cloud Storage → Buckets → Create a Bucket**.

Заполните:

| Настройка | Значение |
| --- | --- |
| Bucket name | уникальное имя, например `solo-vps-backups-abc123` |
| Files in Bucket are | `Private` |
| Object Lock | не включайте для первого теста |

Публичный bucket нам не нужен.

После создания bucket скопируйте **Endpoint**, который показывает Backblaze. Он выглядит примерно так:

```text
s3.<REGION>.backblazeb2.com
```

Для Coolify и Solo VPS используйте его с `https://`:

```text
https://s3.<REGION>.backblazeb2.com
```

Сохраните также `<REGION>` — это часть endpoint между `s3.` и `.backblazeb2.com`.

## 2. Создайте Application Key только для backup bucket

Откройте **B2 Cloud Storage → Application Keys → Add a New Application Key**.

Используйте:

| Поле | Значение |
| --- | --- |
| Name of Key | `solo-vps-backups` |
| Allow Access to Bucket(s) | только созданный backup bucket |
| Type of Access | `Read and Write` |
| Allow List All Bucket Names | включить |
| File Name Prefix | оставить пустым |
| Duration | оставить пустым для постоянного ключа |

`Allow List All Bucket Names` нужен для совместимости с S3-клиентами и проверками подключения, но сам ключ остаётся ограничен выбранным bucket для работы с объектами.

Нажмите **Create New Key** и сохраните в password manager:

- **keyID** — это наш `Access Key ID`;
- **applicationKey** — это наш `Secret Access Key`.

`applicationKey` показывается только при создании. Не добавляйте эти значения в Git и не присылайте их в чат.

## 3. Подключите Backblaze B2 к Coolify

В Coolify откройте **S3 Storages → Add**.

Заполните:

| Поле | Значение |
| --- | --- |
| Name | `solo-vps-b2` |
| Endpoint | `https://s3.<REGION>.backblazeb2.com` из bucket |
| Bucket | точное имя B2 bucket |
| Region | `<REGION>` из endpoint, например `us-west-004` |
| Access Key | Backblaze `keyID` |
| Secret Key | Backblaze `applicationKey` |

Нажмите **Validate Connection & Continue**.

Не продолжайте, пока Coolify не подтвердит успешное подключение. Если получите `403`, сначала проверьте, что Application Key создан с **Read and Write**, ограничен нужным bucket и у него включён **Allow List All Bucket Names**.

## 4. Отправьте PostgreSQL backup в B2

Откройте существующий schedule:

**`solo-vps-db-demo → Backups`**.

В секции **S3**:

1. включите **S3**;
2. выберите `solo-vps-b2`;
3. оставьте **Disable Local Backup** выключенным;
4. задайте разумный S3 retention, например `7` копий;
5. нажмите **Save**.

Теперь добавим запись, которая должна попасть именно во внешнюю копию.

Откройте Terminal исходной БД и выполните:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "DELETE FROM solo_vps_backup_probe WHERE id IN (3,4); INSERT INTO solo_vps_backup_probe VALUES (3, 'before-offsite'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Убедитесь, что есть строка:

```text
3|before-offsite
```

Вернитесь в **Backups** и нажмите **Backup Now**.

Нужен результат:

```text
Success
Backup Availability: Local Storage, S3 Storage
```

`Success (S3 Warning)` не считается успехом этой главы: это означает, что локальный dump получился, а внешняя копия — нет.

Откройте **Backblaze → B2 Cloud Storage → Buckets → ваш bucket → Browse Files**. В нём должен появиться новый объект Coolify backup.

## 5. Восстановите PostgreSQL прямо из S3

Сначала измените исходную БД **после** созданного внешнего backup:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "INSERT INTO solo_vps_backup_probe VALUES (4, 'after-offsite'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Теперь источник содержит `4|after-offsite`, а объект в B2 был создан раньше.

Создайте в Coolify **новую пустую** PostgreSQL **той же major version**, например `solo-vps-db-offsite-restore`. Не подключайте к ней приложение. Для каждой проверки восстановления используйте новую одноразовую БД. Coolify запускает `pg_restore`, не очищая существующие таблицы: ошибки `relation already exists` или `duplicate key` означают неудачное восстановление, хотя окно подтверждения предупреждает о замене данных.

Откройте **Configuration → Import Backup**.

Если интерфейс показывает восстановление из S3:

1. выберите **S3 storage**, затем `solo-vps-b2`;
2. в **Backblaze → Browse Files** скопируйте полный ключ загруженного объекта. Он выглядит как `data/coolify/backups/databases/.../pg-dump-....dmp`. Если копируете путь из **Backups → Executions** в Coolify, уберите только первый `/`;
3. вставьте ключ в **File path**, нажмите **Check File** и убедитесь, что Coolify показывает **File found in S3** и размер больше нуля;
4. нажмите **Restore From S3** и подтвердите восстановление в пустую одноразовую БД паролем своего аккаунта Coolify.

Это основной путь: Coolify читает внешний backup прямо из B2, локальный `.dmp` на компьютере не нужен. Перед проверкой строк убедитесь, что в выводе восстановления нет ошибок `pg_restore`.

Если в вашей версии Coolify нет S3-варианта, скачайте `.dmp` в **Backblaze → Browse Files** и используйте **Restore from File → Restore Database from File**.

В Terminal восстановленной БД выполните:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "SELECT id, value FROM solo_vps_backup_probe WHERE id IN (3,4) ORDER BY id;"
```

Ожидайте только:

```text
3|before-offsite
```

Строки `4|after-offsite` быть не должно. Теперь доказано, что внешний S3 backup восстанавливает именно сохранённую точку данных.

Для дополнительной проверки независимого доступа можно один раз скачать этот же `.dmp` напрямую из Backblaze. Это полезно, но не обязательно, если прямой S3 restore уже прошёл.

## 6. Сделайте внешний backup самой панели Coolify

Backup PostgreSQL приложения **не содержит состояние Coolify**: проекты, resources, настройки и сохранённые credentials живут в собственной БД панели.

В Coolify откройте **Settings → Backup**.

Если показана кнопка **Configure Backup**, нажмите её. Если Coolify просит сначала проверить localhost server, выполните **Validate Server** и вернитесь в Backup.

В Scheduled Backup:

1. включите **Backup Enabled**;
2. оставьте ежедневное расписание;
3. включите **S3 Enabled**;
4. выберите `solo-vps-b2`;
5. оставьте **Disable Local Backup** выключенным;
6. сохраните настройки;
7. нажмите **Backup Now**.

Execution должен завершиться как **Success**, а в **Backup Availability** должна присутствовать **S3 Storage**.

Откройте B2 bucket и убедитесь, что появился отдельный backup Coolify instance.

## 7. Сохраните APP_KEY вне VPS

Coolify шифрует сохранённые secrets своим `APP_KEY`. Один `.dmp` панели без этого ключа недостаточен для полноценного восстановления credentials.

**На VPS под настроенным администратором:**

```bash
sudo grep '^APP_KEY=' /data/coolify/source/.env
```

Скопируйте **всю строку `APP_KEY=...`** в password manager или другое защищённое хранилище вне VPS.

`APP_KEY` — секрет. Команда выше специально показывает его только для переноса в password manager. Не вставляйте этот вывод в issue, чат, публичный лог или скриншот; в evidence всегда редактируйте значение.

Не сохраняйте его в Git, B2 bucket как обычный текстовый файл или заметку внутри самого VPS.

## 8. Укажите B2 repository в Solo VPS

Coolify backups и restic — разные механизмы. Теперь используем тот же private bucket для зашифрованного filesystem snapshot.

**На VPS под настроенным администратором:**

```bash
cd ~/solo-vps
nano ~/.local/share/solo-vps/config/config.yml
```

В файле уже есть секция `backup`. **Измените существующий `backup.repository`, не добавляйте второй top-level `backup:`.**

```yaml
backup:
  repository:
    endpoint: https://s3.<REGION>.backblazeb2.com
    bucket: <BUCKET_NAME>
    prefix: solo-vps
    region: <REGION>
```

Используйте точные endpoint и region из Backblaze bucket.

Сохраните файл и выполните:

```bash
make check-backup-policy
make backup-tooling
make verify-backup-tooling
make backup-readiness
```

`backup-readiness` проверяет локальный scope и настройки, но ещё ничего не записывает в B2.

## 9. Подготовьте restic credentials на компьютере

Для этой главы **не создавайте новый age key**. Используйте тот же ключ, который уже работает после главы 3.

**Windows PowerShell, в локальной папке `solo-vps`:**

```powershell
.\scripts\windows\init-sops-policy.ps1
.\scripts\windows\init-backup-secrets.ps1
.\scripts\windows\test-backup-secrets.ps1
```

`init-backup-secrets.ps1` попросит:

- Access Key ID — Backblaze `keyID`;
- Secret Access Key — Backblaze `applicationKey`;
- использует ли provider session token — для обычного Backblaze B2 ответьте `N`.

Restic repository password генерируется автоматически и сохраняется только внутри SOPS-encrypted bundle.

Передайте credentials на VPS:

```powershell
$ServerIp = 'YOUR_SERVER_IP'
$AdminUser = 'YOUR_ADMIN_USER'
.\scripts\windows\push-backup-secrets.ps1 -VpsHost $ServerIp -VpsUser $AdminUser
```

**На VPS:**

```bash
cd ~/solo-vps
make verify-backup-credentials
```

Ни Access Key, ни Secret Access Key, ни restic password в выводе появляться не должны.

## 10. Создайте restic repository и первый snapshot

**На VPS под настроенным администратором:**

```bash
make backup-runtime
make verify-backup-runtime
```

Выберите **ровно одну** команду для repository. Не запускайте обе подряд.

Если этого restic repository ещё никогда не было:

```bash
make backup-repository-init
```

После `PASS restic repository initialized` сразу переходите к snapshot — `backup-repository-adopt` больше не нужен.

Если вы повторно проходите главу и repository уже существует с теми же credentials/password, используйте **вместо init**:

```bash
make backup-repository-adopt
```

После успешной инициализации **или** adoption создайте snapshot:

```bash
make backup-now
make backup-status
```

B2 теперь содержит restic repository под prefix `solo-vps/<server-hostname>/`. Имена его объектов выглядят технически — это нормально; редактировать их вручную не нужно.

В одном bucket теперь нормально видеть две независимые ветки:

```text
data/coolify/backups/...              Coolify: PostgreSQL и backup панели
solo-vps/<hostname>/config            restic repository metadata
solo-vps/<hostname>/{data,index,keys,locks,snapshots}
                                      внутренние объекты restic
```

Не удаляйте отдельные `config`, `data`, `index`, `keys`, `locks` или `snapshots` через Backblaze UI. Управляйте restic repository только командами Solo VPS/restic.

## 11. Проверьте реальное восстановление restic

Snapshot считается полезным только после restore-test.

```bash
make backup-restore-test
```

Solo VPS восстановит последний snapshot во временный приватный каталог под `/var/tmp`, проверит ожидаемый `/data/coolify` scope и затем удалит test tree.

Нужен результат:

```text
PASS Solo VPS filesystem recovery-material restore test
```

Эта проверка **не накладывает** backup поверх работающего Coolify.

## 12. Включите ежедневный restic backup

Только после успешного restore-test:

```bash
make backup-schedule-enable
```

Проверьте timer:

```bash
systemctl list-timers solo-vps-backup.timer --no-pager
```

По умолчанию backup запускается ежедневно примерно в `03:15` с небольшим случайным сдвигом.

## 13. Сохраните age private key отдельно от компьютера

SOPS-encrypted `backup.enc.yaml` содержит credentials и restic password, но открыть его можно только вашим age private key.

На Windows ключ находится здесь:

```text
%USERPROFILE%\.config\solo-vps\age-key.txt
```

Сделайте **защищённую резервную копию этого файла вне VPS и вне единственного компьютера**: например, encrypted attachment в password manager или зашифрованный внешний носитель.

Не печатайте содержимое ключа в терминал ради этой проверки и не загружайте его в Git/B2 как обычный файл.

## Что теперь защищено

| Что потерялось | Откуда восстанавливать |
| --- | --- |
| данные PostgreSQL приложения | Coolify `.dmp` в B2 |
| проекты/settings/history Coolify | Coolify instance `.dmp` в B2 + сохранённый `APP_KEY` |
| нужные файлы `/data/coolify` | encrypted restic repository в B2 |
| restic/S3 credentials | SOPS-encrypted `backup.enc.yaml` + отдельная копия age private key |
| код приложения | Git repository / опубликованный image |

Restic **не делает raw backup живого PostgreSQL data directory**. Для БД используйте logical backups Coolify, которые мы отдельно проверили восстановлением.

Полная потеря VPS ещё не проверена: для неё нужен отдельный replacement server. Мы сделаем этот destructive exercise позже на disposable VPS, а не на рабочем сервере.

**Готово:** глава завершена, если PostgreSQL backup восстановлен напрямую из B2 в пустую тестовую БД (или скачан и восстановлен запасным способом через файл), Coolify instance backup виден в B2, `make backup-restore-test` прошёл, а ежедневный restic timer включён.

## Альтернативные S3-провайдеры

Основной маршрут этой главы — Backblaze B2. Если он недоступен в вашей стране или аккаунте, можно использовать другой S3-compatible provider с private bucket, bucket-scoped credentials и внешним failure domain.

Готовая альтернативная инструкция: [Cloudflare R2](../backup-storage-cloudflare-r2.md).
