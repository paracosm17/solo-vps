# Update Solo VPS, Coolify and Traefik

Use this page when an installation already works and a new Solo VPS release or a Coolify/Traefik update notification appears.

Run every command **in Bash/WSL from the Solo VPS directory on the same controller that configured the server**. If the controller runs on the VPS, log in as the existing administrator and start in `~/solo-vps`. Keep the existing config, inventory and keys; a server reinstall is unnecessary.

## What gets updated

| Component | What changes | How to update |
| --- | --- | --- |
| Solo VPS | Automation source and reviewed component versions | Prepare a new checkout of a published tag |
| Coolify | Dashboard, its database and platform containers | From the new source, run `coolify-upgrade-preflight`, then `coolify-upgrade` |
| Traefik | Reverse proxy image | Run `proxy-upgrade-preflight`, then `proxy-upgrade` |

A source update alone leaves running containers intact. When both components need updating, use **Solo VPS → Coolify → Traefik → verification**. Apply only the transitions required by the selected Solo VPS release notes.

## 1. Find a reviewed update

From your current project directory:

```bash
make updates-check
make updates-plan
```

The first command checks GitHub Releases for **Solo VPS and Coolify**; the second shows the local plan offline. It does not separately discover upstream Traefik releases yet: find its reviewed version in Solo VPS release notes and `config/coolify-release.yml`.

A Coolify notification announces an upstream release. Installing through Solo VPS first requires a published Solo VPS release that qualifies the transition. **If none exists yet, retain the working version and wait for compatibility qualification.** Editing a version number does not replace that qualification.

Your installed checkout continues to use its reviewed version even when upstream releases a newer one. Select a published Solo VPS release whose notes support a transition from your installation. A Traefik-only compatibility release may retain the current Coolify version.

## 2. Choose a release and prepare recovery

Open [Solo VPS GitHub Releases](https://github.com/paracosm17/solo-vps/releases). Read the supported origins, changed components and required actions. If your current version differs, follow the documented intermediate releases.

Before changing runtime:

- prepare and verify fresh backups of the Coolify database/configuration, proxy files/image and application data; retain an encrypted copy outside the VPS;
- confirm administrator SSH and provider console/rescue access work;
- let deployments finish, then pause new deployments and settings changes during the transition;
- check the applications' current `/healthz` and retain the previous source directory.

See [off-site backups](offsite-backups.md), [PostgreSQL backups](postgresql-backups.md) and [recovery boundaries](../upgrades.md#rollback-and-recovery). Automatic local upgrade checkpoints supplement those backups and cannot survive VPS loss.

## 3. Prepare new Solo VPS source

In the **old** project directory, retain the `make paths` output, then enter the exact published tag from Releases:

```bash
make paths
printf '%s' 'Solo VPS tag from GitHub Releases (v0.x.y): '; read -r RELEASE_VERSION
make source-update-prepare RELEASE_VERSION="$RELEASE_VERSION" && cd "../solo-vps-$RELEASE_VERSION"
```

After preparation succeeds, from the new directory:

```bash
make setup
make paths
make validate
make doctor
make updates-plan
```

Continue only after every command succeeds. Config/inventory paths must match between the old and new directories. Preparation preserves the old checkout and does not update the VPS. Review local changes in the old directory or an already-existing target directory separately before proceeding.

Continue from the new directory. For a controller running on the VPS, retain the previous `~/solo-vps` separately and place the new checkout at that standard path, as described in [the detailed procedure](../upgrades.md#retest-an-existing-vps-after-a-source-fix).

## 4. Update Coolify when required by the release

Compare the version shown in the dashboard with `make updates-plan` and the **new checkout's** release notes. When they match, continue to the next required component.

For a supported transition, copy the exact HTTPS URL from **Servers → `server.hostname` → Sentinel → Configuration → Coolify URL**, including a trailing `/` when configured. Sentinel must report **In Sync**.

```bash
printf '%s' 'Exact Coolify URL from Sentinel settings: '; read -r COOLIFY_SENTINEL_URL
export COOLIFY_SENTINEL_URL
make coolify-upgrade-preflight
```

After preflight succeeds and backups are verified:

```bash
COOLIFY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN make coolify-upgrade
make verify-coolify
```

The command retains a local checkpoint and performs the reviewed transition. Stop on failure and read [the resume procedure](../upgrades.md#interrupted-upgrade).

Use Solo VPS commands for this path. Coolify's **Update** button bypasses its checkpoint, reviewed artifacts and transaction/resume checks; that transition is outside this integration's qualified path.

## 5. Update Traefik when required by the release

The new checkout's `config/coolify-release.yml` defines the target image. Preflight checks the reviewed origin, proxy health, networks and published ports:

```bash
make proxy-upgrade-preflight
```

After it succeeds:

```bash
PROXY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_PROXY_UPGRADE_PLAN make proxy-upgrade
```

The command retains a checkpoint and changes only the image through native Coolify actions. Analytics settings, certificates and route configuration are preserved. Proxy recreation briefly interrupts incoming requests. This is a separate explicit operation; ordinary port reconciliation leaves its version intact.

Stop if the source image is outside the reviewed set. For interruption or rollback, follow [the Traefik procedure](../upgrades.md#traefik-reverse-proxy).

## 6. Verify the result

```bash
make verify
make audit
```

Open the Coolify dashboard and real applications; check `/healthz`, Sentinel **In Sync** and analytics delivery when enabled. Export the new checkpoints off-host. Retain old source and backups until the result is confirmed and your retention period ends.

The update is complete when versions match the selected release, checks pass and applications work. Returning to the old source directory does not undo Coolify migrations. Find Docker, Ubuntu and failed-transition recovery details in [the upgrade reference](../upgrades.md).
