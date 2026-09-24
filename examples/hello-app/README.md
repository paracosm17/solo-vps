# Hello app

A deliberately small application used to prove the Solo VPS deployment path.

## Contract

The container:

- listens on port `8080`;
- serves `GET /healthz`;
- returns a small JSON health response;
- does not need a database or persistent volume;
- is suitable for manual Coolify deployment and CI/GHCR smoke tests.

## Run the dependency-free tests

From the Solo VPS repository:

```bash
make test-example-app
make validate-example-app
```

## Deploy it manually first

Use [Deploy your first application](../../docs/operations/first-app.md). The tutorial deploys this directory through Coolify before introducing CI/CD.

## Migration preflight

`migration_preflight.py` is the reference **Application migration preflight** hook. This sample has no database, so it reports no migration mutation and a `container-image-only` rollback scope.

A real stateful application must replace the hook with application-owned, non-mutating compatibility checks. Prefer expand/contract database changes; image rollback is not database rollback.

## Add CI/CD later

After the manual application path works, see [GitHub Actions + GHCR delivery](../../docs/ci-ghcr.md) and the [consumer workflow template](../../templates/github-actions/README.md).
