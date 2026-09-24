# 7. Watch CPU, memory and disk in Grafana

Logs answer “what happened?”. Metrics show **what happened to the VPS itself over time**: whether CPU load grew, memory became scarce or disk space started running out.

This chapter does not build a large monitoring stack. Solo VPS starts a small separate Grafana Alloy process that reads only a few Linux host metrics and sends them to Grafana Cloud. The log service from chapter 3 keeps running separately.

By the end of the chapter you should be able to:

- find CPU, memory and disk data in **Grafana → Drilldown → Metrics**;
- view useful percentages in Explore;
- receive a test email notification from Grafana;
- make a real disk alert enter `Firing`, receive the email and return the rule to a normal state.

## Before you start

You need:

- a working VPS after chapters 1–2;
- a local `solo-vps` checkout on your computer;
- a Grafana Cloud account. If you completed chapter 3, use the **same stack**;
- working SSH access to the configured VPS `admin.user`.

Metrics use the same pinned Alloy binary but a separate `solo-vps-metrics.service`. It does not need the Docker socket and does not change the log service `solo-vps-alloy.service`.

## 1. Get three Grafana Cloud Metrics values

**In a browser:** open the [Grafana Cloud Portal](https://grafana.com/), select your stack and find the **Prometheus** card. Click **Details**.

Save these values in your password manager:

1. **Remote Write Endpoint** — an HTTPS URL ending in `/api/prom/push`;
2. **User** — the numeric Metrics instance ID;
3. a separate access-policy token with only **`metrics:write`**.

For the token, open Cloud access policies, create a policy such as `solo-vps-metrics`, add the `metrics:write` scope, then create and copy a token. Treat the token as a secret; do not paste it into issues, chats or Git.

[Grafana Cloud Metrics documentation](https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/metrics/metrics-prometheus/query-http-api/) uses the same values: Remote Write Endpoint and User come from **Prometheus → Details**, and the token is the Basic Auth password.

## 2. Prepare local encryption if you have not already done it

If chapters 3 or 6 already work on this computer and `test-age-key` passes, **do not recreate** the existing age key.

### Windows PowerShell

**On your computer, in the Solo VPS directory:**

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
.\scripts\windows\install-secrets-tools.ps1
.\scripts\windows\new-age-key.ps1
.\scripts\windows\init-sops-policy.ps1
.\scripts\windows\test-age-key.ps1
```

Repeated runs reuse a valid existing key and policy. Expect:

```text
PASS Solo VPS production age key SOPS roundtrip
```

If `init-sops-policy.ps1` reports an old-recipient mismatch, do not delete files manually. For an intentional clean onboarding replay, use the previously documented `-StartFresh` path.

### Linux computer

**On your computer, in the Solo VPS directory:**

```bash
make secrets-tools
solo_age_keygen="$(python3 scripts/secrets_toolchain.py paths | sed -n 's/^age-keygen=//p')"
mkdir -p ~/.config/solo-vps
chmod 700 ~/.config/solo-vps
if [ ! -e ~/.config/solo-vps/age-key.txt ]; then
    "$solo_age_keygen" -o ~/.config/solo-vps/age-key.txt
fi
chmod 600 ~/.config/solo-vps/age-key.txt
make init-sops-policy SOPS_AGE_RECIPIENT="$("$solo_age_keygen" -y ~/.config/solo-vps/age-key.txt)"
```

Keep the private age key only on your computer and in your separate recovery copy. Do not copy it to the VPS.

## 3. Encrypt Metrics credentials and send them to the VPS

### Windows PowerShell

**On your computer, in the Solo VPS directory:**

```powershell
$ServerIp = 'YOUR_SERVER_IP'
$AdminUser = 'YOUR_ADMIN_USER'
.\scripts\windows\init-metrics-secrets.ps1
.\scripts\windows\test-metrics-secrets.ps1
.\scripts\windows\push-metrics-secrets.ps1 -VpsHost $ServerIp -VpsUser $AdminUser
```

The first command asks for:

```text
Grafana Cloud Prometheus remote write URL
Grafana Cloud Metrics user ID
Grafana Cloud access-policy token (metrics:write)
```

The token input is hidden. If `metrics.enc.yaml` already exists and decrypts with the current age key, the helper validates and reuses it instead of overwriting it.

**Expected result:**

```text
PASS workstation-to-VPS metrics credential delivery
```

The VPS receives `/etc/solo-vps/metrics/grafana-cloud.json` as `root:root` mode `0600`. Credential values are not printed.

If SSH needs a specific identity, add `-IdentityFile "$env:USERPROFILE\.ssh\your-admin-key"`.

### Linux computer

**On your computer, in the Solo VPS directory:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
make metrics-secrets-init
make metrics-secrets-check
make metrics-secrets-push METRICS_VPS_HOST="$SERVER_IP" METRICS_VPS_USER="$ADMIN_USER"
```

If needed, add `METRICS_SSH_IDENTITY_FILE="$HOME/.ssh/your-admin-key"`.

## 4. Start metric collection

**Connect to the VPS:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
ssh "${ADMIN_USER}@${SERVER_IP}"
```

**On the VPS:**

```bash
cd ~/solo-vps
make verify-metrics-credentials
make metrics-runtime
make verify-metrics-runtime
```

`make metrics-runtime` verifies the pinned Alloy binary, creates the dedicated non-root `solo-vps-metrics` user, installs the configuration and starts the service. The small supported metric set covers CPU, filesystem, load average, memory and basic system information.

Expect the final verification to report:

```text
service: running/enabled
collector: prometheus.exporter.unix
remote_write: Grafana Cloud Metrics
```

You can also inspect the service directly:

```bash
systemctl status solo-vps-metrics.service --no-pager
```

No public inbound metrics port is opened. Alloy's local HTTP endpoint listens only on `127.0.0.1:12346`.

## 5. Confirm metrics arrived in Grafana

Wait about 1–2 minutes after the first start.

**In Grafana:**

1. Open **Drilldown → Metrics**.
2. Under **Data source**, choose the Prometheus source for your stack.
3. Set the time range in the upper-right corner to at least **Last 15 minutes** or **Last 1 hour**.
4. Search for `node_uname_info`.
5. If the metric does not appear immediately, click the **circular-arrow ↻ Refresh** button next to the time range. This only refreshes the Grafana query; you do not need to restart Alloy.
6. Then find these metrics:

```text
node_cpu_seconds_total
node_memory_MemAvailable_bytes
node_filesystem_avail_bytes
```

You can add this label filter:

```text
job = integrations/node_exporter
```

A brand-new collector can show only one sample at first. Wait a few minutes and click **↻ Refresh** again; the graph will begin filling in.

**Expected result:** the metrics exist and show recent samples from your VPS. The `instance` label should be the host name, for example `prod-001`.

[Metrics Drilldown](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/simplified-exploration/metrics/drill-down-metrics/) is intended for this queryless discovery workflow. If the metric is still missing after refreshing, run `make verify-metrics-runtime` on the VPS.

## 6. View three useful percentages

Drilldown is good for discovering metrics. Use **Explore** for calculated percentages.

**In Grafana:** open **Explore**, select the same Prometheus data source and switch the query editor to **Code**. In this chapter, `Code` belongs here, not in Drilldown.

### CPU busy, %

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{job="integrations/node_exporter",mode="idle"}[5m])) * 100)
```

### Memory used, %

```promql
100 * (1 - node_memory_MemAvailable_bytes{job="integrations/node_exporter"} / node_memory_MemTotal_bytes{job="integrations/node_exporter"})
```

### Root disk used, %

```promql
100 * (1 - node_filesystem_avail_bytes{job="integrations/node_exporter",mountpoint="/"} / node_filesystem_size_bytes{job="integrations/node_exporter",mountpoint="/"})
```

Run the queries one at a time. The goal is not a decorative dashboard; it is to answer three questions: do you have enough CPU, memory and disk?

!!! note "Why there is no ready-made dashboard yet"
    A dashboard becomes useful after you know which charts you actually use. The first Solo VPS release supports a small host-metric set and one actionable alert instead of dozens of panels by default.

## 7. Configure Grafana alert email

In the current Grafana Cloud flow, an email contact point can reject an address that is not a member of your Grafana Cloud organization. The simplest path for this chapter is to use **the same email address you use to sign in to Grafana Cloud**.

If you need a different recipient, add it to the organization first:

1. open the **Grafana Cloud Portal** at `grafana.com` — this is the account portal, not the UI inside one stack;
2. open **Org Settings → Members**;
3. click **Invite New Member**;
4. enter the recipient email and choose the **Viewer** role;
5. accept the invitation from that mailbox;
6. return to the Grafana stack and refresh the page.

!!! warning "Organization members can access Grafana"
    Do not add an arbitrary shared mailbox only to receive alerts if you do not want it to have Grafana access. For this basic chapter, use an email that is already an organization member.

Inside the Grafana stack, open **Alerts & IRM → Alerting → Notification configuration → Contact points** and click **Create contact point** / **New contact point**.

Use:

```text
Name: solo-vps-email
Integration: Email
Addresses: an email of an existing Grafana organization member
```

Click **Save contact point**. Then click **Test** and send a test notification.

Wait for the email. Grafana Cloud does not require an SMTP server on your VPS. **Check Spam/Junk:** the first Grafana message can land there. If it does, mark it as not spam so you do not miss a real alert later.

If Grafana shows an error similar to:

```text
Failed to save the contact point
Invalid receiver: invalid email ... addresses ... are not members of this organization
```

this is **not an SMTP problem and not a Solo VPS problem**. The address is not a member of the current Grafana Cloud organization. Use the email of your current Grafana user, or first add the desired address through **Org Settings → Members**.

Keep resolved messages enabled; after the test `Firing` state we also want a recovery notification.

[Grafana Cloud member management](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/account-management/cloud-portal/) documents **Org Settings → Members → Invite New Member**.

## 8. Test a real disk alert without filling the disk

Now we will prove the real `metric → alert rule → email` path **without filling the disk**. For a few minutes, use a deliberately test-only threshold of free space `< 101%`. Every normal disk has less than 101% free space, so the rule is guaranteed to fire.

This guide uses Grafana's **default simplified rule editor**. Keep the **Advanced options** toggle in section 2 **off**. In this mode Grafana reduces the query for you and compares it with the threshold directly, so you do not need to create separate `Reduce` or `Threshold` expressions.

### 8.1. Open a new rule

Open:

**Alerts & IRM → Alerting → Alert rules → New alert rule**.

The page is split into numbered sections `1` through `6`.

In **1. Enter alert rule name**, enter:

```text
solo-vps-root-disk-low
```

### 8.2. Add the free-disk query

In **2. Define query and alert condition**:

1. choose your stack Prometheus data source in the left dropdown — the same `...-prom` source you used in Explore;
2. click **Code** above the query field;
3. paste:

```promql
100 * node_filesystem_avail_bytes{job="integrations/node_exporter",mountpoint="/"} / node_filesystem_size_bytes{job="integrations/node_exporter",mountpoint="/"}
```

4. click **Run queries**.

The query returns the **percentage of free space** on `/`. If the VPS has 85% free, the result is roughly `85`.

If there is no result, test the same PromQL in **Explore** first, then click **Run queries** again. Do not save an alert rule with an empty query result.

### 8.3. Set the temporary test threshold

Directly **below the query** is the small **Alert condition** box. In the current default UI it looks like:

```text
WHEN QUERY   IS ABOVE   0
```

Change only this row:

1. leave `WHEN QUERY` unchanged;
2. click **IS ABOVE** and choose **IS BELOW**;
3. replace `0` with `101`.

The row should read:

```text
WHEN QUERY   IS BELOW   101
```

You do **not** need to create a `Rule A`, `Reduce`, `Threshold expression`, or another query.

Click **Preview alert rule condition**. Because actual free disk space is always below 101%, the preview should show that the condition is met.

### 8.4. Choose a folder

In **3. Add folder and labels**, Grafana requires a folder before it can save the rule.

If you do not already have one:

1. click **New folder**;
2. create `Solo VPS`;
3. select it for this rule.

Labels are optional for the first rule.

### 8.5. Configure evaluation

In **4. Set evaluation behavior**:

1. choose an existing evaluation group with a `1m` interval;
2. if there is none, click **New evaluation group**, name it `solo-vps-1m`, and set **Evaluation interval: 1m**;
3. under **Pending period**, click **None**;
4. under **Keep firing for**, leave **None**.

For this test we want the rule to enter `Firing` at the next minute evaluation.

### 8.6. Select the recipient

In **5. Configure notifications**, find **Contact point** and select:

```text
solo-vps-email
```

If `solo-vps-email` is not in the list, stop here: finish step 7 first and make its **Test** succeed.

The **Advanced options** toggle is not needed here either.

### 8.7. Save and wait for Firing

Section **6. Configure notification message** is optional. For a clearer email you can use:

```text
Summary: Solo VPS root disk has low free space
Description: Free space on / crossed the configured threshold.
```

Click **Save** at the bottom.

Then:

1. open **Alerts & IRM → Alerting → Alert rules**;
2. find `solo-vps-root-disk-low`;
3. wait for the next evaluation — with a `1m` interval this normally takes one or two minutes;
4. confirm the state becomes **Firing**;
5. wait for the email sent to `solo-vps-email`; if it is not in the inbox, check **Spam/Junk**.

If the page does not update, click Grafana's **↻ Refresh** button and check the rule again.

!!! warning "101% is only a test threshold"
    It is deliberately unsuitable for production so the alert fires safely. Do not leave it configured after this exercise.

### 8.8. Return to a production threshold

After the test email arrives, edit the same rule.

In section **2**, change only the number in the Alert condition row:

```text
WHEN QUERY   IS BELOW   15
```

In section **4**, change:

```text
Pending period: 5m
Keep firing for: None
```

Save the rule.

On a normal VPS with more than 15% free space on `/`, the rule should return to **Normal** after the next evaluation. If resolved messages are enabled, Grafana also sends a recovery notification.

If the VPS already has less than 15% free space, that is a real capacity problem rather than a failed test; free space or enlarge the disk first.

**Production meaning:** alert when `/` remains below 15% free space for at least five minutes.

## 9. What to use later

For a routine health check:

```bash
cd ~/solo-vps
make verify-metrics-runtime
```

In Grafana, start with **Drilldown → Metrics** and inspect CPU, memory and filesystem metrics. Move to Explore only when you need a calculated query or exact comparison.

Do not alert on every metric. A useful alert must imply an action. For example:

- low `/` free space → find growing data/logs and clean them up or enlarge the disk;
- memory stays close to the limit → identify the consumer and decide whether the VPS needs more RAM;
- CPU remains high → inspect application/container load.

Application metrics such as HTTP `500` counts, request latency or queue depth require instrumentation in the application itself and are **outside this basic chapter**.

## If metrics do not appear

**On the VPS:**

```bash
cd ~/solo-vps
make verify-metrics-credentials
make verify-metrics-runtime
sudo journalctl -u solo-vps-metrics.service -n 100 --no-pager
```

Also confirm Grafana is using the **Prometheus** data source, not Loki, and the selected time range includes the last few minutes.

For `401`/`403`, re-check the Metrics User ID and confirm the token has `metrics:write`. Do not broaden the token to administrator privileges just to make the error disappear.

## Done

The chapter is complete when all four statements are true:

1. `make verify-metrics-runtime` passes;
2. CPU, memory and filesystem metrics are visible under **Drilldown → Metrics**;
3. the contact-point test email arrives;
4. `solo-vps-root-disk-low` entered `Firing`, sent an email, and returned to normal after changing to the production `15%` threshold.

The server now has more than logs and an external uptime monitor: you can see resource exhaustion developing before it turns into an outage.
