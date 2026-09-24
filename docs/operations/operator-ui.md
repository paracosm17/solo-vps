# Using the platform every day

After basic setup, a normal update means changing code on your workstation, pushing it to GitHub, waiting for checks and merging the change. Your application on the VPS updates automatically.

This article follows [part two](first-app.md): a separate application repository, GitHub Actions and a **Docker Image** application in Coolify. Your own application needs this workflow, with its tests and Dockerfile configured.

## What each tool does

| Name | What it means for you |
| --- | --- |
| Solo VPS | Prepares the server: access, security, Docker and Coolify |
| GitHub | Stores code. A pull request lets you check an update before releasing it |
| GitHub Actions | Runs tests, builds the application and starts deployment |
| GHCR / Packages | Stores images: packages containing the application and its dependencies |
| Docker | Runs an image in a container on the VPS. A container is a running instance of the application |
| Coolify | Provides a dashboard for applications, domains, variables, databases and deployments |
| Grafana | Searches retained logs over a chosen time range, once collection is configured |

**CI** means automatically checking and building changes. **CD** means delivering the checked update to the server. **Production** is the application people are using.

Solo VPS connects these tools through a repeatable setup process. After setup, each change no longer requires manually copying code to the server and building it there. Server maintenance, backups and fixing application bugs remain your responsibility.

## From a change to a running version

<div class="solo-delivery-flow" role="list" aria-label="Six stages of releasing an application">
  <div role="listitem"><span>1</span><div><strong>Workstation · change the code</strong><p>Create a branch, save your changes in a commit and run git push.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>GitHub · open a pull request</strong><p>Actions runs tests and a trial build. The running application stays on its existing version.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>GitHub · merge into main</strong><p>Once checks are green, select Merge. This starts the release of a new version.</p></div></div>
  <div role="listitem"><span>4</span><div><strong>Actions → GHCR · prepare the image</strong><p>Tests run again. CI builds, publishes and verifies a specific image with a unique digest.</p></div></div>
  <div role="listitem"><span>5</span><div><strong>Coolify · start the update</strong><p>CI supplies the image reference. Coolify downloads it and starts a new container on the VPS.</p></div></div>
  <div role="listitem"><span>6</span><div><strong>You · check the result</strong><p>Wait for Deploy to succeed, open the application and check the feature you changed.</p></div></div>
</div>

Pushing to a working branch does not yet update production. A change to `main` triggers deployment when `SOLO_VPS_DEPLOY_ENABLED` is enabled. A direct push to `main` can also trigger deployment; use a pull request to see the checks first.

A **digest** identifies the exact contents of an image. It ensures the server receives the image that CI verified.

## Release your next change

First finish or save any uncommitted changes. **On your workstation, in the application repository:**

```bash
git switch main
git pull --ff-only
git switch -c change-homepage
```

Choose a new branch name for each task. Edit the files and run your application's tests. Commit the selected files and push the branch. In the demo, if you changed only `app.py`:

```bash
git add app.py
git commit -m "Update homepage"
git push -u origin change-homepage
```

**On GitHub:**

1. Open **Pull requests → New pull request**.
2. Choose base `main` and your branch, then create the PR.
3. Wait for checks to pass. If a check fails, read its log, fix the error and push another commit to the same branch.
4. Select **Merge pull request → Confirm merge**.
5. Open **Actions** and the run for the new commit in `main`.
6. Wait for **Deploy immutable image to Coolify** to succeed.
7. Open your application domain and check the result.

**Coolify → application → Deployments** shows deployment history. A normal GitHub release does not require a separate **Deploy** click in Coolify.

## Change a setting without changing code

For example, you need to change an external API address or a message the application reads from an environment variable.

**In Coolify → application → Environment Variables:**

1. Add or edit the required **Name** and **Value**.
2. Enable **Available at Runtime** for a running application setting.
3. Leave **Available at Buildtime** disabled unless the build needs the value.
4. Select **Save**.
5. Wait for any active CI deployment to finish. Select **Redeploy** and wait for success.
6. Check the feature that uses the setting.

In the demo, `APP_MESSAGE` changes the `message` response field. The image stays the same: the new container receives a different ENV value.

If the application embeds a value into files at build time, as some frontend applications do, Redeploy alone is insufficient. It needs a new build with the setting supplied in CI.

## Where passwords and tokens belong

| Purpose | Where to set it |
| --- | --- |
| Database password or external API token used by the running application | Coolify → application → Environment Variables |
| CI deployment access | GitHub → Settings → Environments → production → Environment secrets |
| Log-agent or backup credentials | Follow that feature's setup guide; the project keeps an encrypted copy on your workstation |

Keep passwords out of source code, Dockerfiles and logs. Storing a value in a secret does not stop the application from accidentally printing it. `APP_MESSAGE` is unsuitable for a real secret: the demo returns it to clients.

When replacing a token, update it where it is used and verify operation before revoking the old token, if the service supports that sequence. Revoke an exposed token immediately.

## Where to find logs

| What you need to know | Where to look |
| --- | --- |
| Why tests or a build failed | GitHub → repository → Actions → run → failed job |
| Why the new container did not start | Coolify → application → Deployments → latest deployment |
| What the application is writing now | Coolify → application → Logs |
| What happened three days ago | Grafana → Explore, after setting up retained logs |

### A user reports an error from three days ago

1. Ask for the time, timezone, action and request identifier if available.
2. Open Grafana, select the application and an absolute time range around the error.
3. Find the request or error text. Read nearby entries.
4. Compare the time with **Coolify → Deployments**: which version was running?
5. Save the relevant excerpt for investigation, removing personal information before sharing.
6. Fix the cause in code and release it through a normal PR.

History starts after collection is configured. Logs already deleted before then cannot be recovered retroactively. Investigating a month-old event requires at least a month of retention.

Grafana cannot invent details the application never logged. Include timestamps, useful error descriptions and request identifiers; exclude passwords and tokens.

## When an update fails

| What you see | What to do |
| --- | --- |
| Failed PR tests or build | Open the first failed job, fix the code and push a commit to the same branch. This PR has not changed production |
| Image published after merge, but Deploy stops before connecting to the VPS | Read the variable, SSH or API error. Fix it and rerun the failed job for the current `main` |
| New container fails its health check | Read Deployments and the rollback result in Actions. Do not start a second deployment while the first is active |
| CI times out or loses contact | Check Coolify first: the operation may have continued. Do not retry blindly |
| Actions is green but a feature behaves incorrectly | Test the feature and inspect its logs. A health check does not prove all business logic is correct |
| Error appears after an ENV change | Restore the previous value in Coolify, Redeploy and check the result |

For a confirmed failure of a new version, the helper may restore the previous image. `DEPLOY_FAILED_ROLLBACK_OK` means the previous version is healthy again. CI remains red because the release failed.

`DEPLOY_FAILED_ROLLBACK_FAILED` means automatic recovery also failed. Read Deployments and follow the [deployment recovery guide](deployment-rollback.md). An unknown result or timeout does not trigger automatic rollback, which could conflict with an operation still in progress.

**Reverting an image does not restore deleted database rows or undo schema changes.** Changes to data need their own backup and recovery plan.

## When the application stops opening

1. Try the domain from another connection, such as mobile data. Record when the outage started.
2. If Coolify is available, inspect application status, the latest deployment and Logs. Compare the outage time with recent code and ENV changes.
3. If the dashboard is also unavailable, check the VPS in your provider's panel.
4. If the VPS is running but normal access is unavailable, use the provider console. Continue with [server diagnostics](status-and-logs.md).
5. After recovery, check the public application address and the external monitor's recovery notification, if alerts are configured.

Do not start an investigation by reinstalling Coolify or deleting containers: that can destroy useful evidence without fixing the cause.

## Regular habits

Before a release, review the PR; after it, check Deploy and the changed feature. Once you have a database, check backup freshness and periodically restore a copy into a separate test database.

Watch free disk space, token and certificate expiry, and outage notifications. Updating your application, Coolify and Ubuntu are different operations. Use a separate maintenance window. The practical sequence for failed deployments, ENV mistakes, collector restarts and reboot is in [chapter 8: failures and maintenance](incidents-and-maintenance.md); Docker/Coolify version changes remain in the [upgrade guide](../upgrades.md).

**Next: [what to add after basic setup](after-basic-setup.md).** Start with retained logs when the current Coolify log view is no longer enough.
