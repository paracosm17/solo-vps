#!/usr/bin/env python3
"""Offline planner for the Solo VPS Docker/Coolify lifecycle contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


class LifecycleError(ValueError):
    pass


def load_policy(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LifecycleError("platform lifecycle policy must be a mapping")
    return data


def parse_engine_version(value: str) -> tuple[int, int, int]:
    value = value.strip()
    match = re.match(r"^(?:\d+:)?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise LifecycleError(f"cannot parse Docker Engine version: {value!r}")
    return tuple(int(part) for part in match.groups())


def classify_docker(policy: dict, version: str | None) -> dict:
    docker = policy.get("docker", {})
    supported = [int(item) for item in docker.get("supported_major_versions", [])]
    if not supported:
        raise LifecycleError("docker.supported_major_versions must not be empty")
    result = {
        "supported_major_versions": supported,
        "version_floor_inclusive": str(docker.get("version_floor_inclusive", "")),
        "version_ceiling_exclusive": str(docker.get("version_ceiling_exclusive", "")),
        "candidate_policy": str(docker.get("fresh_install_candidate_policy", "")),
    }
    if version is not None:
        parsed = parse_engine_version(version)
        result.update(
            {
                "observed_version": version,
                "observed_major": parsed[0],
                "supported": parsed[0] in supported,
            }
        )
    return result


def build_plan(policy: dict, docker_version: str | None = None) -> dict:
    coolify = policy.get("coolify", {})
    upgrade = coolify.get("supported_upgrade", {})
    current = str(coolify.get("current_supported", ""))
    previous = str(coolify.get("previous_supported", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", current):
        raise LifecycleError("coolify.current_supported must be a semantic version")
    if not re.fullmatch(r"\d+\.\d+\.\d+", previous):
        raise LifecycleError("coolify.previous_supported must be a semantic version")
    if upgrade.get("from") != previous or upgrade.get("to") != current:
        raise LifecycleError("Coolify supported upgrade path must match previous/current versions")

    return {
        "operation": "plan",
        "docker": classify_docker(policy, docker_version),
        "coolify": {
            "previous_supported": previous,
            "current_supported": current,
            "upgrade_path": f"{previous} -> {current}",
            "automatic_updates": bool(coolify.get("automatic_updates", False)),
            "fresh_restic_backup_required": bool(upgrade.get("require_fresh_restic_backup", False)),
            "offsite_instance_database_backup_required": bool(
                upgrade.get("require_verified_offsite_instance_database_backup", False)
            ),
            "local_control_plane_checkpoint_required": bool(upgrade.get("require_local_control_plane_checkpoint", False)),
            "automatic_downgrade_on_failure": bool(upgrade.get("automatic_downgrade_on_failure", True)),
            "failure_recovery": str(upgrade.get("failure_recovery", "")),
        },
        "network_request": False,
        "mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", nargs="?", default="plan", choices=("plan",))
    parser.add_argument("--policy", default="docs/contracts/platform-lifecycle-policy.yml")
    parser.add_argument("--docker-version")
    args = parser.parse_args()
    try:
        plan = build_plan(load_policy(Path(args.policy)), args.docker_version)
    except (OSError, yaml.YAMLError, LifecycleError) as exc:
        print(f"ERROR platform lifecycle plan: {exc}")
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    print("network_request: false")
    print("mutation: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
