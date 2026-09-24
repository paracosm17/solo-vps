#!/usr/bin/env python3
"""Validate the source-only M14 pinned restic host-tooling contract."""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR backup tooling contract: PyYAML is required.", file=sys.stderr)
    raise SystemExit(127)

EXPECTED_VERSION = "0.19.1"
EXPECTED_ARCHES = {"x86_64": "amd64", "aarch64": "arm64"}
EXPECTED_SHA256 = {
    "x86_64": "f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c",
    "aarch64": "a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465",
}
EXPECTED_INSTALL_PATH = "/usr/local/bin/restic"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    pass


def load_yaml(path: pathlib.Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read/parse {path}: {exc}") from exc


def validate_defaults(data: Any) -> None:
    if not isinstance(data, dict):
        raise ContractError("backup defaults must be a YAML mapping")

    version = data.get("solo_vps_restic_version")
    if version != EXPECTED_VERSION:
        raise ContractError(f"restic version must be exact {EXPECTED_VERSION}")

    if data.get("solo_vps_restic_install_path") != EXPECTED_INSTALL_PATH:
        raise ContractError("restic install path must remain /usr/local/bin/restic")

    artifacts = data.get("solo_vps_restic_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(EXPECTED_ARCHES):
        raise ContractError("restic artifacts must cover exactly x86_64 and aarch64")

    for ansible_arch, release_arch in EXPECTED_ARCHES.items():
        item = artifacts[ansible_arch]
        if not isinstance(item, dict):
            raise ContractError(f"artifact {ansible_arch} must be a mapping")
        url = item.get("url")
        digest = item.get("sha256")
        if not isinstance(url, str):
            raise ContractError(f"artifact {ansible_arch} URL must be a string")
        parsed = urlparse(url)
        expected_path = (
            f"/restic/restic/releases/download/v{EXPECTED_VERSION}/"
            f"restic_{EXPECTED_VERSION}_linux_{release_arch}.bz2"
        )
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != expected_path:
            raise ContractError(f"artifact {ansible_arch} must use the exact official GitHub release URL")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ContractError(f"artifact {ansible_arch} must have an exact SHA-256 pin")
        if digest != EXPECTED_SHA256[ansible_arch]:
            raise ContractError(f"artifact {ansible_arch} SHA-256 does not match the reviewed 0.19.1 pin")

    conflicts = data.get("solo_vps_restic_conflicting_paths")
    if conflicts != ["/usr/bin/restic", "/snap/bin/restic"]:
        raise ContractError("unmanaged distro/snap restic migration guards must remain explicit")


def validate_task_policy(role_dir: pathlib.Path) -> None:
    apply_text = (role_dir / "tasks" / "install-restic.yml").read_text(encoding="utf-8")
    verify_text = (role_dir / "tasks" / "verify-tooling.yml").read_text(encoding="utf-8")

    required_apply_markers = [
        "ansible.builtin.get_url:",
        "checksum:",
        "ansible.builtin.copy:",
        "remote_src: true",
        "ansible.builtin.import_tasks: inspect-existing.yml",
        "always:",
    ]
    for marker in required_apply_markers:
        if marker not in apply_text:
            raise ContractError(f"install task is missing required safety marker: {marker}")

    forbidden_apply_markers = [
        "restic self-update",
        "ansible.builtin.shell:",
        "ansible.builtin.raw:",
        "state: latest",
        "restic init",
        "RESTIC_PASSWORD",
        "AWS_SECRET_ACCESS_KEY",
        "systemd_service",
        "cron:",
    ]
    for marker in forbidden_apply_markers:
        if marker in apply_text:
            raise ContractError(f"install task contains out-of-scope behavior: {marker}")

    allowed_verify_modules = {
        "ansible.builtin.import_tasks",
        "ansible.builtin.stat",
        "ansible.builtin.command",
        "ansible.builtin.assert",
        "ansible.builtin.debug",
    }
    modules = set(re.findall(r"^\s+(ansible\.builtin\.[a-zA-Z0-9_]+):\s*$", verify_text, flags=re.MULTILINE))
    unexpected = sorted(modules - allowed_verify_modules)
    if unexpected:
        raise ContractError(f"verify-tooling contains non-read-only modules: {unexpected}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_backup_tooling.py <ansible/roles/backup>", file=sys.stderr)
        return 2
    role_dir = pathlib.Path(sys.argv[1])
    try:
        validate_defaults(load_yaml(role_dir / "defaults" / "main.yml"))
        validate_task_policy(role_dir)
    except (ContractError, OSError) as exc:
        print(f"ERROR backup tooling contract: {exc}", file=sys.stderr)
        return 2
    print("PASS backup tooling contract: pinned restic host tooling is source-safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
