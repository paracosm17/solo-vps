# 1. Set up the VPS and Coolify

By the end of this part, you will have a configured Ubuntu VPS and a Coolify dashboard available over HTTPS. In part two, you will deploy an application and enable automatic delivery.

Follow the steps in order. Each command block says where to run it: **workstation**, **VPS**, or **browser**.

## Before you begin

Prepare:

- a fresh **Ubuntu 24.04 LTS** VPS with **2 vCPU**, **2 GiB RAM** and at least **30 GiB free disk**;
- SSH access as `root` and access to the provider's recovery console;
- inbound TCP ports **22, 80, 443** allowed by the provider;
- a Windows PowerShell or Linux workstation with `ssh` and `scp`;
- a domain and access to its DNS records;
- access to the public Solo VPS repository (or a separately supplied test ZIP); you will also need the same source on your workstation in part two.

**PRE-ALPHA:** use a disposable VPS for now. The [source repository](https://github.com/paracosm17/solo-vps) is public, but there is no validated release yet. The command below clones the current `main`; `git rev-parse HEAD` reports its exact revision automatically if you need it for an evidence report.

This is the supported one-VPS alpha setup. Make/Ansible run on the VPS in the steps below; Windows PowerShell handles workstation SSH/SCP. If you run Linux-side project tools on Windows, use WSL. The exact release revision has not yet passed the clean-host and recovery gates; do not use this path as a production guarantee.

Choose these values before you start:

| Name | Value |
| --- | --- |
| `SERVER_IP` | Your VPS IPv4 address |
| `ADMIN_USER` | The Linux administrator name you want Solo VPS to create |
| `COOLIFY_DOMAIN` | Your Coolify dashboard domain, for example `coolify.example.com` |
| `REPOSITORY_URL` | `https://github.com/paracosm17/solo-vps.git` |

The project directory remains `solo-vps`. Commands below define their variables before use; replace every `YOUR_...` value. External backup storage, Grafana and another server are not required.

## 1. Connect to the fresh server

**On your workstation:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    ssh "root@$ServerIp"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ssh "root@${SERVER_IP}"
    ```

For the first connection, compare the SSH fingerprint with the provider console, accept the connection and enter the password supplied by the provider.

You now have an Ubuntu shell. Run the next commands on the VPS.

## 2. Install the prerequisites and get Solo VPS

**On the VPS as root:**

```bash
apt-get update
apt-get install -y --no-install-recommends make git nano ca-certificates
```

The first command refreshes package indexes; the second installs the tools needed to obtain and configure the project.

For this test, clone the public `main` branch. Once a release tag exists, use `git clone --branch v0.1.0 --depth 1 https://github.com/paracosm17/solo-vps.git solo-vps`. The ZIP path is for a separately supplied test archive only.

=== "Git"

    **On the VPS as root:**

    ```bash
    git clone https://github.com/paracosm17/solo-vps.git solo-vps
    cd solo-vps
    ```

    You are now in the Solo VPS directory. Run `git rev-parse HEAD` to record the exact revision for an evidence report; you do not need to enter it for installation.

=== "ZIP"

    For the current test, use the supplied `solo-vps.zip` with the project files directly at the archive root. GitHub's automatically generated source ZIP has a wrapper directory and does not match these commands; use the Git path for the public release.

    **On the VPS as root:**

    ```bash
    apt-get install -y --no-install-recommends unzip
    ```

    **On your workstation, in the archive directory:**

    === "Windows PowerShell"

        ```powershell
        $ServerIp = 'YOUR_SERVER_IP'
        scp solo-vps.zip "root@${ServerIp}:/root/solo-vps.zip"
        ```

    === "Linux"

        ```bash
        SERVER_IP='YOUR_SERVER_IP'
        scp solo-vps.zip "root@${SERVER_IP}:/root/solo-vps.zip"
        ```

    **Return to the VPS terminal as root:**

    ```bash
    unzip -q solo-vps.zip -d /root/solo-vps
    cd /root/solo-vps
    ```

    This directory contains `Makefile`, `scripts` and `ansible`. Keep the same source copy on your workstation for part two.

Some helpers in part two run on your workstation. After the admin handoff in step 7, copy the same `~/solo-vps` source directory from the VPS to your workstation using the commands there. This preserves the exact source revision without copying a hash manually.

## 3. Prepare the project and edit its configuration

**On the VPS as root, in solo-vps:**

```bash
make setup
nano ~/.local/share/solo-vps/config/config.yml
```

`make setup` installs the automation tools and creates the configuration. In the opened file, edit the `server` values and administrator name:

```yaml
server:
  host: YOUR_SERVER_IP
  hostname: solo-vps-01
  timezone: UTC

admin:
  user: YOUR_ADMIN_USER
```

These are fields to edit, not a replacement for the whole file. Preserve the other settings, including the SSH-key fields under `admin`.

`hostname` is the server's short name. You can keep `timezone` set to `UTC`.

Save the file: **Ctrl+O → Enter → Ctrl+X**.

**Only for a separate disposable 1 vCPU / 20 GiB VPS:** add the following section to the same config file. This permits one vCPU and at least 10 GiB **free** on `/` while retaining the RAM minimum. It is experimental and cannot close release evidence gates for the supported configuration. Watch free disk closely. Omit it on a supported VPS.

```yaml
evaluation:
  allow_small_vps: true
```

## 4. Send your administrator public key

This key lets you sign in from your workstation as the configured `admin.user`. The private key stays on your workstation.

**On your workstation, in a new terminal:**

=== "Windows PowerShell"

    Build the path to your usual `id_ed25519` key:

    ```powershell
    $SshDir = Join-Path $HOME '.ssh'
    $AdminKey = Join-Path $SshDir 'id_ed25519'
    ```

    If you do not have an SSH key yet, create it with the following commands. Set a passphrase for your personal key when prompted.

    ```powershell
    New-Item -ItemType Directory -Force -Path $SshDir | Out-Null
    ssh-keygen -t ed25519 -f $AdminKey -C 'Solo VPS admin'
    ```

    If the key already exists, use it without creating another one. Send its public part:

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    Get-Content -Raw -LiteralPath "$AdminKey.pub" | ssh "root@$ServerIp" 'cd ~/solo-vps && make human-admin-key-stdin'
    ```

=== "Linux"

    If you do not have `~/.ssh/id_ed25519` yet, create it. Set a passphrase for your personal key when prompted.

    ```bash
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -C 'Solo VPS admin'
    ```

    If the key already exists, use it without creating another one. Send its public part:

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    cat ~/.ssh/id_ed25519.pub | ssh "root@${SERVER_IP}" 'cd ~/solo-vps && make human-admin-key-stdin'
    ```

Expect `PASS human admin workstation key configuration` and `private_key_received: false`.

## 5. Configure the server

Keep the root terminal open and confirm you can open the provider's recovery console.

**In the retained VPS terminal as root:**

```bash
cd ~/solo-vps
make use-bootstrap SSH_USER=root
make prepare-access
make apply
```

`make use-bootstrap` selects the provider SSH user. `make prepare-access` trusts this VPS's own SSH host key and prepares its local automation key. `make apply` creates the administrator and configures the firewall, automatic security updates and Docker. Verification is included in the command.

Wait for `PASS Solo VPS host apply`.

## 6. Sign in as the administrator

**On your workstation, in another terminal:**

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

**In the new SSH session on the VPS:**

```bash
sudo -n id -u
```

Expect `0`. This confirms that the new administrator can execute sudo commands without a password. Keep this session open.

## 7. Secure SSH and switch to the administrator

After the successful administrator login and `0` result, you can disable password login and direct root login. The provider console must remain available.

**In the retained VPS terminal as root:**

```bash
cd ~/solo-vps
SSH_HARDENING_CONFIRM=I_HAVE_VERIFIED_PROVIDER_RECOVERY SSH_HARDENING_ADMIN_LOGIN_CONFIRM=I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN make secure
```

Wait for `PASS Solo VPS SSH security transition`. The command also prepares the project copy for the configured administrator.

**On your workstation, in a new terminal:**

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

**In this new SSH session on the VPS:**

```bash
cd ~/solo-vps
```

Run subsequent server commands here as the configured administrator.

**On your workstation, in the directory where you want to keep the source for part two:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    scp -r "${AdminUser}@${ServerIp}:solo-vps" .
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    scp -r "${ADMIN_USER}@${SERVER_IP}:solo-vps" .
    ```

If `solo-vps` already exists locally, choose another empty destination directory; do not overwrite local files.

## 8. Install Coolify

**On the VPS as the administrator, in solo-vps:**

```bash
make platform
make verify
```

The first command installs Coolify, prepares the localhost server and proxy, and verifies them. The second checks the configured host once as a whole.

Wait for `PASS Solo VPS application platform`, followed by verification completing without errors. You do not need to repeat the installation.

## 9. Register in Coolify

**On your workstation, in a separate terminal:**

=== "Windows PowerShell"

    ```powershell
    $ServerIp = 'YOUR_SERVER_IP'
    $AdminUser = 'YOUR_ADMIN_USER'
    ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 "${AdminUser}@${ServerIp}"
    ```

=== "Linux"

    ```bash
    SERVER_IP='YOUR_SERVER_IP'
    ADMIN_USER='YOUR_ADMIN_USER'
    ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:6001:127.0.0.1:6001 -L 127.0.0.1:6002:127.0.0.1:6002 "${ADMIN_USER}@${SERVER_IP}"
    ```

Keep this terminal open. Waiting without a shell prompt is normal for the SSH tunnel. Local port `18000` leaves `8000` available for the documentation site.

**In your browser:**

1. Open [http://127.0.0.1:18000](http://127.0.0.1:18000).
2. Create the first administrator account with a name, email and password.
3. On **Welcome to Coolify**, choose **Skip Setup**.
4. Open **Servers → localhost**.

Solo VPS already created this server. Expect **Server is reachable and validated** and **Proxy Running**. Use the existing `localhost`.

## 10. Set the dashboard domain

**In your domain's DNS panel**, create:

| Type | Name | Value |
| --- | --- | --- |
| A | `coolify` | VPS IPv4 address |

The example is `coolify.example.com`. With Cloudflare, select **DNS only**. Add an AAAA record only when working IPv6 is configured.

**In Coolify:**

1. Select **Settings with the gear icon near the bottom of the left sidebar**.
2. Open **Configuration → General**.
3. Set **URL** to `https://coolify.example.com`, replacing the domain with yours.
4. Select **Save**.
5. Open that HTTPS address in a new tab and sign in.

These are instance settings. **Servers → localhost → IP Address/Domain** is the SSH connection address; it remains `host.docker.internal`.

The dashboard should open over HTTPS with a valid certificate. Use its domain for everyday access. You can close the tunnel with **Ctrl+C** in its terminal.

## Done: the server and dashboard are ready

You have a configured administrator, secured SSH, Docker and Coolify over HTTPS.

**Continue to [2. Deploy an application and enable CI/CD](operations/first-app.md).** That page contains every required step for your application, automatic delivery, environment variables and logs.
