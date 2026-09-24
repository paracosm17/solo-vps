# 4. Сделайте и восстановите резервную копию PostgreSQL

После этой главы вы будете знать не только то, что backup job стала зелёной, а что **конкретные данные действительно восстанавливаются**.

Сначала проверим локальную копию на том же VPS. Это защищает от ошибки приложения, неудачной миграции или случайного удаления данных. От потери самого VPS такая копия **не защищает** — внешнее хранилище добавим отдельно.

<div class="solo-delivery-flow" role="list" aria-label="Как проверяется резервная копия PostgreSQL">
  <div role="listitem"><span>1</span><div><strong>PostgreSQL · VPS</strong><p>Создаём узнаваемую тестовую запись.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Coolify Backups · VPS</strong><p>Coolify делает logical backup и хранит локальную копию.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Отдельная PostgreSQL · VPS</strong><p>Восстанавливаем backup в пустую тестовую БД и проверяем данные.</p></div></div>
</div>

## Перед началом

Нужен уже работающий Coolify из главы 1. Для первого упражнения **не используйте production-базу как restore target**.

Если у приложения PostgreSQL ещё нет, это нормально: создайте временную БД специально для проверки этой главы. Внешний порт открывать не нужно — всё упражнение выполняется внутри Coolify.

В примерах используются два ресурса:

- `solo-vps-db-demo` — исходная тестовая база;
- `solo-vps-db-restore` — отдельная база, куда мы восстановим backup.

После проверки второй ресурс можно удалить.

## 1. Создайте тестовую PostgreSQL

**В Coolify:**

1. Откройте проект и environment, где находится демо-приложение.
2. Нажмите **New Resource → Databases → PostgreSQL**.
3. Выберите тот же сервер и destination.
4. Используйте обычный PostgreSQL без дополнительных расширений и запомните выбранную **major version** — для restore создадим такую же.
5. Назовите ресурс `solo-vps-db-demo`.
6. Не включайте публичный доступ к БД.
7. Нажмите **Start** и дождитесь состояния Running/Healthy.

Coolify создаёт отдельный persistent volume для данных. Он переживает обычное пересоздание контейнера, но сам по себе backup не заменяет. [Официальное описание PostgreSQL в Coolify](https://coolify.io/docs/databases/postgresql) объясняет этот lifecycle.

## 2. Запишите данные, которые легко проверить

Откройте **Terminal** у `solo-vps-db-demo`. Если вкладки Terminal у ресурса нет, используйте общий **Terminal** в боковом меню и выберите контейнер этой PostgreSQL.

Выполните:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "CREATE TABLE IF NOT EXISTS solo_vps_backup_probe (id integer PRIMARY KEY, value text NOT NULL); TRUNCATE solo_vps_backup_probe; INSERT INTO solo_vps_backup_probe VALUES (1, 'before-backup'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Ожидайте:

```text
1|before-backup
```

Эта строка — наш контрольный факт. После backup мы изменим исходную БД, а восстановленная копия должна остаться в состоянии `before-backup`.

## 3. Настройте локальный backup

Откройте `solo-vps-db-demo → Backups` и нажмите **Add** рядом с Scheduled Backups.

Для первого рабочего варианта задайте:

| Настройка | Значение |
| --- | --- |
| Frequency | `daily` |
| Enabled | включено |
| S3 | выключено |
| Disable Local Backup | выключено, если поле показано |
| Number of backups to keep | `7` |
| Days to keep backups | `0` |
| Maximum storage (GB) | `0` |
| Timeout | оставьте стандартный `3600` |

`0` в ограничениях по дням и размеру означает «не ограничивать этим правилом»; в нашем примере локальную историю ограничивает количество — семь последних копий.

Для PostgreSQL оставьте поле выбора баз пустым, если хотите копировать database, настроенную у этого ресурса. Не включайте **Backup All Databases** для этого упражнения.

Сохраните schedule. Coolify создаёт engine-aware PostgreSQL backup через `pg_dump`, а локальный файл хранит на сервере под `/data/coolify/backups`. Вручную собирать путь не нужно — используйте данные конкретного execution. [Поля schedule и retention описаны в документации Coolify](https://coolify.io/docs/databases/backups).

## 4. Сделайте backup прямо сейчас

В созданном schedule нажмите **Backup Now**.

Дождитесь нового execution и откройте его. Проверьте:

- статус **Success**;
- размер файла больше `0`;
- указана нужная database;
- доступна **Local Storage**;
- S3 не требуется и в этой главе остаётся выключенным.

Скачайте эту копию на компьютер кнопкой **Download**. Это не делает её полноценным off-site backup-процессом, но даёт простой файл для независимого restore-упражнения.

**Не переходите дальше, если execution Failed или файл имеет нулевой размер.**

## 5. Измените исходную БД после backup

Вернитесь в Terminal `solo-vps-db-demo` и выполните:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "INSERT INTO solo_vps_backup_probe VALUES (2, 'after-backup'); SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Ожидайте уже две строки:

```text
1|before-backup
2|after-backup
```

Теперь источник ушёл вперёд относительно backup. Это позволит доказать, что restore возвращает именно сохранённое состояние, а не просто подключается к текущей БД.

## 6. Создайте отдельную БД для восстановления

Создайте второй ресурс **PostgreSQL** тем же способом, что в шаге 1:

- имя: `solo-vps-db-restore`;
- тот же сервер и destination;
- та же PostgreSQL **major version**;
- без публичного порта.

Запустите его и дождитесь Running/Healthy. В эту БД не добавляйте тестовую таблицу вручную.

## 7. Восстановите скачанный backup

Откройте `solo-vps-db-restore → Configuration → Import Backup`.

1. Выберите **Restore from File**.
2. Загрузите файл, скачанный в шаге 4.
3. Для обычного backup одной PostgreSQL database оставьте **Backup includes all databases** выключенным.
4. Для custom-format backup оставьте стандартную команду с `pg_restore`, если вы её не меняли в source resource.
5. Нажмите **Restore Database from File**.
6. В destructive confirmation внимательно убедитесь, что target — именно `solo-vps-db-restore`, а не исходная база.
7. Дождитесь окончания **Database Restore Output** без ошибки.

Встроенный Import Backup действительно изменяет целевую БД, поэтому restore всегда проверяйте на disposable target. [Текущий workflow Restore from File описан Coolify здесь](https://coolify.io/docs/databases/restore).

## 8. Проверьте восстановленные данные

Откройте Terminal у `solo-vps-db-restore` и выполните:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -Atc "SELECT id, value FROM solo_vps_backup_probe ORDER BY id;"
```

Правильный результат:

```text
1|before-backup
```

Строки `2|after-backup` здесь быть **не должно**: мы создали её уже после backup.

Для контроля исходная `solo-vps-db-demo` по-прежнему должна показывать обе строки. Так мы доказали сразу три вещи: backup содержит данные, restore реально выполняется, а восстановлена именно нужная точка во времени.

## Если что-то не получилось

| Что видно | Что проверить |
| --- | --- |
| Backup Now не создаёт execution | PostgreSQL должна быть запущена; проверьте schedule и database scope |
| Execution Failed | Откройте сообщение execution; проверьте credentials ресурса и timeout |
| `Permission denied` для `/data/coolify/backups/...` | На VPS из `~/solo-vps` выполните `make coolify`, затем `make verify-coolify` и повторите **Backup Now**. Не делайте `chmod -R`/`chown -R` для `/data/coolify` вручную |
| Backup Success, но нет Local Storage | Убедитесь, что **Disable Local Backup** выключен |
| Restore не принимает файл | Убедитесь, что это backup PostgreSQL, а target использует совместимую major version |
| `pg_restore` сообщает о существующих объектах | Restore target должен быть отдельным и не содержать ваших application tables |
| После restore нет таблицы | Проверьте, какую database копировал schedule и к какой `$POSTGRES_DB` подключён Terminal |
| В restored DB есть `after-backup` | Вы выбрали более новый backup или сделали Backup Now уже после второй вставки |

Не удаляйте исходную БД и не восстанавливайте поверх неё только ради проверки инструкции.

## Готово: локальный restore доказан

Оставьте schedule включённым, если эта БД нужна приложению. Периодически проверяйте **Executions**, а после важных изменений схемы повторяйте restore exercise на отдельной БД.

Локальная копия всё ещё находится на том же VPS. Потеря диска или сервера может уничтожить и database, и эти backup-файлы одновременно. Для ценных данных следующий обязательный шаг — копия вне VPS.

**Дальше:** пройдите [главу 5 — внешние уведомления о недоступности](external-uptime.md). После неё перейдём к копиям вне VPS и восстановлению после потери сервера.
