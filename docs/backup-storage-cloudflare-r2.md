# Use Cloudflare R2 for off-site backups

> **Alternative provider.** The main Solo VPS guided path uses [Backblaze B2](backup-storage-backblaze-b2.md) because its free start does not require a credit card. If your Cloudflare account asks for a payment method to activate R2, use the default B2 path instead.

Cloudflare R2 is one concrete managed S3-compatible storage option for Solo VPS restic backups. It does **not** require a second VPS: the only compute host remains your application VPS.

This page covers provider setup only. The generic backup workflow is in [restic off-site backups](backups-restic.md).

## 1. Create a private bucket

**Where: Cloudflare dashboard → R2**

Create one bucket dedicated to the Solo VPS backup repository. Keep it private.

A generic name is enough; do not copy a personal bucket name into public project files.

## 2. Create bucket-scoped credentials

Create an R2 S3 API token with:

```text
permission: Object Read & Write
scope:      specific backup bucket
```

Record the generated Access Key ID and Secret Access Key in your password manager/secret workflow. The secret is shown only at creation time.

Do not commit either value.

## 3. Put only repository coordinates in Solo VPS config

R2's S3 endpoint has the form:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Configure the persistent Solo VPS file with **non-secret** metadata:

```yaml
backup:
  repository:
    endpoint: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    bucket: <backup-bucket>
    prefix: solo-vps
    region: auto
```

`region: auto` is the R2 S3-compatible value used by this provider example.

## 4. Create encrypted backup credentials

Do not add S3 credentials or the restic password to `config.yml`.

Use the workstation flow from [restic off-site backups](backups-restic.md) to create the encrypted `backup.enc.yaml` bundle and deliver only runtime credentials to the VPS.

## 5. Continue with repository initialization

Back in the generic backup guide, run readiness, install the backup runtime, then choose **exactly one** repository ownership path:

- initialize a new empty restic repository; or
- adopt an existing repository after read-only verification.

## What this page does not prove

Creating a bucket and token does not prove:

- the VPS can authenticate;
- the restic repository was initialized;
- a fresh snapshot exists;
- a restore works;
- the backup survives VPS destruction.

Those are separate verification/recovery steps.


## References

- Cloudflare R2 S3 API: <https://developers.cloudflare.com/r2/get-started/s3/>
- R2 authentication: <https://developers.cloudflare.com/r2/api/tokens/>
