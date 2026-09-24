# Recover from a failed application deployment

The Solo VPS deployment helper adds one narrow safety transaction around immutable Coolify Docker Image updates. It can restore the **previous container image** when a candidate deployment fails or becomes unhealthy.

It does not roll back databases or external side effects.

## Normal deployment path

```text
git push
→ Application tests
→ Application migration preflight
→ build/publish immutable image to GHCR
→ Coolify deploys exact digest
→ health verification
```

Before mutation, the helper records the current immutable desired image. If the candidate fails after the update, it restores that previous immutable image, starts it, and requires the application to return to `running:healthy`.

A failed candidate still leaves CI red. Rollback restores service state; it does not turn a failed release into a successful release.

## Result classes

```text
DEPLOY_FAILED_ROLLBACK_OK
```

The candidate failed, but the previous exact image was restored and became healthy.

```text
DEPLOY_FAILED_ROLLBACK_FAILED
```

The candidate failed and automatic restoration also failed. Use the printed known-good recovery path and Coolify UI to investigate.

The helper refuses a mutable previous image such as `latest`; an immutable digest is required as the rollback authority.

## Database migration boundary

Rollback scope is **container-image-only**.

It does not reverse:

- database schema changes;
- application data mutations;
- external API side effects;
- queue/event side effects.

For schema changes, prefer backward-compatible **expand-contract** migrations while the previous image remains deployable. An irreversible migration needs a real backup/restore or forward-fix plan before deployment.

The mandatory **Application migration preflight** is non-mutating and does not receive production deployment credentials. The application owns that hook; Solo VPS does not pretend to understand arbitrary schemas.

## If automatic rollback fails

Keep Coolify port `8000` private. Use the local/restricted deployment-control path printed by the helper or operate through Coolify's normal UI.

After recovery:

```bash
make verify-coolify
make audit
```

Then confirm the intended immutable image and application health in Coolify.

## Related

- [GitHub Actions + GHCR](../ci-ghcr.md)
- [PostgreSQL backups](../database-backups.md)

Before mutation the helper requires `running:healthy` and an immutable desired digest. Unknown outcomes, API errors and original-deployment timeouts do not start automatic rollback: the first deployment may still be running. Inspect Coolify deployment history and confirm completion before manual action. Health plus the desired digest alone do not prove the absence of manual container drift; do not mix manual and CI deployment writers.
