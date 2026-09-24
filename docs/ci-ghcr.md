# CI/CD reference

For the complete setup, follow [2. Deploy an application and enable CI/CD](operations/first-app.md). That runbook includes the SSH key, CI account, Coolify token, GitHub fields and the first automatic deployment.

This page explains the workflow contract and how to adapt it to an existing application.

## Delivery pipeline

| Trigger | Result |
| --- | --- |
| Pull request | Tests, lint, migration preflight and image build; no publication or deployment |
| First push to `main`, CD disabled | Tests, image publication to GHCR and verification of its digest |
| Push to `main`, CD enabled | The same checks, followed by deployment through the `production` environment and restricted SSH tunnel |

GitHub Actions builds the image. Coolify pulls and runs it on the VPS. The workflow deploys the exact published `name@sha256:digest`, never `latest`. A separate runner pulls that digest and checks `/healthz` before deployment.

The application workflow lives in `templates/github-actions/hello-app-ci.yml`. Solo VPS's own `.github/workflows/repository-ci.yml` checks this infrastructure repository; its checks and credentials are separate.

## Adapt the template to an existing application

The starter in the runbook already contains the complete template. For an existing app, use this file mapping:

```text
templates/github-actions/hello-app-ci.yml -> .github/workflows/app.yml
scripts/coolify_deploy_api.py             -> scripts/coolify_deploy_api.py
scripts/check_release_revision.py        -> scripts/check_release_revision.py
tests/test_release_revision.py           -> tests/test_release_revision.py
scripts/validate_coolify_image_handoff.py -> scripts/validate_coolify_image_handoff.py
templates/github-actions/tests/*          -> tests/
```

Create empty `scripts/__init__.py` and `tests/__init__.py` if they do not exist. Copy or adapt `requirements-dev.txt`, `ruff.toml` and application-owned `migration_preflight.py` from `examples/hello-app/`. Adjust `APP_DIR`, test/build paths and commands for your application. Packaging details are in `templates/github-actions/README.md`.

The image needs a meaningful health check. Before enabling CD, deploy a fixed digest manually and wait for `running:healthy`; this is the previous image available for recovery. A private GHCR image also needs working [registry pull credentials in Coolify](https://coolify.io/docs/knowledge-base/docker/registry). The public demo does not require them.

## Deployment settings

Use the runbook for [key creation and CI transport](operations/first-app.md#ci-key), followed by [the GitHub environment](operations/first-app.md#github-production). The configuration contract is:

| Scope | Name | Value |
| --- | --- | --- |
| Environment `production`: secret | `SOLO_VPS_DEPLOY_SSH_KEY` | Dedicated CI private key, without a passphrase |
| Environment `production`: secret | `COOLIFY_API_TOKEN` | Current-team token with `read`, `write`, `deploy` |
| Environment `production`: variable | `SOLO_VPS_DEPLOY_HOST` | Server address, without user, protocol or port |
| Environment `production`: variable | `SOLO_VPS_SSH_KNOWN_HOSTS` | One trusted server Ed25519 key line, matching that address |
| Environment `production`: variable | `SOLO_VPS_DEPLOY_SSH_FINGERPRINT` | CI-key fingerprint `SHA256:...` |
| Environment `production`: variable | `COOLIFY_RESOURCE_UUID` | Application UUID |
| Repository: variable | `SOLO_VPS_DEPLOY_ENABLED` | `true`, after the initial image is healthy and credentials are ready |

The server account `solo-vps-ci` permits only local TCP forwarding to `127.0.0.1:8000`, without a shell, sudo or Docker membership. Obtain the server key through a trusted admin session; CI must not trust an unverified `ssh-keyscan` result. The plan's `CI_DEPLOY_*` arguments do not persist configuration: `ci_deploy.ssh_public_key_file` must point to the public key on the controller.

## Database migrations

**Application migration preflight** runs after tests and before image publication with only `contents: read`. It receives no production, deployment or database credentials.

The application owns migrations. Keep preflight non-mutating, prefer backward-compatible expand/contract changes, and prepare a tested restore or forward-fix plan with a fresh backup before irreversible data changes. Solo VPS does not run generic database migrations for applications.

## Failed or superseded deployments

The deploy helper requires a healthy current image with a fixed digest before changing the application. Deployment jobs are serialized. Inside the job, a revision check skips deployment if a newer commit is already on `main`.

After a confirmed candidate failure, the helper attempts to restore and redeploy the previous image. Even if recovery succeeds, CI stays red with `DEPLOY_FAILED_ROLLBACK_OK`. This restores a **container image**, not database state or external side effects.

On timeout or unknown status, the helper does not start rollback while the original deployment may still run. Inspect Coolify Deployments before manual action. For failed recovery, follow [Deployment rollback](operations/deployment-rollback.md) using the token-free context printed by CI.

## Security boundaries

- PRs do not receive production credentials or publish/deploy images.
- GHCR publication uses the repository's `GITHUB_TOKEN`; `packages: write` is limited to publication.
- Third-party actions are pinned to full commit IDs.
- The deploy job uses `cancel-in-progress: false` and strict SSH host-key checking.
- Direct management ports `8000/6001/6002` stay private; CI reaches port 8000 through the restricted tunnel.
- The Coolify token needs `read`, `write`, `deploy`. It covers the current team and expires according to the chosen lifetime.
- GitHub stores deployment secrets; Coolify stores application runtime secrets. SOPS + age is for infrastructure/recovery secrets.

For branch protection, require checks emitted by your application workflow, such as application tests and the PR image build. Do not require Solo VPS-only checks such as `fast-source` in an app repository that does not run them.

## Where to look

| Task | Location |
| --- | --- |
| Inspect tests, build or deploy job | GitHub → repository → Actions |
| Find the published digest | Actions run summary or GHCR package |
| Inspect deployment history/startup errors | Coolify → application → Deployments |
| Inspect application output | Coolify → application → Logs |
| Change runtime ENV | Coolify → application → Environment Variables |

See [Application config and secrets](operations/application-config-and-secrets.md) for runtime configuration and [Daily operations](operations/operator-ui.md) for the operator UI.
