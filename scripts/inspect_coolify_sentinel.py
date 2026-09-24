#!/usr/bin/env python3
"""Read-only, secret-safe inspection of a Coolify Sentinel container."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class SentinelInspectionError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SentinelInspectionError(message)


def _environment(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if separator:
            result[key] = value
    return result


def _mount(inspect: dict[str, Any], destination: str) -> dict[str, Any] | None:
    for item in inspect.get("Mounts") or []:
        if item.get("Destination") == destination:
            return item
    return None


def evaluate_inspect(
    payload: Any,
    *,
    expected_push_endpoint: str,
    expected_image: str | None = None,
    observed_version: str | None = None,
    expected_version: str | None = None,
) -> dict[str, Any]:
    parsed_url = urlparse(expected_push_endpoint)
    _require(
        parsed_url.scheme == "https" and bool(parsed_url.netloc) and not parsed_url.username,
        "expected Sentinel push endpoint must be a credential-free HTTPS URL",
    )
    _require(isinstance(payload, list) and len(payload) == 1, "docker inspect must return exactly one container")
    inspect = payload[0]
    _require(isinstance(inspect, dict), "docker inspect item must be an object")

    name = str(inspect.get("Name", "")).lstrip("/")
    config = inspect.get("Config") or {}
    state = inspect.get("State") or {}
    host_config = inspect.get("HostConfig") or {}
    network = inspect.get("NetworkSettings") or {}
    environment = _environment(config.get("Env") or [])

    _require(name == "coolify-sentinel", "container name must be coolify-sentinel")
    _require(state.get("Status") == "running", "Sentinel container is not running")
    _require((state.get("Health") or {}).get("Status") == "healthy", "Sentinel container is not healthy")
    _require(host_config.get("PidMode") == "host", "Sentinel must match the reviewed upstream host PID contract")
    _require(not (host_config.get("PortBindings") or {}), "Sentinel must not publish a host port")

    for bindings in (network.get("Ports") or {}).values():
        _require(not bindings, "Sentinel has an unexpected published network port")

    socket_mount = _mount(inspect, "/var/run/docker.sock")
    _require(socket_mount is not None, "Sentinel Docker socket mount is missing")
    _require(socket_mount.get("Source") == "/var/run/docker.sock", "Sentinel Docker socket source drifted")
    _require(socket_mount.get("RW") is True, "Sentinel Docker socket access no longer matches reviewed upstream behavior")

    data_mount = _mount(inspect, "/app/db")
    _require(data_mount is not None, "Sentinel data mount is missing")
    _require(data_mount.get("Source") == "/data/coolify/sentinel", "Sentinel data mount source drifted")

    _require(bool(environment.get("TOKEN")), "Sentinel token is missing")
    _require(environment.get("PUSH_ENDPOINT") == expected_push_endpoint, "Sentinel push endpoint does not match the reviewed HTTPS URL")
    _require(environment.get("DEBUG") == "false", "Sentinel debug mode must remain disabled")
    _require(environment.get("COLLECTOR_ENABLED") in {"true", "false"}, "Sentinel collector setting is invalid")

    image = str(config.get("Image", ""))
    if expected_image:
        _require(image == expected_image, "Sentinel image does not match the evaluation candidate")
    if expected_version:
        _require(observed_version == expected_version, "Sentinel API version does not match the evaluation candidate")

    return {
        "status": "PASS",
        "container": name,
        "image": image,
        "runtime_status": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status"),
        "api_version": observed_version,
        "push_endpoint": expected_push_endpoint,
        "token_present": True,
        "debug_enabled": False,
        "metrics_collector_enabled": environment.get("COLLECTOR_ENABLED") == "true",
        "host_pid_namespace": True,
        "docker_socket": "read-write (upstream Coolify contract)",
        "host_ports_published": False,
        "data_path": "/data/coolify/sentinel",
        "mutation": False,
        "secrets_printed": False,
    }


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise SentinelInspectionError(f"command failed: {detail}")
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", default="/usr/bin/docker")
    parser.add_argument("--inspect-json", type=Path)
    parser.add_argument("--expected-push-endpoint", required=True)
    parser.add_argument("--expected-image")
    parser.add_argument("--expected-version")
    args = parser.parse_args()

    try:
        if args.inspect_json:
            payload = json.loads(args.inspect_json.read_text(encoding="utf-8"))
            observed_version = args.expected_version
        else:
            payload = json.loads(_run([args.docker, "container", "inspect", "coolify-sentinel"]))
            observed_version = _run(
                [args.docker, "exec", "coolify-sentinel", "curl", "-fsS", "http://127.0.0.1:8888/api/version"]
            )
            _require(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", observed_version)), "Sentinel API returned an invalid version")
        report = evaluate_inspect(
            payload,
            expected_push_endpoint=args.expected_push_endpoint,
            expected_image=args.expected_image,
            observed_version=observed_version,
            expected_version=args.expected_version,
        )
    except (OSError, json.JSONDecodeError, SentinelInspectionError) as exc:
        print(f"ERROR Sentinel inspection: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
