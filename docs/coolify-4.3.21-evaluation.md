# Испытание Coolify 4.3.21 и Sentinel

Это лист испытаний для владельца Solo VPS. Он нужен один раз перед изменением поддерживаемой версии Coolify и намеренно не публикуется на пользовательском сайте.

Используйте только новый или специально очищенный Ubuntu 24.04 VPS. Не запускайте команды обновления на основном сервере. Текущий поддерживаемый контракт Solo VPS остаётся `4.1.1 → 4.1.2`, пока весь сценарий ниже не завершится успешно.

## Что именно проверяем

Кандидат — Coolify `4.3.21`. Переход пересекает изменение `4.3.19`, после которого Sentinel обязателен для обычных серверов. Sentinel — контейнер-агент Coolify: он отправляет в панель состояние сервера и контейнеров, а при включённых метриках хранит историю CPU/RAM.

Sentinel не переводит VPS в особый «sentinel mode». Но это привилегированный компонент: контейнер использует host PID namespace и Docker socket в режиме read-write. Поэтому мы принимаем его только внутри уже существующей границы доверия Coolify и отдельно доказываем, что его API не опубликован в интернет.

Официальные источники:

- [Coolify 4.3.19: Sentinel стал обязательным](https://github.com/coollabsio/coolify/releases/tag/v4.3.19);
- [Coolify 4.3.21](https://github.com/coollabsio/coolify/releases/tag/v4.3.21);
- [как работает Sentinel](https://coolify.io/docs/core/observability/monitoring/sentinel);
- [правила обновления Coolify](https://coolify.io/docs/core/instance-management/update).

## Результат до начала

До этого испытания должны быть готовы:

- одноразовый VPS, который можно полностью удалить;
- отдельный тестовый домен панели, например `https://coolify-lab.example.com`;
- чистый checkout точного candidate commit Solo VPS;
- отдельные тестовые credentials для DNS, GitHub/GHCR, object storage и мониторинга;
- приложение с простым публичным health endpoint и тестовой записью в PostgreSQL.

Не используйте production DNS, production buckets или секреты основного VPS.

Сначала создайте отдельный controller state. Эти переменные должны оставаться экспортированными во всём испытании:

```bash
export COOLIFY_EVALUATION_TARGET_ID=coolify-4321-lab
export COOLIFY_EVALUATION_DATA_DIR="$HOME/.local/share/solo-vps-evaluation-${COOLIFY_EVALUATION_TARGET_ID}"
export SOLO_VPS_DATA_DIR="$COOLIFY_EVALUATION_DATA_DIR"

make coolify-evaluation-init
make paths
```

В выводе `make paths` пути `config`, `inventory`, `state` и `secrets` должны находиться внутри `solo-vps-evaluation-coolify-4321-lab`, а не внутри обычного `~/.local/share/solo-vps`. Evaluation-команды откажутся работать без marker, связывающего этот каталог с `COOLIFY_EVALUATION_TARGET_ID`.

## 1. Поднимите исходное состояние 4.1.2

На рабочей станции пройдите главы 1 и 2 публичной документации до конца. Не обновляйте Coolify кнопкой в панели. Ожидаемый результат:

- `make verify-coolify` проходит;
- панель показывает Coolify `4.1.2`;
- raw-порты `8000`, `6001` и `6002` доступны только через loopback на VPS;
- тестовое приложение открывается по HTTPS;
- в приложении сохранена контрольная запись, которую можно проверить после обновления.

Запишите candidate commit и время начала испытания в заметки. Секреты и содержимое `.env` туда не копируйте.

## 2. Настройте HTTPS-путь Sentinel до обновления

В панели Coolify `4.1.2`:

1. Откройте **Settings → Configuration → General**.
2. Убедитесь, что Instance URL равен публичному HTTPS URL тестовой панели, например `https://coolify-lab.example.com`.
3. Откройте **Servers → localhost → Sentinel → Configuration**.
4. В поле **Coolify URL** укажите тот же HTTPS URL без credentials.
5. Оставьте debug выключенным. Metrics можно оставить выключенными: heartbeat Sentinel от них не зависит.
6. Сохраните настройки, нажмите **Enable Sentinel**, затем **Sync** или **Restart**.
7. Дождитесь статуса **Sentinel In Sync**.

Не указывайте `http://host.docker.internal:8000`: Solo VPS намеренно держит port `8000` на loopback, и контейнер через Docker bridge до него не дойдёт. Не публикуйте `8000` или `8888` ради исправления связи.

## 3. Запустите read-only preflight

В том же checkout на рабочей станции задайте URL панели. `COOLIFY_EVALUATION_TARGET_ID`, `COOLIFY_EVALUATION_DATA_DIR` и `SOLO_VPS_DATA_DIR` уже экспортированы на подготовительном шаге:

```bash
export COOLIFY_SENTINEL_URL=https://coolify-lab.example.com
```

`COOLIFY_EVALUATION_TARGET_ID` — произвольная метка этого disposable VPS, а не IP, hostname или credential.

Затем выполните:

```bash
make coolify-evaluate-4-3-21-preflight
```

Ожидаемый результат — `PASS` без изменений на сервере. Проверка подтверждает:

- исходную версию `4.1.2` и допустимый upgrade path;
- точные release artifacts `4.3.21` и их SHA-256;
- работающий Sentinel и точный HTTPS push endpoint;
- наличие token без вывода его значения;
- host PID namespace и read-write Docker socket как явно принятую upstream-модель;
- отсутствие опубликованного Sentinel API на port `8888`.

Если preflight завершился ошибкой, не переходите дальше. Сохраните только безопасный вывод команды и исправьте причину в candidate source.

## 4. Подготовьте точку восстановления

Убедитесь, что нет активных deployments. Затем:

```bash
make backup-now
make backup-check
make backup-restore-test
```

В панели Coolify запустите **Backup Now** для PostgreSQL тестового приложения. Требуйте **Success**, **S3 Available** и реальный объект в отдельном B2 bucket. Восстановите этот объект прямо из S3 в новую пустую PostgreSQL той же major version и проверьте контрольные строки по [главе о внешних копиях](operations/offsite-backups.md). API helper `database-backup-trigger`/`verify` сейчас не подходит для 4.3.21: API не раскрывает проверяемое соответствие между `s3_storage_id` и UUID, поэтому helper останавливается; не засчитывайте его как PASS.

Проверьте свежий instance backup Coolify в панели и запишите идентификаторы последних off-site snapshot и database backup. Не копируйте пароли или access keys.

## 5. Докажите восстановление прерванного обновления

Первый запуск намеренно остановится сразу после создания локального checkpoint и защищённого transaction marker, но до замены release files:

```bash
COOLIFY_EVALUATION_CONFIRM=I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_4_3_21_TARGET \
COOLIFY_EVALUATION_INTERRUPT_AFTER_MARKER=true \
make coolify-evaluate-4-3-21-upgrade
```

Ожидаемый результат — ненулевой exit code и сообщение `EXPECTED EVALUATION INTERRUPTION`. Это запланированный отказ, а не дефект.

Сразу выполните только read-only проверку marker:

```bash
ssh "${ADMIN_USER}@${SERVER_IP}" 'sudo test -s /data/coolify/.solo-vps-upgrading && echo marker-present'
```

Ожидаемый вывод: `marker-present`. Не удаляйте marker вручную и не пытайтесь делать downgrade.

Продолжите forward-only recovery:

```bash
COOLIFY_EVALUATION_CONFIRM=I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_4_3_21_TARGET \
make coolify-evaluate-4-3-21-resume
```

Ожидаемый результат — успешное завершение, версия `4.3.21`, здоровый Sentinel `1.0.1` и удалённый transaction marker.

## 6. Проверьте кандидат после обновления

Сначала выполните автоматические проверки:

```bash
make verify-coolify-4-3-21-candidate
make audit
```

На candidate checkout обычный `make verify` всё ещё проверяет поддерживаемый pin `4.1.2`, поэтому после перехода на `4.3.21` он ожидаемо останавливается на проверке версии. Это не результат candidate gate. После полного `PASS`, отдельного изменения поддерживаемых pins и пользовательской документации повторите `make verify` на том же disposable VPS перед его удалением.

Затем проверьте вручную:

1. Панель открывается по HTTPS и показывает `4.3.21`.
2. **Servers → localhost** показывает **Sentinel In Sync**.
3. Тестовое приложение отвечает по HTTPS, а контрольная запись PostgreSQL сохранилась.
4. Новый commit тестового приложения проходит GitHub Actions и разворачивается через штатный CI/CD путь.
5. Live logs видны; retained logs продолжают поступать после redeploy.
6. Host metrics и alert delivery работают независимо от того, включена ли история метрик Sentinel.
7. `make backup-now`, `make backup-check`, `make backup-restore-test` проходят; новый backup PostgreSQL показывает **Success** и **S3 Available**, объект есть в B2, а прямой restore в новую пустую тестовую БД проходит без ошибок `pg_restore`.
8. С внешней машины `SERVER_IP:8000`, `:6001`, `:6002` и `:8888` недоступны.

Любой неожиданный открытый port, `Sentinel Out of Sync`, потеря данных, сломанный deploy или неработающий forward resume означает `FAIL`. Основной VPS при этом остаётся на `4.1.2`.

## 7. Зафиксируйте результат и завершите проверку pins

Сохраните sanitised evidence:

- candidate commit;
- provider image и регион disposable VPS;
- время начала и окончания;
- PASS/FAIL каждой секции;
- версии Coolify и Sentinel;
- безопасный JSON-отчёт Sentinel из Ansible;
- идентификаторы backup/snapshot без credentials;
- список найденных дефектов.

После полного candidate `PASS` отдельным коммитом измените поддерживаемые pins, пользовательскую документацию обновления и lifecycle contracts Solo VPS. Сохраните этот disposable VPS до проверки нового source: запустите на нём `make verify` и `make audit`, затем повторите внешний HTTPS health check.

Только после экспорта evidence и успешной проверки новых pins удалите disposable VPS, DNS records и тестовые buckets, затем отзовите выданные ему credentials.
