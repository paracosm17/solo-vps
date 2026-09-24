#!/usr/bin/env python3
"""Validate the M12 dependency/image update hygiene contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import yaml


BASE_IMAGE_RE = re.compile(r"^python:(\d+)\.(\d+)\.(\d+)-slim-bookworm$")
EXACT_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def fail(message: str) -> None:
    raise ValueError(message)


def as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        fail(f"{label} must be a mapping")
    return value


def as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    return value


def validate_dependabot(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = as_mapping(data, "dependabot root")
    if set(root) != {"version", "updates"}:
        fail("dependabot root must contain exactly version and updates")
    if root.get("version") != 2:
        fail("dependabot version must be 2")

    updates = as_list(root.get("updates"), "dependabot updates")
    if len(updates) != 3:
        fail("dependency hygiene must contain Docker, GitHub Actions and pip updaters")

    update = as_mapping(updates[0], "Docker updater")
    allowed_keys = {
        "package-ecosystem",
        "directory",
        "schedule",
        "open-pull-requests-limit",
        "ignore",
    }
    if set(update) != allowed_keys:
        fail("Docker updater keys must stay minimal and explicit")
    if update.get("package-ecosystem") != "docker":
        fail("package-ecosystem must be docker")
    if update.get("directory") != "/examples/hello-app":
        fail("Docker updater must target only /examples/hello-app")
    if update.get("open-pull-requests-limit") != 2:
        fail("open-pull-requests-limit must be 2")

    ignore = as_list(update.get("ignore"), "Docker updater ignore")
    if len(ignore) != 1:
        fail("Docker updater must contain exactly one Python update policy")
    python_policy = as_mapping(ignore[0], "Python update policy")
    if python_policy.get("dependency-name") != "python":
        fail("Docker updater ignore policy must target python")
    if python_policy.get("update-types") != [
        "version-update:semver-major",
        "version-update:semver-minor",
    ]:
        fail("automatic Python updates must stay patch-only within the current feature series")
    if set(python_policy) != {"dependency-name", "update-types"}:
        fail("Python update policy contains unexpected keys")

    schedule = as_mapping(update.get("schedule"), "Docker updater schedule")
    if schedule != {"interval": "weekly"}:
        fail("Docker updates must use the simple weekly schedule")

    for item, ecosystem in zip(updates[1:], ("github-actions", "pip")):
        updater = as_mapping(item, f"{ecosystem} updater")
        if updater != {
            "package-ecosystem": ecosystem,
            "directory": "/",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 2,
        }:
            fail(f"{ecosystem} updater must be weekly, root-scoped and limited to two PRs")


def validate_ansible_requirements(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = as_mapping(data, "Ansible requirements root")
    if set(root) != {"collections"}:
        fail("Ansible requirements must contain only the collections list")

    collections = as_list(root.get("collections"), "Ansible collections")
    if len(collections) != 1:
        fail("current project contract expects exactly one explicit Ansible collection")

    collection = as_mapping(collections[0], "Ansible collection")
    if set(collection) != {"name", "version"}:
        fail("Ansible collection entry must contain exactly name and version")
    if collection.get("name") != "community.general":
        fail("current external Ansible collection must be community.general")

    version = collection.get("version")
    if not isinstance(version, str) or not EXACT_SEMVER_RE.fullmatch(version):
        fail("community.general must be pinned to one exact X.Y.Z version")


def validate_dockerfile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    from_lines = [
        line.strip() for line in text.splitlines() if line.strip().upper().startswith("FROM ")
    ]
    if len(from_lines) != 1:
        fail("hello-app Dockerfile must contain exactly one FROM")

    image = from_lines[0].split(maxsplit=1)[1].strip()
    if "@sha256:" in image:
        fail(
            "hello-app base image must not use a digest in this Dependabot slice; "
            "current updater policy would miss same-tag digest rebuilds"
        )
    if not BASE_IMAGE_RE.fullmatch(image):
        fail("hello-app base image must use python:X.Y.Z-slim-bookworm exact patch tag")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dependabot", type=Path)
    parser.add_argument("dockerfile", type=Path)
    parser.add_argument("ansible_requirements", type=Path)
    args = parser.parse_args()

    try:
        validate_dependabot(args.dependabot)
        validate_dockerfile(args.dockerfile)
        validate_ansible_requirements(args.ansible_requirements)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR dependency hygiene contract: {exc}", file=sys.stderr)
        return 2

    print(
        "PASS dependency hygiene contract: weekly Docker/Actions/pip updates + exact patch base image + exact Ansible collection pin"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
