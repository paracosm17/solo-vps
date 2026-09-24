# Backblaze B2 для внешних backup

Backblaze B2 — основной managed S3-compatible provider в пошаговой главе Solo VPS про внешние резервные копии. Для старта B2 не требует банковскую карту, первые 10 GB хранилища бесплатны, а private bucket можно подключить и к Coolify, и к restic.

Если вы проходите настройку впервые, лучше идти по [главе 6: резервные копии вне VPS](operations/offsite-backups.md). Эта страница оставлена как краткий provider reference.

## 1. Создайте приватный bucket

**Где: Backblaze → B2 Cloud Storage → Buckets → Create a Bucket**

Используйте:

```text
Files in Bucket are: Private
Object Lock:          off для первого теста
```

После создания скопируйте S3 **Endpoint**. Он имеет вид:

```text
s3.<REGION>.backblazeb2.com
```

Для клиентов используйте:

```text
https://s3.<REGION>.backblazeb2.com
```

`<REGION>` — часть endpoint между `s3.` и `.backblazeb2.com`.

## 2. Создайте bucket-scoped Application Key

**Где: B2 Cloud Storage → Application Keys → Add a New Application Key**

Выберите:

```text
Allow Access to Bucket(s):   только backup bucket
Type of Access:              Read and Write
Allow List All Bucket Names: enabled
File Name Prefix:            empty
```

`Allow List All Bucket Names` нужен некоторым S3-интеграциям для проверки bucket. Доступ к объектам при этом остаётся ограничен выбранным bucket.

Сохраните:

```text
keyID           -> AWS_ACCESS_KEY_ID
applicationKey  -> AWS_SECRET_ACCESS_KEY
```

`applicationKey` показывается только один раз.

## 3. Укажите endpoint и region в Solo VPS

В постоянной конфигурации хранятся только несекретные repository coordinates:

```yaml
backup:
  repository:
    endpoint: https://s3.<REGION>.backblazeb2.com
    bucket: <backup-bucket>
    prefix: solo-vps
    region: <REGION>
```

Credentials и restic password в `config.yml` не добавляются.

## 4. Подключение к Coolify

В **S3 Storages → Add** используйте:

```text
Endpoint:   https://s3.<REGION>.backblazeb2.com
Bucket:     <backup-bucket>
Region:     <REGION>
Access Key: keyID
Secret Key: applicationKey
```

Затем выполните **Validate Connection & Continue**.

Если получаете `403`, сначала проверьте `Read and Write`, правильный bucket и включённый `Allow List All Bucket Names`.

## Что эта страница не доказывает

Созданный bucket и успешная validation ещё не доказывают, что:

- PostgreSQL backup реально попал за пределы VPS;
- скачанный внешний `.dmp` восстанавливается;
- Coolify control-plane backup существует;
- restic snapshot восстанавливается;
- credentials переживут потерю единственной рабочей станции.

Эти проверки выполняются в [главе 6](operations/offsite-backups.md).

## Альтернативы

Если Backblaze недоступен для вашего аккаунта или региона, используйте другой S3-compatible provider. Готовая альтернативная инструкция: [Cloudflare R2](backup-storage-cloudflare-r2.md).

## Справка

- Backblaze B2 pricing: <https://www.backblaze.com/cloud-storage/pricing>
- S3-compatible API: <https://www.backblaze.com/docs/cloud-storage-s3-compatible-api>
- Buckets: <https://www.backblaze.com/docs/cloud-storage-create-and-manage-buckets>
- Application Keys: <https://www.backblaze.com/docs/cloud-storage-create-and-manage-app-keys>
