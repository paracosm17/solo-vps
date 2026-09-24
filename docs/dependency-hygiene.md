# Dependency and image update hygiene

M12 establishes a small update contract for the dependencies that already exist in the project. It does not add vulnerability scanners, SBOM generators, signing, or automatic merge behavior.

## Current dependency classes

| Dependency | Current policy | Update path |
| --- | --- | --- |
| `python:3.13.14-slim-bookworm` | exact Python patch tag, Debian variant fixed | weekly Dependabot PR for `examples/hello-app/Dockerfile` |
| `community.general` | exact collection version `13.0.1` | manual reviewed dependency change |
| GitHub Actions in `templates/github-actions/hello-app-ci.yml` | full commit SHA pins | manual reviewed dependency change |
| GitHub Actions in `.github/workflows/` | reviewed workflow versions | weekly Dependabot PR |
| MkDocs packages in `requirements-docs.txt` | exact versions | weekly Dependabot PR |

The validator for this policy is `scripts/validate_dependency_hygiene.py` and is included in `make validate`.

## Why the sample base image is patch-tagged, not digest-pinned

The sample application's final deployable identity is already the immutable GHCR image digest emitted by M11. The base image has a different trade-off.

For this slice the Dockerfile uses:

```dockerfile
FROM python:3.13.14-slim-bookworm
```

rather than a moving minor tag such as `python:3.13-slim-bookworm`. This makes Python maintenance-version changes explicit in review.

It also intentionally does **not** add `@sha256:...` yet. Current Dependabot Core behavior suppresses Docker digest-only updates when the tag version is unchanged. An exact digest could therefore freeze same-tag rebuilds of the official Python image unless the project added another digest-update mechanism.

Both M11 Buildx steps use `pull: true`, so hosted builds explicitly attempt to refresh referenced base images. The resulting application image is still addressed by the registry digest for deployment.

If the project later adopts a tool that reliably proposes digest refreshes, switching the base image to `tag@sha256:digest` can be reconsidered as a separate dependency-policy change.

## Dependabot scope

`.github/dependabot.yml` contains three weekly updaters:

```text
Docker ecosystem
→ /examples/hello-app
→ weekly
→ patch updates within the current Python feature series only
→ at most two open version-update PRs
GitHub Actions ecosystem → /.github/workflows → at most two open PRs
pip ecosystem → /requirements-docs.txt → at most two open PRs
```

Major/minor Python feature-series updates are ignored by automation and must be reviewed as a separate dependency change. There is no auto-merge policy and no registry credential configuration.

Dependabot maintains the real source workflows in `.github/workflows`, but does **not** maintain action pins stored in `templates/github-actions/`. GitHub's `github-actions` updater discovers workflow dependencies from `.github/workflows` with `directory: "/"`; the template is stored elsewhere.

When an application repository copies the template to `.github/workflows/ci.yml`, that repository may add its own `github-actions` Dependabot entry. Template action pins remain a manual reviewed update in this source project.

## Ansible collection policy

`community.general` is the only external Ansible collection currently required. It is pinned exactly in `ansible/requirements.yml`:

```yaml
collections:
  - name: community.general
    version: "13.0.1"
```

The exact pin makes `make deps` reproducible with respect to that collection. Dependabot does not currently list Ansible Galaxy as a supported package ecosystem, so collection upgrades remain manual:

```text
review upstream release notes
→ update exact version
→ make deps in a disposable/controller environment
→ make validate
→ ansible syntax/integration checks when available
```

Adding another mandatory collection requires updating the dependency contract deliberately rather than silently broadening `requirements.yml`.

## What is deferred

This slice does not add:

- vulnerability scanning gates;
- SBOM/provenance attestations;
- image signing;
- image retention automation;
- automatic dependency merging.

Those features add CI cost and policy surface and should be introduced only with a clear failure/maintenance model. They remain P2 follow-up work and must not delay the still-blocked P1 deployment path.

## Validation

Run:

```bash
make validate-dependency-hygiene
make validate
```

Local validation checks that:

- Dependabot only targets the sample Dockerfile on a weekly, patch-only schedule;
- no registry credential block or unrelated ecosystem is introduced;
- the sample base image uses an exact `X.Y.Z` Python patch tag and the fixed `slim-bookworm` variant;
- the current slice does not silently introduce a digest pin without a matching update strategy;
- the external Ansible collection is exact-version pinned;
- M11 builds retain `pull: true` through the existing CI-template validator.

A real Dependabot PR is GitHub-hosted behavior and is not proven by local validation alone.
