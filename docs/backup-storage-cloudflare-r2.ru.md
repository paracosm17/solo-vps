# Cloudflare R2 для внешних backup

> **Альтернативный provider.** Основной пошаговый маршрут Solo VPS использует [Backblaze B2](backup-storage-backblaze-b2.md), потому что для его бесплатного старта не нужна банковская карта. Если ваш Cloudflare account просит добавить способ оплаты для активации R2, используйте основной B2-маршрут.

Cloudflare R2 — один конкретный вариант managed S3-compatible storage для restic backup Solo VPS. Второй VPS **не нужен**: единственным compute host остаётся ваш application VPS.

Эта страница описывает только настройку провайдера. Общий backup workflow находится в [руководстве по внешним restic backup](backups-restic.md).

## 1. Создайте приватный bucket

**Где: Cloudflare dashboard → R2**

Создайте отдельный bucket для backup repository Solo VPS. Оставьте его приватным.

Достаточно generic имени; не копируйте личное имя bucket в публичные файлы проекта.

## 2. Создайте credentials, ограниченные bucket

Создайте R2 S3 API token со следующими правами:

```text
permission: Object Read & Write
scope:      specific backup bucket
```

Сохраните сгенерированные Access Key ID и Secret Access Key в password manager/secret workflow. Secret показывается только при создании.

Не коммитьте ни одно из этих значений.

## 3. В Solo VPS config храните только координаты repository

S3 endpoint R2 имеет вид:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

В постоянной конфигурации Solo VPS укажите **несекретные** metadata:

```yaml
backup:
  repository:
    endpoint: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    bucket: <backup-bucket>
    prefix: solo-vps
    region: auto
```

`region: auto` — S3-compatible значение R2, используемое в этом примере.

## 4. Создайте зашифрованные backup credentials

Не добавляйте S3 credentials или restic password в `config.yml`.

Используйте workstation flow из [руководства по внешним restic backup](backups-restic.md): создайте зашифрованный bundle `backup.enc.yaml` и доставьте на VPS только runtime credentials.

## 5. Перейдите к инициализации repository

В общем backup guide выполните readiness, установите backup runtime, затем выберите **ровно один** путь владения repository:

- инициализировать новый пустой restic repository; или
- принять существующий repository после read-only verification.

## Чего эта страница не доказывает

Создание bucket и token не доказывает, что:

- VPS может аутентифицироваться;
- restic repository инициализирован;
- существует свежий snapshot;
- restore работает;
- backup переживает уничтожение VPS.

Это отдельные verification/recovery шаги.


## Справка

- Cloudflare R2 S3 API: <https://developers.cloudflare.com/r2/get-started/s3/>
- R2 authentication: <https://developers.cloudflare.com/r2/api/tokens/>
