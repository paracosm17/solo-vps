# Handle failures and routine maintenance

Use this runbook when a CI run is red, a deployment fails, an application is unavailable, or the server needs planned maintenance.

You do not need to deliberately break the working VPS to complete this guide. The goal is to know **what changed, what is still healthy, and where to inspect the cause** before clicking Restart, Redeploy, or starting another deployment.

Complete lost-VPS recovery, replacement-host reconstruction, and Coolify version upgrades are separate procedures.

## Before you start

At minimum, complete [part 1](../quick-start.md) and [part 2](first-app.md). Depending on the optional capabilities you configured, you may also have:

- Grafana for retained logs and host metrics;
- UptimeRobot for an independent `/healthz` check;
- PostgreSQL backup/restore;
- off-site backup in S3-compatible storage.

Not every application needs every service. In the commands below, run checks only for components you actually configured.

## 1. Know the four different release failures

A red GitHub Actions run does not always mean production is broken.

| Where it failed | What happened to production | What to do |
| --- | --- | --- |
| Pull request: tests/lint/build | Nothing. Production did not change | Fix the branch and push another commit |
| `main`: tests, migration preflight, publish, or image verification | Deployment did not start. The old version keeps running | Fix the cause and make the next normal release |
| The new image deployment is confirmed failed | The helper attempts to restore the previous immutable image | Wait for rollback to finish and verify the application |
| Deployment times out or has an unknown result | The operation may still be running | **Do not start a second deployment.** Open Coolify → Deployments first |

Until GitHub reaches **Deploy immutable image to Coolify**, there is no production deployment to roll back.

## 2. If a pull request is red

**In GitHub → application repository → Pull requests → your PR:**

1. Open the failed check.
2. Find the first failed step and read its error.
3. Fix the code in the same branch.
4. Commit and `git push` again.
5. Wait for green checks before selecting **Merge**.

Do not fix this through Coolify. The PR has not changed production.

## 3. If `main` is red before deployment

**In GitHub → Actions → the run for the `main` commit:**

Check which job failed. If **Application tests**, **Application migration preflight**, **Publish main image**, or **Verify published image by digest** is red, **Deploy immutable image to Coolify** should not release that candidate.

Open the public application and `/healthz`. They should still show the previous working version.

Fix the cause through a normal PR. Do not click **Redeploy** in Coolify just because CI never reached the deployment step.

## 4. If the deployment itself failed

**In GitHub → Actions → the red `Deploy immutable image to Coolify` job:**

Find the final deployment-helper result.

### `DEPLOY_FAILED_ROLLBACK_OK`

This means:

```text
new image failed
→ helper restored the previous exact image
→ previous version is running:healthy again
→ CI stays red because the new release still failed
```

Now:

1. Open **Coolify → application → Deployments** and confirm all operations have finished.
2. Open the public `/healthz`.
3. Open `/` and confirm the expected previous version still works.
4. If needed, inspect Grafana Logs around the failed deployment time.
5. Fix the candidate in a new normal PR. Do not try to make the red workflow green with a manual Redeploy of the old image.

Rollback restores **only the container image**. It does not reverse database migrations, data changes, sent messages, or other external side effects. Risky schema/data changes need a compatible migration plan and a backup before deployment.

### `DEPLOY_FAILED_ROLLBACK_FAILED`

The new image failed and automatic restoration of the previous image also did not complete.

1. Do not start another CI deployment.
2. In **Coolify → application → Deployments**, wait for the current operation to finish and inspect its final error.
3. Check the current application status in Coolify.
4. On the VPS run read-only diagnostics:

```bash
cd ~/solo-vps
make ops-status
make verify-coolify
```

5. Use the exact known-good recovery path printed by CI and the [failed-deployment recovery reference](deployment-rollback.md). Do not substitute `latest` for an immutable digest.

### Timeout or unknown result

If the helper reports an unknown outcome, automatic rollback intentionally does not start: the first deployment may still be running.

Open **Coolify → Deployments** and wait for a final state. Only then decide whether you need a new release or recovery. Two concurrent writers — CI and a manual Redeploy — make recovery harder.

## 5. If the application is down without a new release

First determine whether the problem is the application or the whole VPS.

**From outside the server:**

1. Open `https://app.example.com/healthz`.
2. Check UptimeRobot. If it also says DOWN, the failure is visible independently of your browser.

**In Coolify:**

3. Open the application and check its status.
4. Open **Logs** and recent **Deployments**.
5. If the application is simply stopped and no deployment is active, select **Start** or **Restart**, then check `/healthz` again.

**In Grafana, when configured:**

6. In **Drilldown → Logs**, select the time when the incident started and inspect the latest application errors.
7. In **Drilldown → Metrics**, check CPU, memory, and free space on `/`.

If the UI is not enough, run on the VPS:

```bash
cd ~/solo-vps
make ops-status
make verify
make audit
```

`make ops-status`, `make verify`, and `make audit` do not automatically fix the server. They preserve the state you need to understand before making manual changes.

In the `make audit` summary, `UNAVAILABLE` means **“this particular command did not check it”**, not that the component is broken. Use `make verify-coolify` for Coolify and `make backup-status` for a configured off-site repository. When audit runs directly on the VPS, the capability report may also show the workstation-only SOPS policy/toolchain as `NOT_CONFIGURED` / `NOT_INSTALLED`: by design the private age key and SOPS policy stay on your workstation and are not copied to the VPS.

If SSH itself is unavailable, use your VPS provider's console/rescue access. Do not blindly weaken the firewall or SSH policy just to regain a login.

## 6. If an ENV change broke the application

If the application failed immediately after an Environment Variables change, the image itself may still be healthy.

**In Coolify → application → Environment Variables:**

1. Restore the previous value.
2. Select **Save**.
3. Confirm no other deployment is running.
4. Select **Redeploy**.
5. Wait for `Running (healthy)` and check the function that uses the variable.

For a secret, do not copy an old value from application logs. Use your password manager or another authoritative secret store.

## 7. Restart collectors separately from the application

A Grafana problem does not mean Coolify or the application needs a restart.

If **logs** stop arriving, on the VPS:

```bash
cd ~/solo-vps
sudo systemctl restart solo-vps-alloy.service
make verify-observability-runtime
```

Then make one new application request and find it in Grafana Logs.

If **metrics** stop arriving:

```bash
cd ~/solo-vps
sudo systemctl restart solo-vps-metrics.service
make verify-metrics-runtime
```

Wait one scrape interval, then select **↻ Refresh** in Grafana Metrics Drilldown.

If a backup fails, do not restart unrelated services. Start with:

```bash
cd ~/solo-vps
make backup-status
```

To create one explicit new off-site snapshot:

```bash
make backup
```

This command writes to external storage. Use it only after off-site backup is configured in chapter 6.

## 8. Replace the Coolify API token before it expires

Chapter 2 created the CI token with a 30-day lifetime. Do not wait for the next release to discover that it expired.

**In Coolify:**

1. Open **Keys & Tokens → API Tokens**.
2. Create a new token with the same minimum permissions: `deploy`, `write`, and `read`; leave `root` and `read:sensitive` off.
3. Save the new token in your password manager. Keep the old token for now unless it is compromised.

**In GitHub → application repository → Settings → Environments → production:**

4. Under **Environment secrets**, update `COOLIFY_API_TOKEN` with the new value.
5. The next normal release should complete deployment successfully.
6. After a successful deployment, delete the old token in Coolify.

If a token leaked, the order changes: revoke it immediately, then create a replacement and update the GitHub secret. Do not keep a compromised credential alive just to make validation easier.

## 9. Prepare for a planned reboot

Solo VPS does not enable automatic reboot after Ubuntu security updates. If the system says a reboot is required, choose a maintenance window when you can verify the server immediately afterward.

**Before reboot, on the VPS:**

```bash
cd ~/solo-vps
make verify
make audit
```

If chapter 6 is configured:

```bash
make backup-status
```

Also:

1. confirm there is no active GitHub/Coolify deployment;
2. confirm the latest required PostgreSQL backup completed successfully;
3. check `/healthz` before the maintenance window begins.

Only then run:

```bash
sudo reboot
```

The SSH session will disconnect. Wait for the host to boot and reconnect as the configured administrator.

**After reboot:**

```bash
cd ~/solo-vps
make verify
make audit
```

If chapters 3, 6, and 7 are configured, also run:

```bash
make verify-observability-runtime
make verify-metrics-runtime
make backup-status
systemctl list-timers solo-vps-backup.timer --no-pager
```

Then verify externally:

- application `/healthz`;
- UptimeRobot has returned to **UP**;
- fresh logs and metrics appear in Grafana.

!!! note "Do not reboot production just to practise"
    Do not reboot a working production VPS only to tick a documentation box. Use this checklist when a reboot is actually required. Use a disposable/test VPS for a separate rehearsal.

## 10. Do not upgrade Docker and Coolify "while you are here"

Review the currently supported lifecycle with the read-only command:

```bash
cd ~/solo-vps
make update
```

It **does not upgrade** Docker or Coolify.

Ubuntu security updates are handled separately and automatic reboot is disabled. Change Docker major versions and Coolify only through the [upgrade guide](../upgrades.md) and inside the version window supported by the current Solo VPS release.

Do not enable a floating `latest`, unattended Coolify upgrades, or a manual Docker package upgrade simply because an upstream version appeared. A control-plane change needs backup/recovery prerequisites and a clear verification path first.

## 11. A short incident sequence

When something breaks, use the same order every time:

```text
1. What is unavailable: the app, Coolify, SSH, or the whole VPS?
2. Was there a deploy, ENV change, update, or reboot just before it?
3. Is an operation still active? If yes, do not start another one.
4. Do GitHub/Coolify show a release error or a runtime error?
5. Do Grafana Logs explain the application failure?
6. Do Grafana Metrics show CPU/RAM/disk exhaustion?
7. What do make ops-status / make verify / make audit report?
8. Only then make the smallest corrective change.
```

Do not begin an incident with `docker rm`, `chmod -R`, deleting `/data/coolify`, disabling the firewall, or recreating secrets. Those actions destroy evidence and can turn a local fault into a recovery problem.

## Done

This chapter is complete when these boundaries are clear:

- a red PR or build before deployment does not change production;
- `DEPLOY_FAILED_ROLLBACK_OK` restores the previous image, not database state or external side effects;
- timeout/unknown deployment status means you wait for the first operation before starting another;
- the application, retained logs, metrics, and backup runtime are verified independently;
- planned maintenance has a baseline and recovery material before the change, then verification afterward;
- a Docker/Coolify upgrade is not an ordinary "while I am here" package update.

For rarer operations, continue with the dedicated [Docker/Coolify upgrade guide](../upgrades.md) and [lost-VPS recovery guide](../disaster-recovery.md).
