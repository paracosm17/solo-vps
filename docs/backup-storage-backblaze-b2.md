# Use Backblaze B2 for off-site backups

Backblaze B2 is the default managed S3-compatible provider in the Solo VPS guided off-site backup chapter. B2 does not require a credit card to get started, the first 10 GB of storage are free, and a private bucket works with both Coolify and restic.

If this is your first setup, follow [Chapter 6: off-site backups](operations/offsite-backups.md). This page is a short provider reference.

## 1. Create a private bucket

**Where: Backblaze → B2 Cloud Storage → Buckets → Create a Bucket**

Use:

```text
Files in Bucket are: Private
Object Lock:          off for the first test
```

After creation copy the S3 **Endpoint**. It has the form:

```text
s3.<REGION>.backblazeb2.com
```

Clients use:

```text
https://s3.<REGION>.backblazeb2.com
```

`<REGION>` is the endpoint segment between `s3.` and `.backblazeb2.com`.

## 2. Create a bucket-scoped Application Key

**Where: B2 Cloud Storage → Application Keys → Add a New Application Key**

Choose:

```text
Allow Access to Bucket(s):   only the backup bucket
Type of Access:              Read and Write
Allow List All Bucket Names: enabled
File Name Prefix:            empty
```

`Allow List All Bucket Names` is required by some S3 integrations for bucket discovery/validation. Object access remains restricted to the selected bucket.

Save:

```text
keyID           -> AWS_ACCESS_KEY_ID
applicationKey  -> AWS_SECRET_ACCESS_KEY
```

The `applicationKey` is shown only once.

## 3. Put the endpoint and region in Solo VPS

Persistent configuration stores only non-secret repository coordinates:

```yaml
backup:
  repository:
    endpoint: https://s3.<REGION>.backblazeb2.com
    bucket: <backup-bucket>
    prefix: solo-vps
    region: <REGION>
```

Do not put storage credentials or the restic password in `config.yml`.

## 4. Add it to Coolify

Under **S3 Storages → Add** use:

```text
Endpoint:   https://s3.<REGION>.backblazeb2.com
Bucket:     <backup-bucket>
Region:     <REGION>
Access Key: keyID
Secret Key: applicationKey
```

Then select **Validate Connection & Continue**.

If you get `403`, first check `Read and Write`, the selected bucket and **Allow List All Bucket Names**.

## What this page does not prove

A bucket and successful validation do not prove that:

- a PostgreSQL backup was really copied off the VPS;
- a downloaded remote `.dmp` restores correctly;
- a Coolify control-plane backup exists;
- a restic snapshot restores correctly;
- credentials survive loss of the only workstation.

Those checks are performed in [Chapter 6](operations/offsite-backups.md).

## Alternatives

If Backblaze is unavailable for your account or region, use another S3-compatible provider. A ready alternative guide is available for [Cloudflare R2](backup-storage-cloudflare-r2.md).

## References

- Backblaze B2 pricing: <https://www.backblaze.com/cloud-storage/pricing>
- S3-compatible API: <https://www.backblaze.com/docs/cloud-storage-s3-compatible-api>
- Buckets: <https://www.backblaze.com/docs/cloud-storage-create-and-manage-buckets>
- Application Keys: <https://www.backblaze.com/docs/cloud-storage-create-and-manage-app-keys>
