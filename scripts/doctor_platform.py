#!/usr/bin/env python3
"""Report local readiness for optional Solo VPS platform capabilities without network access."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR platform doctor: PyYAML is required (Python module 'yaml').", file=sys.stderr)
    raise SystemExit(127)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for import_root in (PROJECT_ROOT, SCRIPTS_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts.secrets_toolchain import (  # noqa: E402
    ToolchainError,
    check_installation,
    controller_platform,
    default_cache_root,
    install_dir,
    load_manifest,
)
from scripts.validate_backup_policy import BackupPolicyError, validate as validate_backup_policy  # noqa: E402
from scripts.validate_config import ConfigError, validate_config  # noqa: E402
from scripts.validate_secrets_policy import validate as validate_secrets_policy  # noqa: E402


class PlatformDoctorError(ValueError):
    """Raised when a configured local capability is internally inconsistent."""


@dataclass(frozen=True)
class Capability:
    name: str
    status: str
    detail: str


NON_FATAL_STATUSES = {"READY", "PENDING", "NOT_CONFIGURED", "NOT_INSTALLED", "UNSUPPORTED"}


def load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlatformDoctorError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise PlatformDoctorError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlatformDoctorError(f"'{path}' must be a YAML mapping")
    return value


def inventory_user(data: Any) -> str:
    root = require_mapping(data, "inventory")
    all_group = require_mapping(root.get("all"), "all")
    hosts = require_mapping(all_group.get("hosts"), "all.hosts")
    if len(hosts) != 1:
        raise PlatformDoctorError(
            f"'all.hosts' must contain exactly one VPS during single-host MVP; found {len(hosts)}"
        )
    inventory_name, raw_vars = next(iter(hosts.items()))
    host_vars = {} if raw_vars is None else require_mapping(raw_vars, f"all.hosts.{inventory_name}")
    user = host_vars.get("ansible_user")
    if not isinstance(user, str) or not user.strip() or user != user.strip():
        raise PlatformDoctorError(f"'all.hosts.{inventory_name}.ansible_user' must be a non-empty string")
    return user


def is_documentation_backup(repository: Any) -> bool:
    if not isinstance(repository, dict):
        return False
    endpoint = repository.get("endpoint")
    if not isinstance(endpoint, str):
        return False
    try:
        hostname = urlsplit(endpoint).hostname
    except ValueError:
        return False
    if not hostname:
        return False
    hostname = hostname.rstrip(".").lower()
    return hostname == "example.com" or hostname.endswith(".example.com")


def check_admin_path(config: dict[str, Any], inventory: Any) -> Capability:
    admin = require_mapping(config.get("admin"), "admin")
    admin_user = admin.get("user")
    if not isinstance(admin_user, str):
        raise PlatformDoctorError("'admin.user' must be a string")
    current_user = inventory_user(inventory)
    if current_user == admin_user:
        return Capability(
            "admin_activation_path",
            "READY",
            f"inventory connects as managed admin.user '{admin_user}'",
        )
    return Capability(
        "admin_activation_path",
        "PENDING",
        f"inventory ansible_user '{current_user}' differs from admin.user '{admin_user}'; after bootstrap run `make use-admin`",
    )


def check_backup_policy(config: dict[str, Any], root: Path) -> Capability:
    backup = config.get("backup")
    if backup is None:
        return Capability("backup_policy", "NOT_CONFIGURED", "optional backup metadata is absent")
    backup_map = require_mapping(backup, "backup")
    repository = backup_map.get("repository")
    if is_documentation_backup(repository):
        return Capability(
            "backup_policy",
            "NOT_CONFIGURED",
            "backup repository still uses documentation-only example metadata",
        )

    defaults_path = root / "ansible" / "roles" / "backup" / "defaults" / "main.yml"
    defaults = load_yaml(defaults_path, "backup defaults")
    try:
        locator = validate_backup_policy(config, defaults)
    except BackupPolicyError as exc:
        raise PlatformDoctorError(f"configured backup policy is invalid: {exc}") from exc
    return Capability("backup_policy", "READY", f"non-secret repository metadata is valid: {locator}")


def check_secrets_policy(root: Path, policy_path: Path, recipient_path: Path) -> Capability:
    live_policy = policy_path.expanduser().resolve()
    live_recipient = recipient_path.expanduser().resolve()
    if not live_policy.exists() and not live_recipient.exists():
        return Capability(
            "secrets_policy",
            "NOT_CONFIGURED",
            "persistent SOPS policy/recipient are not initialized on this workstation",
        )
    try:
        validate_secrets_policy(root, policy_path=live_policy, recipient_path=live_recipient)
    except (OSError, ValueError) as exc:
        raise PlatformDoctorError(f"configured local SOPS policy is invalid: {exc}") from exc
    return Capability("secrets_policy", "READY", "persistent SOPS policy/recipient are internally consistent")


def check_secrets_toolchain(root: Path, cache_dir: Path | None) -> Capability:
    manifest_path = root / "tools" / "secrets-toolchain.json"
    try:
        manifest = load_manifest(manifest_path)
    except ToolchainError as exc:
        raise PlatformDoctorError(f"pinned secrets toolchain manifest is invalid: {exc}") from exc
    try:
        platform_id = controller_platform()
    except ToolchainError as exc:
        return Capability("secrets_toolchain", "UNSUPPORTED", str(exc))

    cache_root = (cache_dir or default_cache_root()).expanduser().resolve()
    target = install_dir(cache_root, manifest, platform_id)
    if not target.exists():
        return Capability(
            "secrets_toolchain",
            "NOT_INSTALLED",
            f"pinned controller tools are absent from {target}",
        )
    try:
        check_installation(target, manifest_path, manifest, platform_id)
    except ToolchainError as exc:
        raise PlatformDoctorError(f"installed secrets toolchain failed integrity checks: {exc}") from exc
    return Capability("secrets_toolchain", "READY", f"pinned controller tools verified at {target}")


def inspect_capabilities(
    root: Path,
    config_path: Path,
    inventory_path: Path,
    cache_dir: Path | None = None,
    sops_policy: Path | None = None,
    sops_recipient: Path | None = None,
) -> list[Capability]:
    config = load_yaml(config_path, "config")
    inventory = load_yaml(inventory_path, "inventory")
    try:
        validate_config(config)
    except ConfigError as exc:
        raise PlatformDoctorError(f"config contract: {exc}") from exc
    config_map = require_mapping(config, "config")

    data_base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))).expanduser()
    state_root = data_base / "solo-vps"

    return [
        check_admin_path(config_map, inventory),
        check_backup_policy(config_map, root),
        check_secrets_policy(
            root,
            sops_policy or (state_root / "sops/.sops.yaml"),
            sops_recipient or (state_root / "sops/production.txt"),
        ),
        check_secrets_toolchain(root, cache_dir),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--sops-policy", type=Path, default=None, help="external persistent SOPS policy path")
    parser.add_argument("--sops-recipient", type=Path, default=None, help="external persistent public recipient path")
    parser.add_argument(
        "--secrets-cache-dir",
        type=Path,
        default=None,
        help="Override the controller cache root used only for the read-only SOPS/age integrity check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        results = inspect_capabilities(
            args.root.expanduser().resolve(),
            args.config.expanduser().resolve(),
            args.inventory.expanduser().resolve(),
            args.secrets_cache_dir.expanduser().resolve() if args.secrets_cache_dir else None,
            args.sops_policy.expanduser().resolve() if args.sops_policy else None,
            args.sops_recipient.expanduser().resolve() if args.sops_recipient else None,
        )
    except PlatformDoctorError as exc:
        print(f"ERROR platform doctor: {exc}", file=sys.stderr)
        return 2

    print("PASS doctor platform capability report")
    for result in results:
        if result.status not in NON_FATAL_STATUSES:
            print(f"ERROR platform doctor: unexpected status {result.status}", file=sys.stderr)
            return 2
        print(f"  {result.name}: {result.status} — {result.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
