# ADR-0005: Accept Coolify Sentinel only inside the Coolify trust boundary

Status: Proposed

Date: 2026-09-17

## Context

Coolify `4.3.19` made Sentinel mandatory on regular servers. Sentinel reports host and container status to Coolify and optionally stores CPU/RAM history. Its upstream container uses the host PID namespace and a read-write Docker socket, so it is a privileged part of the control plane rather than an isolated metrics sidecar.

Solo VPS keeps Coolify management ports loopback-only. The generated localhost Sentinel URL `http://host.docker.internal:8000` therefore cannot be the maintained communication path: making raw port `8000` public would weaken the existing boundary.

## Proposed decision

Treat Sentinel as part of the existing high-trust Coolify control plane, not as a separate low-trust monitoring component.

Accept a Coolify release that requires Sentinel only when disposable runtime evidence proves all of the following:

- Sentinel pushes to the existing public HTTPS Coolify dashboard URL with its generated authentication token;
- no Sentinel API port is published on the host;
- raw Coolify management ports remain loopback-only;
- debug mode is disabled and the exact image/version is known;
- host PID and read-write Docker socket access match the explicitly reviewed upstream contract;
- backup, recovery, verification and audit remain functional.

Metrics collection remains optional. Repository-managed Alloy remains the separate maintained path for retained logs and host metrics.

## Consequences

Sentinel compromise must be treated like Coolify control-plane compromise because its Docker socket access can control host containers. The component cannot honestly be described as least-privilege or read-only.

The HTTPS push path avoids exposing a new management port, but depends on the dashboard domain, TLS and reverse proxy being healthy. The disposable evaluation must therefore prove communication before and after the upgrade.

Until the candidate exercise passes, Solo VPS retains its existing supported Coolify pins. This proposal does not authorize an automatic upgrade or a downgrade-based recovery path.
