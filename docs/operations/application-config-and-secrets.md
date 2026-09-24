# Configure application variables and secrets in Coolify

For normal application runtime configuration, use Coolify. SOPS + age is for infrastructure/recovery files and is **not equivalent to Vault** or an everyday application secret editor.

## One JSON variable is valid

You do not need one environment variable per JSON field. If your application naturally consumes one configuration document, a multiline variable is reasonable:

```text
APP_CONFIG_JSON
```

Example value:

```json
{
  "payments": {
    "merchant_id": "<value>",
    "token": "<secret>"
  },
  "notifications": {
    "chat_id": "<value>"
  }
}
```

In Coolify, enable **Multiline** when the value spans multiple lines. The application parses `APP_CONFIG_JSON` at startup.

## Prefer separate variables when lifecycle differs

Use independent variables when values rotate or vary independently:

```text
DATABASE_URL
STRIPE_API_KEY
SENTRY_DSN
SMTP_PASSWORD
```

This makes per-environment overrides and rotations easier to reason about.

## Build-time vs Runtime

Keep the boundary explicit:

- **Runtime** values are delivered to the running application;
- **Build Variable** values exist during image build and should not be used for secrets unless your build truly needs them;
- **Docker Build Secrets** are preferable when the build needs secret material without baking it into image layers.

Avoid copying a runtime secret into the image just because the Dockerfile can access a build argument.

## Locked secrets

Use Coolify's locked/secret treatment for sensitive runtime values. Restrict who can view/edit the application in Coolify and do not paste production values into issue reports, public logs, or documentation.

## Shared variables

Coolify **Shared variables** can reduce duplication for values intentionally shared across resources/environments. Do not use sharing as a substitute for least privilege: a secret that only one application needs should stay scoped to that application.

## CI-only secrets

Deployment/API credentials used only by GitHub Actions belong in GitHub repository/environment secrets, not in Coolify application runtime variables.

## Infrastructure/recovery secrets

S3 credentials, restic passwords, and Grafana Cloud ingestion credentials used by Solo VPS host automation follow [SOPS + age](../secrets-sops-age.md), not the application variable path.

## Config files

If an application genuinely needs file semantics, prefer a reviewed mechanism that materializes the value at runtime with restrictive permissions. Do not add an always-on secret server merely to turn a static JSON value into a file for one VPS.

## Reference

- Coolify environment variables: <https://coolify.io/docs/knowledge-base/environment-variables>
