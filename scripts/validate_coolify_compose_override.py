#!/usr/bin/env python3
"""Validate the M9 loopback-only Docker Compose override contract."""

from __future__ import annotations

import argparse
import pathlib
import sys

import yaml


class OverrideList(list):
    """Marker for Docker Compose !override sequences."""


class ComposeLoader(yaml.SafeLoader):
    pass


def _construct_override(loader: ComposeLoader, node: yaml.Node) -> OverrideList:
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.YAMLError("!override must tag a sequence")
    return OverrideList(loader.construct_sequence(node, deep=True))


ComposeLoader.add_constructor("!override", _construct_override)

EXPECTED = {
    "coolify": [
        {
            "target": 8080,
            "published": "${APP_PORT:-8000}",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }
    ],
    "soketi": [
        {
            "target": 6001,
            "published": "${SOKETI_PORT:-6001}",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        },
        {
            "target": 6002,
            "published": "6002",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        },
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=pathlib.Path)
    return parser.parse_args()


def fail(message: str) -> int:
    print(f"ERROR Coolify Compose override: {message}", file=sys.stderr)
    return 2


def main() -> int:
    args = parse_args()
    try:
        data = yaml.load(args.template.read_text(encoding="utf-8"), Loader=ComposeLoader)
    except (OSError, yaml.YAMLError) as exc:
        return fail(f"cannot read/parse {args.template}: {exc}")

    if not isinstance(data, dict) or set(data) != {"services"}:
        return fail("override must contain only the services mapping")
    services = data.get("services")
    if not isinstance(services, dict) or set(services) != set(EXPECTED):
        return fail("override must modify only coolify and soketi")

    for service, expected_ports in EXPECTED.items():
        definition = services.get(service)
        if not isinstance(definition, dict) or set(definition) != {"ports"}:
            return fail(f"{service}: only ports may be overridden")
        ports = definition.get("ports")
        if not isinstance(ports, OverrideList):
            return fail(f"{service}: ports must use Docker Compose !override")
        if list(ports) != expected_ports:
            return fail(f"{service}: loopback port mapping differs from the pinned contract")

    print("PASS Coolify Compose override: 8000/6001/6002 -> 127.0.0.1 with !override")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
