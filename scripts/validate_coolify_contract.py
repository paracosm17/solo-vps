#!/usr/bin/env python3
"""Validate the local pinned Coolify release/integration contract."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import yaml

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXPECTED_ARTIFACTS = {"docker-compose.yml", "docker-compose.prod.yml", ".env.production"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("defaults", type=pathlib.Path)
    return parser.parse_args()


def fail(message: str) -> int:
    print(f"ERROR Coolify contract: {message}", file=sys.stderr)
    return 2


def main() -> int:
    args = parse_args()
    try:
        data = yaml.safe_load(args.defaults.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return fail(f"cannot read/parse {args.defaults}: {exc}")

    if not isinstance(data, dict):
        return fail("role defaults must be a YAML mapping")

    version = data.get("solo_vps_coolify_version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        return fail("solo_vps_coolify_version must be an exact X.Y.Z release")

    image_tag = data.get("solo_vps_coolify_image_tag")
    if image_tag != "{{ solo_vps_coolify_version }}":
        return fail("Coolify image tag must derive from the exact pinned release version")

    if data.get("solo_vps_coolify_initial_access_mode") != "ssh-tunnel":
        return fail("initial access must remain ssh-tunnel until exposure is explicitly activated")

    if data.get("solo_vps_coolify_management_ports") != [8000, 6001, 6002]:
        return fail("management port contract must be exactly 8000/6001/6002")

    if data.get("solo_vps_coolify_management_bind_address") != "127.0.0.1":
        return fail("initial management bind address must remain 127.0.0.1")

    if data.get("solo_vps_coolify_minimum_compose_version") != "2.24.4":
        return fail("minimum Compose version must remain 2.24.4 for !override support")

    if data.get("solo_vps_coolify_compose_override_filename") != "docker-compose.solo-vps.yml":
        return fail("managed Compose override filename changed unexpectedly")

    artifacts = data.get("solo_vps_coolify_release_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(EXPECTED_ARTIFACTS):
        return fail("release artifact manifest is incomplete")

    names = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return fail("each release artifact must be a mapping")
        name = artifact.get("name")
        url = artifact.get("url")
        checksum = artifact.get("checksum")
        names.add(name)
        # The YAML URLs intentionally use a Jinja base variable, so validate both
        # the source host contract and the committed checksum locally.
        if not isinstance(url, str) or "solo_vps_coolify_release_base_url" not in url:
            return fail(f"{name}: URL must derive from the pinned release base URL")
        if not isinstance(checksum, str) or not SHA256_RE.fullmatch(checksum):
            return fail(f"{name}: checksum must be sha256:<64 lowercase hex>")

    if names != EXPECTED_ARTIFACTS:
        return fail(f"artifact names must be {sorted(EXPECTED_ARTIFACTS)}")

    base_url = data.get("solo_vps_coolify_release_base_url")
    if not isinstance(base_url, str) or "raw.githubusercontent.com/coollabsio/coolify" not in base_url:
        return fail("release base URL must use the official Coolify GitHub repository")
    if "solo_vps_coolify_release_tag" not in base_url:
        return fail("release base URL must derive from the exact release tag")

    if data.get("solo_vps_coolify_data_root") != "/data/coolify":
        return fail("Coolify data root must remain /data/coolify")

    print(f"PASS Coolify contract: v{version}, {len(artifacts)} pinned artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
