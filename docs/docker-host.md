# Docker host baseline

Solo VPS owns the Docker **host** configuration; Coolify owns application/container lifecycle on top of it.

## Supported target

The current alpha contract supports:

- Ubuntu 24.04 LTS;
- `x86_64` and `aarch64` host architectures;
- Docker Engine **29.x** only;
- Docker Compose plugin `2.24.4+` for the current Coolify integration.

The lifecycle fails closed outside the supported Docker major instead of silently crossing into Docker 30.

## What Solo VPS manages

The Docker role installs packages from Docker's official Ubuntu repository:

```text
docker-ce
docker-ce-cli
containerd.io
docker-buildx-plugin
docker-compose-plugin
```

It also owns `/etc/docker/daemon.json` with a deliberately small baseline:

```json
{
  "live-restore": true,
  "log-driver": "local",
  "log-opts": {
    "max-size": "20m",
    "max-file": "5"
  }
}
```

## Existing runtime safety gate

A fresh Solo VPS install refuses to silently replace conflicting distro/container runtime packages such as `docker.io`, `podman-docker`, or an independently managed `containerd`/`runc` stack.

If the host already has a container runtime, treat it as a migration decision rather than forcing the fresh-host role through it.

## Docker group

The managed administrator is allowed to operate Docker because Coolify integration requires it. Docker-group access is effectively root-equivalent; Solo VPS grants it only to the already privileged managed administrator.

## Networking boundary

Solo VPS does not set a global loopback bind default for application containers. Coolify is responsible for application networking and proxying.

Use `make audit` to review actual host/Docker publication. Do not assume UFW alone describes container exposure.

## Apply and verify

Use the normal lifecycle:

```bash
make apply
make verify
make audit
```

## Upgrades

Do not treat `make docker` as a general updater. The supported lifecycle is documented in [Upgrade guide](upgrades.md).
