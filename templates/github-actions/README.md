# GitHub Actions + GHCR + Coolify template

This directory contains the reusable application-delivery workflow for Solo VPS.

## Copy into an application repository

For a complete standalone sample, run `python3 scripts/create_app.py ../hello-app` from the Solo VPS root. For an existing application, copy:

```text
hello-app-ci.yml                         -> .github/workflows/ci.yml
../../scripts/coolify_deploy_api.py      -> scripts/coolify_deploy_api.py
../../scripts/check_release_revision.py -> scripts/check_release_revision.py
../../tests/test_release_revision.py    -> tests/test_release_revision.py
../../scripts/validate_coolify_image_handoff.py -> scripts/validate_coolify_image_handoff.py
tests/*                                  -> tests/
```

Also provide `${APP_DIR}/migration_preflight.py`. The reference app uses [`../../examples/hello-app/migration_preflight.py`](../../examples/hello-app/migration_preflight.py).

Also copy/adapt `requirements-dev.txt` and `ruff.toml` from `examples/hello-app`. Then adapt `APP_DIR`, tests, lint/format commands and the migration check.

Leave **repository variable** `SOLO_VPS_DEPLOY_ENABLED` unset for initial publication. Create and verify the first immutable Docker Image in Coolify, configure `production`, then set it to `true`. Follow the [first application tutorial](../../docs/operations/first-app.md).

## Delivery chain

```text
pull request
-> application/helper tests
-> Application migration preflight
-> Docker build without push

push to main
-> application/helper tests
-> Application migration preflight
-> Docker build + GHCR push
-> exact name@sha256:digest
-> fresh read-only registry verification job
-> loopback /healthz smoke test
-> production environment gate
-> restricted SSH -L tunnel
-> Coolify read-only API preflight
-> exact-digest deploy
-> running:healthy
```

On a candidate failure after mutation, the helper restores the previous immutable desired image and redeploys it. `DEPLOY_FAILED_ROLLBACK_OK` still fails the workflow so a failed release remains visible.

## Application migration boundary

**Application migration preflight** is mandatory, non-mutating, and application-owned. The **application owns** migration compatibility; Solo VPS does not provide a generic database migration executor.

Prefer **expand/contract** migrations. For irreversible schema/data changes, require fresh backup evidence and a tested restore or explicit forward-fix plan.

Automatic recovery is **container image rollback** only. It does not perform **database rollback**, application-data rollback, or reversal of external side effects.

## Required `production` environment

Create a GitHub Actions environment named exactly `production`.

Secrets:

```text
SOLO_VPS_DEPLOY_SSH_KEY
COOLIFY_API_TOKEN
```

Variables:

```text
SOLO_VPS_DEPLOY_HOST
SOLO_VPS_SSH_KNOWN_HOSTS
SOLO_VPS_DEPLOY_SSH_FINGERPRINT
COOLIFY_RESOURCE_UUID
```

Use the dedicated `solo-vps-ci` private key. The server receives only the public half. Pin the server Ed25519 host key from a trusted operator channel; the workflow intentionally refuses dynamic `ssh-keyscan` trust.

The Coolify API token needs only the deployment abilities (`read`, `write`, `deploy`). Do not use `root` or `read:sensitive`.

## Security contract

- Default workflow permission: `contents: read`.
- Only publish adds `packages: write`; registry verification uses `packages: read`.
- PR jobs never authenticate to GHCR and never deploy.
- Same-repository GHCR publishing uses `GITHUB_TOKEN`.
- Main publishes a commit-derived tag, but deployment uses the emitted immutable digest.
- The deploy job consumes the same verified digest.
- Deployment credentials exist only in the `production` job/step boundary.
- Production deploys are serialized; a newer push does not cancel an active deploy.
- SSH uses a dedicated key, strict known-hosts verification, no agent forwarding, and only `-L 127.0.0.1:18000:127.0.0.1:8000`.
- The helper checks Coolify before mutation and requires explicit deploy confirmation.
- The workflow explicitly permits the first-app public domain while preserving internal port, no host mapping and no custom Docker options.
- Inside the serialized job, verify the candidate is still the current main commit before deployment. An unknown API result fails closed.
- Unknown deployment outcomes/timeouts stop without overlapping rollback; the previous app must report running:healthy before mutation.
- Third-party actions are pinned to full commit SHAs; update them as reviewed dependencies, not floating tags.

## Pinned actions

The workflow file is the source of truth for action commit pins. Release labels remain beside those pins for readability. When updating an action:

```text
review upstream release
-> update the release label + full commit SHA
-> make validate-ci-template
-> make test-ci-template
-> inspect the workflow diff
-> prove hosted behavior before calling the update verified
```

## Local checks

```bash
make validate-ci-template
make test-ci-template
make validate-application-migration-contract
make test-application-migration-contract
```

See [`../../docs/ci-ghcr.md`](../../docs/ci-ghcr.md) for the operator-facing setup and transport guide.
