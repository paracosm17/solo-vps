# After basic setup

The server is configured, the application opens over HTTPS and GitHub changes reach it automatically. Now add what daily operation needs: retained logs, backups, outage notifications and resource metrics.

There is no need to repeat basic parts 1 and 2. Choose the next step based on what your application already uses.

## Understand daily operation first

[Using the platform every day](operator-ui.md) shows the path from changing code to a running version. It also explains where to change ENV, which logs to open and what to do when a release fails.

## 3. Keep a log history

When an error is reported days later, the current Coolify Logs view may be insufficient. Separate storage lets you search by application, time and text even after replacing a container.

The project provides Grafana Cloud with an Alloy agent on the VPS. The agent sends logs; you read them in Grafana. You do not need to maintain a second server for storage and search.

**Successful setup means:** you find a request by its unique marker, select an exact time range and find the same entry after another deployment. Later, verify it remains available after several days within the chosen retention period.

Choose retention and acceptable volume before enabling collection. New storage cannot recover logs already deleted.

[Configure retained logs](observability.md).

## 4. Add backups when you add a database

For a PostgreSQL application, start with a separate test database: insert a few rows, create a backup and restore it into another empty database. Compare the actual data, not just the operation status.

A local copy on the same VPS helps recover from application mistakes. Losing the disk or VPS loses that copy with the original. It is a first step; valuable data also needs a copy outside the server.

Start with a local copy on the same VPS: Coolify can schedule PostgreSQL backups without S3. Then restore one into a separate test database and compare the data.

The [guided PostgreSQL backup and restore chapter](postgresql-backups.md) walks through that proof from database creation to a restored point in time. The advanced [PostgreSQL reference](../database-backups.md) remains available for S3/API and more automated workflows.

**Successful setup means:** backups run on schedule, old copies are removed according to your chosen rule, and the restored test database contains the expected data. The primary database remains unchanged and working.

## 5. Receive outage notifications

Logs do not alert you until you open them. An external monitor regularly opens the public `/healthz` and reports when the application stops responding.

The first guided path uses UptimeRobot Free: no second VPS is required, checks run outside the server, and DOWN/UP notifications arrive by email.

**Successful setup means:** the test notification arrived, then you safely stopped the demo application, received DOWN, started it again, and received UP/recovery.

[Chapter 5: external uptime alerts](external-uptime.md).

## 6. Move backups off the VPS

A local backup helps after an application mistake, but not after losing the VPS itself. The next step is private S3-compatible storage outside the server.

One guided chapter uploads a PostgreSQL backup, a Coolify control-plane backup, and an encrypted restic snapshot of the required `/data/coolify` files. You then restore PostgreSQL directly from S3 into a separate database and prove the external backup is usable.

**Successful setup means:** usable data is available without the local VPS file, the Coolify backup exists off-server, restic passes a restore test, and the daily off-site timer is enabled.

[Chapter 6: off-site backups](offsite-backups.md). Full [lost-VPS recovery](../disaster-recovery.md) is tested later on a separate replacement server.

## 7. Watch CPU, memory and disk

Logs explain what happened to requests. Metrics show what happened to the VPS at the same time: whether load grew, memory became scarce or disk space started filling up.

Solo VPS uses a separate lightweight Grafana Alloy process and sends a small host-metric set to the same Grafana Cloud stack. You then configure one useful disk alert and prove email delivery with a real firing rule.

**Successful setup means:** CPU, memory and filesystem data are visible in Grafana Metrics Drilldown, and the free-disk alert completed a real `Firing → email → Normal` test.

[Chapter 7: VPS metrics](metrics.md). Application-level metrics such as HTTP error rate are added separately when the application exports them.

## 8. Handle failures and planned maintenance

Once the normal path works, you need to distinguish a red PR, a build failure, a failed deployment, and an actual production outage. The next chapter turns those cases into one sequence and adds checklists for ENV mistakes, collector restarts, CI API-token replacement, and planned reboot.

**Result:** you know when production never changed, how to read `DEPLOY_FAILED_ROLLBACK_OK`, why an unknown deployment must finish before another starts, and what to verify before and after maintenance. A destructive reboot is not required just to complete the chapter.

[Failures and maintenance](incidents-and-maintenance.md).

## When to move to your own application

You can deploy an application without valuable data after the basic chapters. Before storing important database data, test backup and restore. Add retained logs and external alerts for an application with users.

Complete one task at a time: configure it, observe the result, then continue.
