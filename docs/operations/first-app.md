# 2. Deploy an application and enable CI/CD

Continue from [part one](../quick-start.md): your VPS is configured and the Coolify dashboard opens over HTTPS. Now create a demonstration application, deploy it and enable automatic delivery from GitHub. Then change an environment variable and inspect the logs.

Every required action is on this page. Reference pages are for additional configuration after you finish.

## Before you begin

Your workstation needs Git, Python 3.12 or newer, and the same Solo VPS source you used on the server. For a ZIP, extract it into a separate `solo-vps` directory. Start commands in the directory containing `Makefile` and `scripts`.

You also need a GitHub account with working `git push` authentication. This walkthrough uses a new public repository and public image, containing no private code or real secrets, so the VPS needs no additional registry credentials.

| Name | Value |
| --- | --- |
| `SERVER_IP` | Your VPS IPv4 address from part one |
| `ADMIN_USER` | The value of `admin.user` from part one |
| `APP_DOMAIN` | Your demonstration application's domain, for example `app.example.com` |
| `GITHUB_OWNER` | Your GitHub username or organization |
| `APPLICATION_REPOSITORY_URL` | The new repository URL copied from GitHub |

The application is named `solo-vps-demo`. Its directory will sit beside `solo-vps`, not inside it. The example does not need a database.

## 1. Create the GitHub repository

**In your browser, on GitHub:**

1. Select **+ → New repository**.
2. Set **Repository name** to `solo-vps-demo`.
3. Select **Public**.
4. Leave README, `.gitignore` and license initialization disabled.
5. Select **Create repository**.
6. Copy the empty repository's HTTPS or SSH URL, using the method for which you have working `git push` authentication.

Keep this tab open. Use a new empty repository: an older project's files and rules can block the initial push.

## 2. Create the application on your workstation

**On your workstation, open a terminal in the solo-vps directory:**

=== "Windows PowerShell"

    ```powershell
    python scripts/create_app.py ../solo-vps-demo
    ```

=== "Linux"

    ```bash
    python3 scripts/create_app.py ../solo-vps-demo
    ```

Wait for `Created application:` and the new directory path before continuing. If the destination exists, the helper does not overwrite it: choose a different unused name and use that name in subsequent steps.

**In the same workstation terminal, PowerShell or Linux:**

```bash
cd ../solo-vps-demo
git init -b main
git add .
git commit -m "Create demo application"
```

Your separate repository now contains the application, Dockerfile and complete workflow at `.github/workflows/app.yml`.

## 3. Push the application and wait for its first image

**On your workstation, in solo-vps-demo:**

```bash
APPLICATION_REPOSITORY_URL='YOUR_APPLICATION_REPOSITORY_URL'
git remote add origin "$APPLICATION_REPOSITORY_URL"
git push -u origin main
```

**On GitHub, in solo-vps-demo → Actions:**

1. Open the **Hello app CI** run for the first commit.
2. Wait for green **Application tests**, **Application migration preflight**, **Publish main image** and **Verify published image by digest** jobs.
3. In the run summary, copy **Published immutable image**. Its format is:

```text
ghcr.io/<github-owner>/solo-vps-demo@sha256:<64-hex-digest>
```

This identifies the exact image you built. Keep it for the next step. **Build pull request image** and **Deploy immutable image to Coolify** are expected to be skipped here. Do not create `SOLO_VPS_DEPLOY_ENABLED` yet.

**On GitHub, open the repository owner's profile → Packages:**

1. Open `solo-vps-demo`, then **Package settings**.
2. Under **Danger Zone → Change visibility**, select **Public** and confirm the visibility change for this demonstration package.

If the package is already Public, leave it as it is. Repository and package visibility are separate settings.

## 4. Prepare the application domain

**In your domain's DNS panel**, create:

| Type | Name | Value |
| --- | --- | --- |
| A | `app` | VPS IPv4 address |

The example is `app.example.com`. With Cloudflare, select **DNS only**. Add an AAAA record only when working IPv6 is configured.

## 5. Create the application in Coolify

**In Coolify:**

1. Open **Projects** and create a project named `solo-vps-demo`.
2. Open its `production` environment.
3. Select **+ New Resource → Docker Image**, then the existing **localhost** server.
4. Set **Image Name** to just `ghcr.io/<github-owner>/solo-vps-demo`, replacing the owner.
5. Complete resource creation.

**In the created application → Configuration → General**, set:

| Field | Value |
| --- | --- |
| Name | `solo-vps-demo` |
| Docker Image | The published reference before `@`: `ghcr.io/<github-owner>/solo-vps-demo` |
| Docker Image Tag or Hash | `sha256-` followed by all 64 characters after `sha256:` in the published reference |
| Domains | `https://app.example.com`, replacing the domain |
| Ports Exposes | `8080` |
| Ports Mappings | Leave empty |
| Custom Docker Options | Leave empty |

**Docker Image Tag or Hash** needs a **hyphen** after `sha256`, not a colon. Set these two fields **after creating the resource**: Coolify 4.1.2's creation form can misparse a complete digest reference.

Leave the additional Coolify **Health Check** disabled: the Dockerfile already checks `/healthz`. Port `8080` is inside the container; HTTPS access does not require `8080:8080` in Ports Mappings.

Select **Save**.

## 6. Deploy the first image

**In the Coolify application:**

1. Select **Deploy**.
2. Open **Deployments** and the current deployment log.
3. Wait for successful completion and **Running / Healthy**.

**In your browser**, open your domain:

- `https://app.example.com/` — JSON containing `version: "1"` and `message: "Hello from Solo VPS"`;
- `https://app.example.com/healthz` — `{"status":"ok"}`.

Open the application's **Logs** in Coolify: these HTTP requests should appear there.

Continue after the first deployment succeeds. CI needs a working application to update.

## 7. Create a dedicated SSH key for CI {#ci-key}

**On your workstation, in a new terminal:**

GitHub Actions will use this key. Your personal administrator key is not needed for CI. If you already created this CI key, skip `ssh-keygen` and use the existing key. Do not confirm overwriting it.

=== "Windows PowerShell"

    ```powershell
    $SshDir = Join-Path $HOME '.ssh'
    $CiKey = Join-Path $SshDir 'solo-vps-demo-ci'
    New-Item -ItemType Directory -Force -Path $SshDir | Out-Null
    ssh-keygen -t ed25519 -f $CiKey -C 'solo-vps-demo CI'
    ```

    Press **Enter** at both passphrase prompts to leave it empty: CI runs without interactive input.

    Transfer only the public part to the VPS:

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    scp "$CiKey.pub" "${AdminUser}@${ServerIp}:/home/${AdminUser}/.ssh/solo-vps-demo-ci.pub"
    ```

=== "Linux"

    ```bash
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    ssh-keygen -t ed25519 -f ~/.ssh/solo-vps-demo-ci -C 'solo-vps-demo CI'
    ```

    Press **Enter** at both passphrase prompts to leave it empty: CI runs without interactive input.

    Transfer only the public part to the VPS:

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    scp ~/.ssh/solo-vps-demo-ci.pub "${ADMIN_USER}@${SERVER_IP}:/home/${ADMIN_USER}/.ssh/solo-vps-demo-ci.pub"
    ```

The private file without `.pub` stays on your workstation.

## 8. Create the restricted CI user on the VPS

**On your workstation, connect to the VPS:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    ssh "${AdminUser}@${ServerIp}"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    ssh "${ADMIN_USER}@${SERVER_IP}"
    ```

**In this SSH session on the VPS as the administrator:**

```bash
cd ~/solo-vps
nano ~/.local/share/solo-vps/config/config.yml
```

Add this at the end, with no indentation before `ci_deploy`:

```yaml
ci_deploy:
  ssh_public_key_file: ~/.ssh/solo-vps-demo-ci.pub
```

If that section already exists, edit its field instead of adding a duplicate. A commented example beginning with `#` is not an active setting. Preserve the rest of the file. In nano, save with **Ctrl+O → Enter → Ctrl+X**.

**On the VPS as the administrator, in the same directory:**

```bash
SERVER_IP='YOUR_SERVER_IP'
make plan-ci-deploy-transport CI_DEPLOY_SERVER_HOST="$SERVER_IP" CI_DEPLOY_PUBLIC_KEY_FILE="$HOME/.ssh/solo-vps-demo-ci.pub"
```

Check the plan shows your `server_host`, user `solo-vps-ci`, and API address `127.0.0.1:8000`. Then apply it:

```bash
CI_DEPLOY_TRANSPORT_CONFIRM=I_HAVE_REVIEWED_THE_RESTRICTED_CI_SSH_TRANSPORT make ci-deploy-transport
```

Expect `failed=0`, `unreachable=0` and a message confirming the CI identity is restricted to forwarding to `127.0.0.1:8000`. Verification is included in the command.

The new `solo-vps-ci` user has no shell, sudo or Docker access. It lets CI contact the Coolify API through an SSH tunnel. Your configured administrator remains the normal human access.

## 9. Prepare two public values for GitHub

**In the open, trusted SSH session on the VPS as the administrator:**

Prepare two values for step 11. Leave the output in this terminal or save each value with its name in a note: in a few minutes, you will paste them into GitHub in the same order.

**First — `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`, the CI key's fingerprint:**

```bash
ssh-keygen -lf ~/.ssh/solo-vps-demo-ci.pub -E sha256 | awk '{print $2}'
```

The command prints only the ready-to-use `SHA256:...` value. Copy it **in full, including `SHA256:`**. The prefix is required; the characters after the colon alone will not work. The separate `256` in the full `ssh-keygen` output is the key length; this command already removes it.

**Second — `SOLO_VPS_SSH_KNOWN_HOSTS`, the server's own key line:**

```bash
SERVER_IP='YOUR_SERVER_IP'
awk -v host="$SERVER_IP" '{print host " " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

Copy the entire single line `IP ssh-ed25519 ...`. This is `SOLO_VPS_SSH_KNOWN_HOSTS`. Its IP must match `SOLO_VPS_DEPLOY_HOST`.

The first value checks the key CI uses to connect. The second lets CI recognize your server. Both are public; the private server key is not needed.

## 10. Create a Coolify API token

**In Coolify as the administrator:**

1. Open sidebar **Settings**, then **Configuration → Advanced**.
2. Enable **API Access** and save the change.
3. Select **Keys & Tokens** in the left sidebar, then the **API Tokens** tab. The page heading is **Security**.
4. Set **Description** to `solo-vps-demo CI`.
5. Keep **30 days** expiry. Before it expires, create a replacement token and update the GitHub secret.
6. Select **deploy** first, then **write** and **read**. The **Permissions** line must contain all three. Leave `root` and `read:sensitive` unchecked.
7. Select **Create** and immediately copy the token into your password manager: it is shown only once.

The token covers the current Coolify team, rather than just one application. Use the team containing `solo-vps-demo` for this walkthrough.

Open the application and copy its UUID from the address bar: the segment after `/application/`, ending before the next `/` or `?`, if present. Do not use the project, environment or server UUID. This is `COOLIFY_RESOURCE_UUID`.

## 11. Fill in the GitHub production environment {#github-production}

**On GitHub, in the solo-vps-demo repository:**

1. Open **Settings → Environments**.
2. Select **New environment**, enter `production`, then **Configure environment**. If it exists already, open it.
3. Under **Environment secrets → Add Secret**, create these two secrets:

| Name | Secret |
| --- | --- |
| `SOLO_VPS_DEPLOY_SSH_KEY` | The entire private CI key, including the `BEGIN OPENSSH PRIVATE KEY` and `END OPENSSH PRIVATE KEY` lines |
| `COOLIFY_API_TOKEN` | The token from the previous step |

To copy the private **CI key**, run **on your workstation**:

If you previously created the key in a different directory, use its actual path: set `$CiKey` in PowerShell or change the path passed to `cat` on Linux. Do not create another key.

=== "Windows PowerShell"

    ```powershell
    $CiKey = Join-Path (Join-Path $HOME '.ssh') 'solo-vps-demo-ci'
    Get-Content -Raw -LiteralPath $CiKey | Set-Clipboard
    ```

    Paste the clipboard into `SOLO_VPS_DEPLOY_SSH_KEY` and save the secret.

=== "Linux"

    ```bash
    cat ~/.ssh/solo-vps-demo-ci
    ```

    Copy the entire output into `SOLO_VPS_DEPLOY_SSH_KEY` and save the secret. This is a private key: do not send the output to a chat or store it in the repository.

**On the same GitHub → production page**, under **Environment variables → Add Variable**, create:

| Name | Value |
| --- | --- |
| `SOLO_VPS_DEPLOY_HOST` | The `SERVER_IP` value only, without a user, protocol or port |
| `SOLO_VPS_DEPLOY_SSH_FINGERPRINT` | First value from step 9: the complete CI-key fingerprint, **including `SHA256:`** |
| `SOLO_VPS_SSH_KNOWN_HOSTS` | Second value from step 9: the complete `IP ssh-ed25519 ...` line |
| `COOLIFY_RESOURCE_UUID` | The application UUID from step 10 |

You should now have **two secrets and four variables** in `production`.

## 12. Enable automatic deployment

**On GitHub, in the solo-vps-demo repository:**

1. Open **Settings → Secrets and variables → Actions → Variables**.
2. Select **New repository variable**.
3. Set **Name** to `SOLO_VPS_DEPLOY_ENABLED` and **Value** to `true`.
4. Select **Add variable**.

This one variable belongs **at repository level**, outside `production`: it enables the deploy job. Saving it does not trigger a deployment. The next application change will exercise it.

## 13. Release version two through a pull request

**On your workstation, in the solo-vps-demo terminal:**

```bash
git switch -c demo-version-2
```

Open `app.py` in your editor. Replace only this line:

```python
APP_VERSION: Final = "1"
```

with:

```python
APP_VERSION: Final = "2"
```

Save the file. **In the same workstation terminal:**

```bash
git add app.py
git commit -m "Show application version 2"
git push -u origin demo-version-2
```

**On GitHub:**

1. Open **Pull requests → New pull request**.
2. Select base `main`, compare `demo-version-2`, then **Create pull request**.
3. Wait for green tests, migration preflight and **Build pull request image**. A PR does not publish or deploy the application.
4. Select **Merge pull request → Confirm merge**.
5. Open **Actions** and the run for the new commit on `main`.
6. Wait for successful publication, digest verification and **Deploy immutable image to Coolify**. If your environment requires approval, approve the waiting deployment first.

**In your browser**, refresh `https://app.example.com/`. It should now show `version: "2"`. **Coolify → application → Deployments** will contain a new deployment.

CI/CD is working: the GitHub change passed checks and reached the VPS automatically. Do not run a manual Deploy for this application while its CI deploy job is running.

## 14. Change an environment variable

**In Coolify → application → Environment Variables:**

1. Select **+ Add** in the regular application's section, not Preview Deployments.
2. Set **Name** to `APP_MESSAGE`.
3. Set **Value** to `Hello from Coolify`.
4. Enable **Available at Runtime** and disable **Available at Buildtime**.
5. Select **Save**.
6. Once CI has finished, select the application's **Redeploy** and wait for successful startup.

Refresh `https://app.example.com/`. The version stays `2`, and the message becomes `Hello from Coolify`. No image rebuild or Git change is needed.

Add real application passwords and API tokens here in the same way, for runtime only. The demonstration `APP_MESSAGE` is not secret: the application deliberately returns it. Do not expose secrets in HTTP responses or logs, add them to `app.py` or the Dockerfile, or commit them to Git.

GitHub holds the two **deployment** secrets. Coolify holds the **running application's** variables and secrets.

## 15. Find logs and deployment results

**In your browser**, open the application's `/` and `/healthz` again.

**In Coolify → application → Logs**, find recent `GET /` and `GET /healthz` lines with status `200`. This is the running application's output.

| What happened | Where to look |
| --- | --- |
| Tests, build or automatic delivery failed | GitHub → repository → Actions → run → red job |
| Container did not start | Coolify → application → Deployments → latest deployment |
| Running application has an error | Coolify → application → Logs |
| An ENV value or secret needs changing | Coolify → application → Environment Variables |

## Done: basic setup is complete

After successfully completing these steps, you have a configured VPS, Coolify and an application over HTTPS, GitHub CI/CD, dedicated deployment access, runtime variables and a place for secrets, and live application logs.

You can move on to your own application. The demo has no database, and viewing live logs does not configure long-term log retention.

Continue with [After basic setup](after-basic-setup.md): retained logs, backups and notifications. To understand how to operate the platform first, open [Daily operations](operator-ui.md).

Choose additional tasks when needed:

- [Application config and secrets](application-config-and-secrets.md) — additional runtime settings.
- [External uptime alerts](external-uptime.md) — learn about outages independently of the VPS.
- [Off-site backups](../backups-restic.md) — configure before storing valuable data.
- [PostgreSQL backup and restore](../database-backups.md) — when you add a database.
- [Retained logs and metrics](observability.md) — when you need history.

## If a step does not finish

### Deploy failed because of the fingerprint after merge

If Deploy stopped before the SSH connection after successfully publishing the image, check `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`. With the older workflow, an invalid format could produce only `Process completed with exit code 1` immediately after `PASS release revision`; that exit code alone does not identify the cause.

1. Open **GitHub → repository → Settings → Environments → production → Environment variables**.
2. Edit `SOLO_VPS_DEPLOY_SSH_FINGERPRINT`: paste the entire first value from step 9, including **`SHA256:`**, and save.
3. Open **Actions → failed run after merge → Re-run jobs → Re-run failed jobs**. Fixing the variable does not require a new PR or image rebuild.
4. Wait for Deploy to succeed, then refresh the application URL: expect `version: "2"`. Continue with step 14.

A re-run uses the original commit. If `main` has advanced, the freshness check skips the old deployment; use the run for the current `main`. If the error differs or deployment has already started in Coolify, read its log first.

| Symptom | What to check |
| --- | --- |
| Starter says the directory exists | Do not blindly enter it. Choose a new directory name and create the app again |
| Initial push is rejected | The URL should point to a new empty repository; check Git authentication and repository rules |
| Coolify cannot pull the image | The GHCR package must be Public; recheck the name and `sha256-…` after resource creation |
| Domain does not open | A record, no incorrect AAAA record, provider ports 80/443, Proxy Running and deployment log |
| Deploy job is skipped after merge | `SOLO_VPS_DEPLOY_ENABLED=true` belongs in repository variables; inspect the `main` run, not the PR |
| CI SSH verification fails | Secret must contain the private CI key; fingerprint identifies that key; known_hosts identifies the server at the same IP |
| API returns 401/403 | API Access, token expiry and all three permissions: `read`, `write`, `deploy` |
| CI reports timeout or unknown status | Inspect Coolify Deployments first: the original deployment may still be running. Follow the [rollback guide](deployment-rollback.md) for further action |

UI labels were checked against Coolify 4.1.2. Further details: [Coolify API tokens](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Livewire/Security/ApiTokens.php), [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
