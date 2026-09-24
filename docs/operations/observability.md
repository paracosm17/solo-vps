# 3. Keep application logs in Grafana

After this chapter, you will be able to find an application's log entries by time and text, including entries from a container that has already been replaced by a new deployment.

Complete [VPS setup](../quick-start.md) and [application delivery](first-app.md) first. Keep using Coolify **Logs** for a quick look at the running application. This chapter adds searchable history.

<div class="solo-delivery-flow" role="list" aria-label="How application logs reach your browser">
  <div role="listitem"><span>1</span><div><strong>Application · VPS</strong><p>The application writes requests and errors to its container log.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Grafana Alloy · VPS</strong><p>The agent reads those entries and sends them over HTTPS.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Grafana Cloud · browser</strong><p>Loki stores the entries. Grafana lets you search and download them.</p></div></div>
</div>

The setup does **not** require a second VPS. It collects stdout/stderr from Coolify-managed applications and service containers on this host. It does not collect host metrics, GitHub Actions build logs or standalone database logs.

Before enabling collection, check that the applications' logs are suitable for sending to Grafana Cloud. The agent does not automatically remove passwords, tokens or personal data. Existing container logs may also be sent when collection starts.

## Before you begin

You need the working demo, SSH access as the configured `admin.user`, and the **same Solo VPS revision on both your workstation and VPS**. This is the first guided chapter that runs Solo VPS helper scripts directly on your workstation.

If the Solo VPS directory is already present on your workstation, use it and do not download another copy. If it is missing, prepare the same source you used for the server:

- **Git:** clone `<repository-url>`, enter `solo-vps`, then check out the same `<reviewed-revision>` from chapter 1.
- **ZIP:** unpack the same Solo VPS ZIP on your workstation and open a terminal in that directory.

The workstation needs an Internet connection to download the encryption tools; the VPS needs outbound HTTPS to download Alloy and send logs. Reuse `SERVER_IP`, `ADMIN_USER` and the application domain from the basic chapters. The source directory on the VPS remains `~/solo-vps`.

In steps 3 and 4, follow the commands for your workstation OS. Commands marked **VPS** run in the SSH session, not in local PowerShell.

## 1. Create a Grafana Cloud account and stack

**In your browser:**

1. Open [Grafana Cloud](https://grafana.com/products/cloud/) and select **Create free account**.
2. Complete registration using the offered sign-in method; verify your email if requested.
3. Open the **Cloud Portal**. A *stack* is your Grafana workspace and its associated log storage.
4. Use the stack that registration created for you. The Free plan allows one stack, so do not create a duplicate. If you use a paid plan and actually need a new stack, **Add Stack** is in the Cloud Portal; choose its name and data region there.
5. Open the stack and use **Launch** on the Grafana tile to open its Grafana interface. Keep the portal open in another tab.

If you already have an account, sign in and use the existing stack you want Solo VPS logs to reach. The registration and stack controls are described in [Grafana's account guide](https://grafana.com/docs/grafana-cloud/learn-and-build/get-started/) and [stack guide](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/account-management/cloud-stacks/create-update-stacks/).

Before sending logs, check the current plan's **retention** and **monthly log allowance**. Grafana currently documents a 50 GB monthly log allowance on Free and a minimum 14-day retention for Free accounts; service limits can change, so verify the [current pricing](https://grafana.com/pricing/) and your account's usage/billing page. A three-day-old incident needs at least three days of retained history; a month-old incident needs longer retention.

**Expected result:** the portal shows the selected stack, and its Grafana interface opens. Record the chosen retention period for the later history check.

## 2. Get the three connection values

**In the Cloud Portal:**

Open your stack's **Details**, then **Details** on the **Loki / Logs** tile. Find the **Sending Logs to Grafana Cloud using Grafana Alloy** example. Keep the `url` and `username` values from that example. [Grafana documents this location](https://grafana.com/docs/loki/latest/operations/meta-monitoring/deploy/).

**Still in the Cloud Portal:**

1. Open **Security → Access Policies**.
2. Select **Create access policy** and name it `solo-vps-logs`.
3. If the page asks for a realm or stack, select only the stack from the previous step.
4. Enable **Logs → Write** (`logs:write`). Do not add read, delete, metrics or admin permissions for this collector.
5. Create the policy, then select **Add token** for it.
6. Name the token `solo-vps-alloy`, choose an expiry date you can maintain, and create it.
7. Save the token in your password manager immediately. Its value is shown only once.

Grafana documents access policies in the Cloud Portal under **Security**. Some accounts also expose a Cloud access policies page inside the stack UI; either route is fine as long as the policy is scoped to the intended stack and only has `logs:write`. Use a [Cloud access policy](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/create-access-policies/) for Loki ingestion, not a Grafana service-account token.

Use the following mapping when the workstation helper asks for input:

| Helper prompt / stored field | What to enter |
| --- | --- |
| Grafana Cloud Loki push URL / `LOKI_URL` | The complete HTTPS `url` ending in `/loki/api/v1/push` |
| Grafana Cloud Logs user ID / `LOKI_USERNAME` | The numeric `username` from the Loki example |
| Grafana Cloud access-policy token / `GRAFANA_CLOUD_API_KEY` | The token you just created with `logs:write` |

The user ID is not your email, Grafana login or stack name. The push URL is not the address of the Grafana dashboard. Copy values without surrounding quotes. If the portal shows only the Loki base address, append `/loki/api/v1/push` once.

**Expected result:** you have all three values in a protected place. Do not put the token in a command, GitHub variable, application ENV or chat message.

## 3. Prepare encryption on your workstation

Solo VPS keeps an encrypted copy of the connection values on your computer. The private age key unlocks that copy and stays on the workstation.

### Windows PowerShell

**On your workstation, in the Solo VPS directory:**

If this copy came from a downloaded ZIP, Windows can mark its PowerShell files as Internet-downloaded. Remove that mark from the Solo VPS Windows helpers once, then run the installer:

```powershell
Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File
.\scripts\windows\install-secrets-tools.ps1
```

This does not lower your PowerShell execution policy. If `Get-ExecutionPolicy` reports `RemoteSigned`, leave it that way; Solo VPS does not require changing it to `Unrestricted`.

Prepare the encryption key. This command is safe to run again: if the key already exists, the helper validates it and **does not replace it**.

```powershell
.\scripts\windows\new-age-key.ps1
```

Expect `PASS Solo VPS age key created` or `PASS Solo VPS age key already exists`. Do not delete an existing key just to rerun the helper. Then run:

```powershell
.\scripts\windows\init-sops-policy.ps1
.\scripts\windows\test-age-key.ps1
```

Expect `PASS Solo VPS production age key SOPS roundtrip`.

If this workstation has already been used with Solo VPS, policy files and encrypted bundles from an older run may still exist. The helper never deletes them automatically. On a recipient mismatch it prints the current key, the previous recipient, and the number of `*.enc.yaml` bundles.

If you **need the old encrypted files**, stop and recover the previous age key. If you are simply repeating setup and can enter the tokens/passwords again, run:

```powershell
.\scripts\windows\init-sops-policy.ps1 -StartFresh
```

`-StartFresh` does not delete the previous data. It moves the old policy and active `*.enc.yaml` files to `%LOCALAPPDATA%\solo-vps\archive\workstation-secrets\<timestamp>\`, then creates a clean policy for the current key. The private age key stays in place. Run `test-age-key.ps1` again and continue the chapter.

If PowerShell still blocks the helpers after `Unblock-File`, see [workstation secrets troubleshooting](../secrets-sops-age.md#windows-workstation).

### Linux workstation

**On your workstation, in the Solo VPS directory:**

```bash
make secrets-tools
solo_age_keygen="$(python3 scripts/secrets_toolchain.py paths | sed -n 's/^age-keygen=//p')"
test -x "$solo_age_keygen"
mkdir -p ~/.config/solo-vps
chmod 700 ~/.config/solo-vps
if [ ! -e ~/.config/solo-vps/age-key.txt ]; then
    "$solo_age_keygen" -o ~/.config/solo-vps/age-key.txt
fi
chmod 600 ~/.config/solo-vps/age-key.txt
make init-sops-policy SOPS_AGE_RECIPIENT="$("$solo_age_keygen" -y ~/.config/solo-vps/age-key.txt)"
```

This uses the checksum-verified age tool installed by the project and preserves an existing key. Stop if any command fails. The next step checks decryption with this key.

On either OS, keep a recoverable copy of `~/.config/solo-vps/age-key.txt` somewhere you control outside this computer. On Windows, `~` means your user profile. Losing every copy means losing access to the encrypted bundles. Do not copy this key to Git or the VPS. If you already use custom key/state paths, pass those same paths to the helpers.

## 4. Encrypt the token and deliver it to the VPS

Keep a normal SSH session to `ADMIN_USER@SERVER_IP` working before this step. The delivery helper uses non-interactive SSH and passwordless sudo from the basic setup. If your SSH key has a passphrase, load it into your SSH agent first.

### Windows PowerShell

**On your workstation, in the Solo VPS directory:**

```powershell
$ServerIp = 'YOUR_SERVER_IP'
$AdminUser = 'YOUR_ADMIN_USER'
.\scripts\windows\init-observability-secrets.ps1
.\scripts\windows\test-observability-secrets.ps1
.\scripts\windows\push-observability-secrets.ps1 -VpsHost $ServerIp -VpsUser $AdminUser
```

If no encrypted bundle exists yet, the first command asks for the three values from step 2 and hides token input. If a bundle already exists and matches the current key, the helper validates and reuses it without asking again. Stop if a command fails. If SSH needs a specific key, add `-IdentityFile "$env:USERPROFILE\.ssh\your-admin-key"` to the push command, using your existing administrator key.

The encrypted file is `%LOCALAPPDATA%\solo-vps\state\secrets\observability.enc.yaml`.

### Linux workstation

**On your workstation, in the Solo VPS directory:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
make observability-secrets-init
make observability-secrets-check
make observability-secrets-push OBSERVABILITY_VPS_HOST="$SERVER_IP" OBSERVABILITY_VPS_USER="$ADMIN_USER"
```

Enter the same three values when prompted. If needed, add `OBSERVABILITY_SSH_IDENTITY_FILE="$HOME/.ssh/your-admin-key"` to the push command. The encrypted file is under `~/.local/share/solo-vps/secrets/` by default; `make paths` shows the effective location.

If `observability.enc.yaml` already exists and decrypts with the current key, the helper validates it and **reuses it without overwriting it**. This makes the chapter safe to rerun. To enter Grafana credentials again, use `-StartFresh` in step 3 or follow [token replacement](#replace-a-token) below.

If the VPS source directory differs from `~/solo-vps`, set `-RemoteProject` on Windows or `OBSERVABILITY_REMOTE_PROJECT` on Linux.

**Expected result:** the push reports `PASS workstation-to-VPS observability credential delivery`. It decrypts on the workstation and sends the values through SSH stdin. The age key stays on your computer. This step does not start Alloy and does not grant Docker socket access.

## 5. Install and start collection

**Connect from your workstation:**

```bash
SERVER_IP='YOUR_SERVER_IP'
ADMIN_USER='YOUR_ADMIN_USER'
ssh "${ADMIN_USER}@${SERVER_IP}"
```

**On the VPS as the administrator:**

```bash
cd ~/solo-vps
make verify-observability-credentials
make observability-tooling
make observability-runtime
```

Run the commands in order and stop on failure. The credential check validates `/etc/solo-vps/observability/grafana-cloud.json` without printing its values. The tooling command downloads and verifies the pinned Grafana Alloy binary. The runtime command starts collection and includes its own verification.

From the runtime command onward, Alloy sends matching container logs to the stack. Solo VPS configures the required Docker log access for Alloy; do not grant Docker access manually. You do not need to configure a Coolify Log Drain, install another collector from Grafana's setup wizard or open an inbound port.

At the end, expect `alloy_service: running/enabled`, `docker_api_proxy: running` and `current_invocation_diagnostic_errors: false`, with no failed Ansible tasks. This confirms that the agent is running. Finding an application entry in Grafana is the separate delivery check below.

## 6. Find a request in Grafana

**In your browser**, open this URL using your demo's domain:

```text
https://app.example.com/solo-vps-log-check-before
```

The demo deliberately returns `404` and `{"status":"not_found"}`: the unique path does not exist, but the request is written to the log. It changes no application data. In **Coolify → application → Logs**, confirm a line containing `solo-vps-log-check-before`. Record its date, time and timezone.

For normal searching in this chapter, you **do not need Explore or LogQL**. Use Grafana Logs Drilldown instead.

**In Grafana:**

1. In the left menu, open **Drilldown → Logs**.
2. At the top right, check **Data source**. Select the Loki source for your stack, normally named `grafanacloud-<stack>-logs`.
3. Set the range to **Last 15 minutes**.
4. On the overview page, find your application's service card. For the demo it is normally `solo-vps-demo`. If the name differs, use the service that just produced the request and select **Show logs**.
5. On the service page, find the **Line filter** section above the log list. Keep **Include** selected and enter this in **Filter logs by string**:

```text
solo-vps-log-check-before
```

6. A line containing that path should remain. Select it to inspect the timestamp, `service_name` and the other fields/labels.

Grafana Logs Drilldown is designed for browsing Loki without writing queries. [Grafana's current guide](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/simplified-exploration/logs/view-logs/) likewise uses **Drilldown → Logs**, **Show logs** and the line filter.

!!! note "Grafana has two similar text searches"
    For this chapter, use the **Line filter** above the log list: it filters lines by text across the selected time range. The magnifying-glass control in the Logs side toolbar opens **client-side search** and searches only rows that are already loaded. If you see a match counter such as `1/2` with up/down arrows, that is client-side search — close it and use **Line filter** instead. You do not need the **Code** editor here at all.

The `service_name` value comes from Coolify and can differ from the name you expected. Do not guess a container ID. If you have many applications, use **Add label → service_name** or the service-name search on the overview page before selecting **Show logs**.

**Expected result:** the same request appears in Coolify and Grafana with a timestamp and application metadata. A green agent check without this entry is not enough.

## 7. Check history after a deployment and restart

Do this exercise on the demo when no other deployment is running.

1. Confirm the `before` entry from step 6 is already visible in **Drilldown → Logs**.
2. In **Coolify → application**, select **Redeploy** and wait for a successful deployment.
3. Open the following URL with the same application domain:

```text
https://app.example.com/solo-vps-log-check-after
```

4. Return to **Drilldown → Logs → your application**, choose a time range covering both requests, and enter this in **Line filter**:

```text
solo-vps-log-check-
```

Both `solo-vps-log-check-before` and `solo-vps-log-check-after` must be present. The older entry should remain even though the previous container was replaced.

Next, check that collection resumes after an agent restart. **On the VPS as the administrator, in the Solo VPS directory:**

```bash
sudo systemctl restart solo-vps-alloy.service
make verify-observability-runtime
```

After verification passes, open:

```text
https://app.example.com/solo-vps-log-check-restarted
```

With the same **Line filter**, you should now see three entries: `before`, `after` and `restarted`. This proves that the old history survives a redeploy and that fresh logs resume after Alloy restarts. It does not prove lossless delivery through every arbitrary network or collector outage.

Keep the original `before` timestamp privately. **After three actual days**, open the time picker, set an **Absolute time range** covering that request, and find `solo-vps-log-check-before` again with **Line filter**. Use a new suffix when you repeat the exercise so old evidence cannot look like a new run.

## 8. Investigate an older error

When someone reports an error, first get the approximate time, timezone, and—when available—a request ID or recognizable error text.

Open **Drilldown → Logs → the application**:

1. Set an **Absolute time range** around the incident and check the timezone shown by Grafana.
2. Enter the request ID, part of the URL, `error`, or another expected substring in **Line filter**.
3. Open the matching line's **⋮ → Show context** menu to see nearby entries before and after it.
4. Compare the timestamp with **Coolify → Deployments** to identify which release was running.
5. If you need a file, expand the controls on the right and use **Download logs**. Grafana can export `TXT`, `JSON`, or `CSV`. Check the selected range and line count before sharing the file.

Logs Drilldown supports line context and downloads; [Grafana documents both controls here](https://grafana.com/docs/grafana-cloud/learn-and-build/visualizations/simplified-exploration/logs/view-logs/). A saved link or filter does not extend retention.

### When you need LogQL

Normal operation does not require it. For a more complex query, open the log panel's **⋮** menu in Drilldown and select **Explore**. Grafana carries the current context over. In **Explore**, the Loki editor has **Builder** and **Code** modes; in **Code** you can run, for example:

```logql
{job="solo-vps"} |= "solo-vps-log-check-"
```

That is why the **Code** toggle is not visible in Logs Drilldown: it belongs to a different interface. [The Loki query editor guide](https://grafana.com/docs/grafana/latest/datasources/loki/query-editor/) documents Builder/Code in Explore.

Logs deleted before collection began cannot be recovered this way. Logs older than the stack's retention may also be gone. For your own application, use structured logs with clear errors and request identifiers; keep request IDs in the log content instead of turning every ID into a stream label.

## If an entry is missing

| What you see | What to check |
| --- | --- |
| The marker is absent from Coolify Logs | Confirm the domain points to the demo and the request reached it. An application that writes only to private files needs its logging changed to stdout/stderr |
| Coolify has the marker, Grafana does not | Check the selected stack, Loki data source, time range and the exact broad query from step 6. Then run `make verify-observability-runtime` on the VPS |
| No application is found by discovery | The default filter requires `coolify.managed=true` and `coolify.type=application` or `service`. Standalone databases and unrelated containers are excluded |
| Authentication errors | Check the Logs user ID, push URL, token expiry and `logs:write` for the selected stack. Use token replacement below if needed |
| The runtime says Alloy is missing | Run `make observability-tooling` on the VPS, then retry `make observability-runtime` |
| Delivery fails over SSH | Use the existing administrator key; check SSH-agent access, `SERVER_IP`, `ADMIN_USER` and the source directory. The push helper needs passwordless sudo |
| New entries arrive, but old ones do not appear | Check the absolute interval, timezone, retention and whether collection was running then |
| You see duplicate entries | Check whether another collector or Coolify Log Drain is sending the same application logs |

For an authentication/network problem, isolate the connection with **one synthetic entry**. **On the VPS as the administrator, in the Solo VPS directory:**

```bash
make test-observability-loki
```

This sends the fixed, non-secret message `solo-vps retained-log connectivity smoke` directly to Grafana Cloud. Expect HTTP 204. Then open **Drilldown → Logs**, select **Last 15 minutes**, use **Add label** with `job = solo-vps-smoke`, and select **Show logs**. Success proves the endpoint accepts logs; it does not prove application collection. HTTP 401/403 points to authentication or scope; 404 to the URL; 429 to rate/usage limits; network failures or 5xx to connectivity/provider problems.

Do not widen Docker permissions or paste a full environment dump to troubleshoot. [Server diagnostics](status-and-logs.md) covers broader host issues.

## Replace a token

Create a new token for the same stack/policy in step 2. Keep the previous token until the new one works, unless it has leaked and must be revoked immediately.

Create a **new encrypted file**, validate it and push that file explicitly. This avoids deleting the working bundle. For Windows, use the init helper's `-OutputPath` and the check/push helpers' `-EncryptedPath`; for Linux, use `OBSERVABILITY_SECRET_FILE` for all three Make commands. Store it outside the source checkout and record which file is current.

After delivery, run `make observability-runtime` on the VPS. This updates the service's credential file and restarts Alloy when needed. Find a fresh marker in Grafana, then revoke the previous token in Cloud access policies. Keep the encrypted bundle and age key in your recovery material.

## Done: history is searchable

You have checked a real request, old and new entries across a redeploy, and a fresh entry after restarting the agent. The three-day check remains pending until that time has passed.

Keep an eye on retention, ingestion usage and token expiry. This setup adds application logs; host metrics and external outage alerts are separate tasks.

**Next:** choose the next task in [After basic setup](after-basic-setup.md). If the application has a database, prioritize backup and an actual restore.
