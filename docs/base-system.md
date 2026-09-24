# Base system baseline

The base role keeps the Ubuntu host intentionally small. Solo VPS installs only packages needed by the core one-VPS workflow and leaves application dependencies to containers/Coolify.

## What is managed

`make apply` / `make bootstrap` can:

- set `server.hostname`;
- set `server.timezone`;
- refresh stale APT metadata;
- install the core package set:
  - `ca-certificates`
  - `curl`
  - `git`
  - `jq`
  - `lsof`
  - `rsync`
  - `sudo`
  - `tzdata`
  - `unzip`

The base role does **not** run a full/dist upgrade.

## Configure hostname and timezone

In the persistent config:

```yaml
server:
  host: YOUR_SERVER_IP
  hostname: solo-vps-01
  timezone: UTC
```

`server.host` is the address Ansible connects to. `server.hostname` is the Linux hostname. Keep them conceptually separate.

## Apply and verify

Use the normal lifecycle rather than invoking the base role directly:

```bash
make apply
make verify
```

## Why the package list stays small

A broad host package collection increases update surface and makes the VPS harder to reason about. Application runtimes belong in application images unless the host genuinely needs them.
