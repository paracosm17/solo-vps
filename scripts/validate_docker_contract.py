#!/usr/bin/env python3
"""Validate the M7 Docker repository/install sequencing contract without contacting a host."""

from __future__ import annotations

import pathlib
import sys


class ContractError(ValueError):
    pass


def validate_root(root: pathlib.Path) -> None:
    tasks_path = root / "ansible/roles/docker/tasks/main.yml"
    verify_path = root / "ansible/roles/docker/tasks/verify.yml"
    defaults_path = root / "ansible/roles/docker/defaults/main.yml"
    source_path = root / "ansible/roles/docker/templates/docker.sources.j2"

    tasks = tasks_path.read_text(encoding="utf-8")
    verify = verify_path.read_text(encoding="utf-8")
    defaults = defaults_path.read_text(encoding="utf-8")
    source = source_path.read_text(encoding="utf-8")

    required_source = [
        "Types: deb",
        "URIs: {{ solo_vps_docker_repository_uri }}",
        "Suites: {{ ansible_facts.distribution_release }}",
        "Components: stable",
        "Architectures: {{ solo_vps_docker_dpkg_architecture.stdout | trim }}",
        "Signed-By: {{ solo_vps_docker_key_path }}",
    ]
    for token in required_source:
        if token not in source:
            raise ContractError(f"Docker deb822 source is missing required field: {token}")

    required_tasks = [
        "Inspect whether Docker Engine is already installed before any repository mutation",
        "Refuse an unmanaged existing Docker binary before any repository mutation",
        "Derive the installed Docker CE package major before any repository mutation",
        "Refuse an unsupported existing Docker major before any Docker role mutation",
        "solo_vps_docker_existing_server_major in solo_vps_docker_supported_major_versions",
        "register: solo_vps_docker_repository_key_result",
        "register: solo_vps_docker_repository_source_result",
        "Derive whether Docker package installation is still required",
        "Refresh APT metadata after Docker repository changes or before first install",
        "update_cache: true",
        "solo_vps_docker_missing_packages | length > 0",
        "Confirm Docker CE is available from the configured repository",
        "{{ solo_vps_apt_cache_binary }}",
        "Refuse Docker installation when the official repository has no package candidate",
        "Candidate:",
        "Derive the Docker CE candidate major version",
        "Refuse an untested Docker major before first installation",
        "solo_vps_docker_ce_candidate_major in solo_vps_docker_supported_major_versions",
        "Install Docker Engine, Buildx, and Compose plugin packages",
    ]
    for token in required_tasks:
        if token not in tasks:
            raise ContractError(f"Docker install flow is missing sequencing contract: {token}")

    if "cache_valid_time:" in tasks:
        raise ContractError(
            "Docker repository refresh must not be suppressed by a generic cache_valid_time after adding a new source"
        )
    if "solo_vps_apt_cache_binary: /usr/bin/apt-cache" not in defaults:
        raise ContractError("Docker defaults must pin the apt-cache probe path")
    for token in (
        "solo_vps_docker_supported_major_versions:\n  - 29",
        "solo_vps_docker_minimum_major_version: 29",
        "solo_vps_docker_maximum_major_version: 29",
    ):
        if token not in defaults:
            raise ContractError(f"Docker 29.x support window missing from defaults: {token}")
    if "solo_vps_docker_server_major in solo_vps_docker_supported_major_versions" not in verify:
        raise ContractError("Docker verification must reject installed engines outside the supported major window")

    existing_major_expression = "regex_findall('^(?:[0-9]+:)?([0-9]+)[.]')"
    if existing_major_expression not in tasks:
        raise ContractError(
            "existing Docker package major parser must avoid escaped capture backreferences"
        )

    order = [
        "Refuse an unsupported existing Docker major before any Docker role mutation",
        "Configure the Docker official APT repository",
        "Refresh APT metadata after Docker repository changes or before first install",
        "Confirm Docker CE is available from the configured repository",
        "Refuse Docker installation when the official repository has no package candidate",
        "Refuse an untested Docker major before first installation",
        "Install Docker Engine, Buildx, and Compose plugin packages",
    ]
    positions = [tasks.index(token) for token in order]
    if positions != sorted(positions):
        raise ContractError("Docker repository refresh/candidate/install tasks are in an unsafe order")


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        validate_root(root)
    except (ContractError, OSError) as exc:
        print(f"ERROR Docker contract: {exc}", file=sys.stderr)
        return 2
    print(
        "PASS Docker contract: unsupported existing/fresh Docker majors fail before mutation/install, "
        "and repository metadata is refreshed before supported package installation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
