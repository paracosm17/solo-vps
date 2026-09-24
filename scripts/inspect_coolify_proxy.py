#!/usr/bin/env python3
"""Read-only, redacted Docker evidence for the managed Traefik TCP edge."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


class ProxyError(ValueError):
    pass


def safe_ports(bindings: object) -> bool:
    """Require both HTTP/S mappings, and reject every additional publication."""
    if not isinstance(bindings, dict):
        return False
    published = {key: value for key, value in bindings.items() if value}
    if set(published) != {"80/tcp", "443/tcp"}:
        return False
    for key, values in published.items():
        if not isinstance(values, list):
            return False
        for binding in values:
            if not isinstance(binding, dict):
                return False
            if binding.get("HostIp") not in {"", "0.0.0.0", "::"}:
                return False
            if binding.get("HostPort") != key.split("/")[0]:
                return False
    return True


def evidence(container: dict) -> dict:
    config = container.get("Config") or {}
    labels = config.get("Labels") or {}
    host = container.get("HostConfig") or {}
    if (
        container.get("Name") != "/coolify-proxy"
        or labels.get("coolify.proxy") != "true"
        or labels.get("com.docker.compose.service") != "traefik"
        or not config.get("Image", "").startswith("traefik:")
        or host.get("NetworkMode") == "host"
    ):
        raise ProxyError("The proxy is not the supported Coolify Compose Traefik container; inspect it before changing ports.")
    state = container.get("State") or {}
    running = state.get("Running") is True
    ports_safe = safe_ports(host.get("PortBindings"))
    if running:
        ports_safe = ports_safe and safe_ports((container.get("NetworkSettings") or {}).get("Ports"))
    return {
        "present": True,
        "running": running,
        "healthy": (state.get("Health") or {}).get("Status") == "healthy",
        "ports_safe": ports_safe,
    }


def inspect(docker: str) -> dict:
    def run(args: list[str]) -> str:
        result = subprocess.run([docker, *args], capture_output=True, text=True, timeout=30, check=False)
        if result.returncode:
            # Docker inspect/config output can contain operator secrets; never echo it.
            raise ProxyError("Docker proxy inspection failed; inspect Docker locally.")
        return result.stdout

    identifiers = run(["container", "ls", "--all", "--filter", "name=^/coolify-proxy$", "--format", "{{.ID}}"])
    if not identifiers.strip():
        return {"present": False, "running": False, "healthy": False, "ports_safe": True}
    rows = json.loads(run(["container", "inspect", "coolify-proxy"]))
    if not isinstance(rows, list) or len(rows) != 1:
        raise ProxyError("Docker returned an ambiguous proxy identity.")
    return evidence(rows[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="/usr/bin/docker")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.docker)))
    except (ProxyError, OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        print("ERROR: cannot inspect the supported Coolify Traefik proxy safely; review its identity and Docker state.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
