# 5. Get notified when the application is down

Logs help explain an error **after** it happened. An external uptime monitor solves a different problem: it regularly opens your application and tells you when it stops responding.

The monitor runs outside the VPS, so it can still notify you when the whole server is unavailable.

This chapter uses **UptimeRobot Free**. You do not need a second VPS for the basic path: the free plan checks an HTTP(S) address every 5 minutes and can send both outage and recovery notifications.

<div class="solo-delivery-flow" role="list" aria-label="How external uptime monitoring works">
  <div role="listitem"><span>1</span><div><strong>UptimeRobot · internet</strong><p>Opens the public /healthz every few minutes.</p></div></div>
  <div role="listitem"><span>2</span><div><strong>Application · VPS</strong><p>Returns HTTP 200 while public routing and the application work.</p></div></div>
  <div role="listitem"><span>3</span><div><strong>Email · off VPS</strong><p>Receives DOWN and then UP after recovery.</p></div></div>
</div>

## Before you start

You need the working public application URL from chapter 2, for example:

```text
https://app.example.com/healthz
```

Use the application's final HTTPS URL on normal port `443`. Do not monitor Coolify `8000/6001/6002`, container port `8080`, SSH, or Docker.

First open `/healthz` in a browser or check it from your workstation:

```bash
curl -i https://app.example.com/healthz
```

You need an `HTTP 200` response.

If your application does not have `/healthz` yet, add a small public endpoint that returns `200` when the application is ready for requests. Do not put tokens or other secrets in the URL.

## 1. Create a UptimeRobot account

Open [UptimeRobot](https://uptimerobot.com/) and create a free account or sign in to an existing one.

A paid plan is not required for this chapter. Free checks run every 5 minutes, which is enough to learn about downtime for a small project without operating a monitoring server yourself.

After signing in, open **Monitors**.

## 2. Create an HTTP monitor

Click **Add New Monitor** or **New Monitor** and choose **HTTP(s)**.

Use these starting values:

| Field | Value |
| --- | --- |
| URL | `https://app.example.com/healthz` |
| Friendly Name | a clear name such as `solo-vps-demo` |
| Monitoring Interval | `5 minutes` on Free |
| Alert Contact | your email |

If the UI exposes a timeout, `10 seconds` is a reasonable starting value. You do not need the other advanced options for the first monitor.

Save it and wait until the monitor reports **Up**.

> The email/contact must be attached to this specific monitor. Having an email address in the account does not by itself enable notifications for a monitor.

## 3. Test the notification channel

Open the monitor and find **Test Notification**.

Send a test to the selected email and confirm that it actually arrives. UptimeRobot sends the simulated DOWN/UP messages through the same delivery channel used for real incidents.

Do not continue until the test message arrives. **UptimeRobot messages, especially the first one, can land in Spam/Junk.** Check those folders and mark the message as not spam if needed. Also make sure the contact includes both **Down** and **Up** events.

## 4. Cause one real short outage

Use **only the demo application or another resource that is safe to stop**. Do not stop a production application just for this exercise.

Before the test, make sure the monitor is **Up**.

**In Coolify:**

1. open `solo-vps-demo`;
2. click **Stop**;
3. confirm in a browser that `https://app.example.com/healthz` no longer succeeds;
4. change nothing else and wait for UptimeRobot.

On Free, the next scheduled check may happen immediately or almost 5 minutes later. UptimeRobot also performs confirmation retries after a failed check, so a **Down** message is not expected instantly.

Wait for both facts:

- the monitor becomes **Down**;
- the outage notification arrives by email.

If the monitor is already Down but no email arrives, first verify that the Alert Contact is attached to this monitor.

## 5. Restore the application

Return to Coolify and click **Start**.

First verify it yourself:

```bash
curl -i https://app.example.com/healthz
```

You need `HTTP 200` again.

Then wait for the next external check. The monitor should return to **Up** and the same email should receive a recovery notification.

You have now tested the complete path:

```text
application works
→ external service sees HTTP 200
→ application stops
→ DOWN arrives
→ application starts
→ UP arrives
```

## 6. Keep the monitor enabled

Do not delete the monitor after the exercise. Leave it active — this is when it starts becoming useful.

For planned maintenance on the free plan, the simple option is to **Pause the monitor**, perform the work, then immediately **Resume** it. Paid UptimeRobot plans also provide Maintenance Windows.

Do not pause monitoring for ordinary deployments: the rolling deployment path from chapter 2 should keep the public application available.

## If a notification does not arrive

Check these in order:

1. `/healthz` is actually unavailable from the internet, not only from inside Coolify;
2. the monitor is not Paused;
3. the email/contact is Active;
4. the contact is attached to the correct monitor;
5. both Down and Up events are enabled;
6. check Spam/Junk — UptimeRobot outage and recovery messages can land there too.

If the monitor remains **Up**, open its incident/check history and inspect the HTTP result UptimeRobot sees.

## What this proves

After this chapter, an external service independent of the VPS can detect that your public application is unavailable and deliver DOWN/UP notifications.

Stopping only the application does **not independently prove total VPS loss detection**. Before the Solo VPS public release, that more destructive scenario is tested on a disposable/test server: power the VPS off from the hosting control panel, observe Down externally, power it back on, then observe Up. There is no reason to power off a working server just to follow the beginner guide.

You can also inspect the repository's internal policy without making network requests:

```bash
make uptime-plan UPTIME_HEALTH_URL=https://app.example.com/healthz
```

This command is optional for normal operation.

**Done:** if you actually received the test notification, DOWN, and then UP/recovery, this chapter is complete.

**Next:** [chapter 6](offsite-backups.md) moves PostgreSQL, Coolify and filesystem backups **outside the VPS itself**.
